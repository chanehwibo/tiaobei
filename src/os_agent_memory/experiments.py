"""Developer-held evaluation with dev-only threshold selection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter

from .evaluation import build_store_from_raw_records
from .ingestion import DataIngestionPipeline
from .preference import PreferenceExtractor
from .retrieval_evidence import DEFAULT_POLICY
from .service import MemoryService


CALIBRATION_POLICY = "similarity"


def split_rows(suite, section, split):
    return [row for row in suite.get(section, []) if row["split"] == split]


def retrieval_trial(suite, split, threshold, *, mode="hybrid", cache=True, include_pending=False,
                    embedding_config=None, evidence_policy=DEFAULT_POLICY):
    store = build_store_from_raw_records(split_rows(suite, "records", split), embedding_config=embedding_config)
    underlying = store.embedding
    class CountingProvider:
        calls = 0
        def encode(self, text):
            self.calls += 1
            return underlying.encode(text)
        def similarity(self, left, right):
            return underlying.similarity(left, right)
    provider = CountingProvider()
    store.embedding = provider
    rows = []
    for query in split_rows(suite, "retrieval_queries", split):
        if not cache:
            for memory in store.knowledge.values():
                memory.embedding = []
        started = perf_counter()
        hits = store.search_knowledge(
            query["query"], tenant_id=query["tenant_id"], user_id=query["user_id"],
            top_k=3, min_score=threshold, include_pending=include_pending,
            evidence_policy=evidence_policy,
            **({"retrieval_mode": mode} if mode != "hybrid" else {}),
        )
        elapsed = (perf_counter() - started) * 1000
        expected = set(query["expected_titles"])
        returned = [hit.title for hit in hits]
        intersection = expected & set(returned)
        rows.append({
            "id": query["id"], "difficulty": query.get("difficulty", "unknown"),
            "expected": sorted(expected), "returned": returned,
            "recall": len(intersection) / len(expected) if expected else None,
            "empty_correct": not returned if not expected else None,
            "precision": len(intersection) / len(returned) if returned else None,
            "latency_ms": round(elapsed, 4),
        })
    positives = [row["recall"] for row in rows if row["recall"] is not None]
    negatives = [row["empty_correct"] for row in rows if row["empty_correct"] is not None]
    positive_recall = sum(positives) / len(positives) if positives else 0
    empty_accuracy = sum(negatives) / len(negatives) if negatives else 0
    return {
        "split": split, "mode": mode, "threshold": threshold, "cache": cache,
        "evidence_policy": evidence_policy,
        "positive_queries": len(positives), "no_answer_queries": len(negatives),
        "positive_queries_fully_recalled": sum(value == 1 for value in positives),
        "no_answer_correct": sum(negatives),
        "positive_recall_at_3": round(positive_recall, 4),
        "no_answer_accuracy": round(empty_accuracy, 4),
        "balanced_score": round((positive_recall + empty_accuracy) / 2, 4),
        "mean_latency_ms": round(sum(row["latency_ms"] for row in rows) / max(len(rows), 1), 4),
        "query_phase_encode_calls": provider.calls,
        "rows": rows,
    }


def select_threshold(suite, *, mode="hybrid", embedding_config=None):
    # Reproduce the original dev calibration; a new evidence policy must not
    # silently retune the deployed .265 threshold or inspect test labels.
    trials = [retrieval_trial(suite, "dev", value / 100, mode=mode,
                              embedding_config=embedding_config, evidence_policy=CALIBRATION_POLICY)
              for value in range(8, 81)]
    def objective(row):
        return (row["balanced_score"], min(row["positive_recall_at_3"], row["no_answer_accuracy"]),
                row["positive_recall_at_3"])
    optimum = max(map(objective, trials))
    feasible = [trial for trial in trials if all(quality_targets(trial).values())]
    accepted = feasible or [trial for trial in trials if objective(trial) == optimum]
    accepted_thresholds = {trial["threshold"] for trial in accepted}
    # Maximise distance to a failing operating point within the dev-only region
    # satisfying BOTH targets. If infeasible, retain the best balanced fallback.
    plateaus = []
    for trial in trials:
        if trial["threshold"] in accepted_thresholds:
            if not plateaus or trial["threshold"] - plateaus[-1][-1] > .010001:
                plateaus.append([])
            plateaus[-1].append(trial["threshold"])
    plateau = max(plateaus, key=len)
    threshold = round((plateau[0] + plateau[-1]) / 2, 4)
    dev = {section: split_rows(suite, section, "dev") for section in ("records", "retrieval_queries")}
    digest = hashlib.sha256(json.dumps(dev, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {
        "selected_on": "dev", "mode": mode, "threshold": threshold,
        "scoring_version": "hybrid-cjk-character-v1",
        "calibration_evidence_policy": CALIBRATION_POLICY,
        "dev_operating_region": [plateau[0], plateau[-1]],
        "dev_targets_feasible": bool(feasible), "minimum_per_metric": .85,
        "dev_sha256": digest, "selection": "widest dev region meeting both 85% targets, midpoint; balanced fallback if infeasible",
        "trials": [{k: v for k, v in trial.items() if k not in {"rows", "mean_latency_ms"}} for trial in trials],
    }


def evaluate_frozen(suite, *, embedding_config=None):
    config = select_threshold(suite, embedding_config=embedding_config)
    trial = retrieval_trial(suite, "test", config["threshold"], embedding_config=embedding_config)
    return {
        "dataset": suite["name"], "independent_blind": False, "configuration": config,
        "dataset_sha256": hashlib.sha256(json.dumps(suite, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "test": trial, "quality_targets": quality_targets(trial),
        "evaluation_evidence_policy": DEFAULT_POLICY,
        "threshold_boundary": "historical similarity dev calibration retained; current policy evaluated without retuning",
        "limitations": suite.get("limitations", []),
    }


def quality_targets(trial):
    # Both classes must be present; an empty evaluation cannot pass.
    return {
        "positive_recall_at_3_ge_085": trial.get("positive_queries", 0) > 0 and trial["positive_recall_at_3"] >= .85,
        "no_answer_accuracy_ge_085": trial.get("no_answer_queries", 0) > 0 and trial["no_answer_accuracy"] >= .85,
    }


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def decay_diagnostics():
    """Targeted developer regressions, not a sample of real user effectiveness."""
    def events(prefix, source, value, count, date):
        content = {
            "brief": "用户要求后续回答保持简洁，直接给结论。",
            "detailed": "用户要求后续回答详细展开说明，给出原因。",
        }.get(value, "成功工具返回了可供用户采用的完整结果。")
        return [{
            "id": f"{prefix}-{i}", "source_type": source, "content": content,
            "timestamp": f"{date}T00:00:{i:02d}+00:00", "scene": "office",
            "tool_status": "succeeded" if source == "tool_result" else "unknown",
            "metadata": {"topic": "diagnostic", "tool_name": value},
        } for i in range(count)]

    old_style = events("old-style", "user_behavior", "brief", 8, "2025-01-01")
    new_style = events("new-style", "user_behavior", "detailed", 2, "2026-09-01")
    explicit = events("manual", "manual_config", "brief", 1, "2025-01-01")
    cases = [
        ("implicit_reversal", "output.verbosity", "detailed", old_style + new_style),
        ("tool_reversal", "preferred_tool:office", "current_editor",
         events("old-tool", "tool_result", "old_editor", 8, "2025-01-01")
         + events("new-tool", "tool_result", "current_editor", 2, "2026-09-01")),
        ("stable_control", "output.verbosity", "brief",
         old_style + events("stable", "user_behavior", "brief", 2, "2026-09-01")),
        ("manual_setting_persists", "output.verbosity", "brief", explicit + new_style),
        ("manual_revision", "output.verbosity", "detailed",
         explicit + events("revision", "manual_config", "detailed", 1, "2026-09-01")),
        ("failed_tool_negative_control", "preferred_tool:office", None,
         [{**row, "tool_status": "failed"} for row in
          events("failed", "tool_result", "broken_editor", 8, "2026-09-01")]),
    ]
    rows = []
    for identifier, key, expected, raw in cases:
        records = DataIngestionPipeline().ingest(raw)
        results = []
        for half_life in (30.0, None):
            memories = PreferenceExtractor(half_life_days=half_life).extract(records)
            predicted = next((p.value for p in memories if p.key == key), None)
            results.append({"half_life_days": half_life, "prediction": predicted,
                            "passed": predicted == expected})
        rows.append({"id": identifier, "key": key, "expected": expected,
                     "input_records": len(raw), "accepted_records": len(records), "results": results})
    return {
        "scope": "developer_authored_targeted_regressions_not_independent_requests",
        "independent_blind": False, "cases": rows,
        "comparison": {
            "case_count": len(rows),
            "with_decay_passed": sum(row["results"][0]["passed"] for row in rows),
            "without_decay_passed": sum(row["results"][1]["passed"] for row in rows),
            "improved": sum(row["results"][0]["passed"] and not row["results"][1]["passed"] for row in rows),
            "regressed": sum(not row["results"][0]["passed"] and row["results"][1]["passed"] for row in rows),
            "tied": sum(row["results"][0]["passed"] == row["results"][1]["passed"] for row in rows),
        },
    }


def assess_decay_diagnostics(report):
    """Recount diagnostic outcomes instead of trusting an aggregate flag."""
    checks = {}
    comparison = {}
    try:
        rows = report["decay_diagnostics"]["cases"]
        checks["nonempty_distinct_cases"] = bool(rows) and len({row["id"] for row in rows}) == len(rows)
        checks["paired_settings"] = all(
            len(row["results"]) == 2
            and row["results"][0]["half_life_days"] == 30.0
            and row["results"][1]["half_life_days"] is None for row in rows
        )
        outcomes = [
            [result["prediction"] == row["expected"] for result in row["results"]]
            for row in rows
        ]
        checks["flags_match_predictions"] = all(
            result["passed"] is passed
            for row, pair in zip(rows, outcomes) for result, passed in zip(row["results"], pair)
        )
        comparison = {
            "case_count": len(rows),
            "with_decay_passed": sum(pair[0] for pair in outcomes),
            "without_decay_passed": sum(pair[1] for pair in outcomes),
            "improved": sum(pair[0] and not pair[1] for pair in outcomes),
            "regressed": sum(not pair[0] and pair[1] for pair in outcomes),
            "tied": sum(pair[0] == pair[1] for pair in outcomes),
        }
        checks["summary_matches_cases"] = comparison == report["decay_diagnostics"]["comparison"]
        checks["enabled_cases_pass"] = comparison["with_decay_passed"] == len(rows) and bool(rows)
        checks["no_regressions"] = comparison["regressed"] == 0
        checks["honest_scope"] = report["decay_diagnostics"]["independent_blind"] is False
    except (KeyError, TypeError, IndexError):
        checks["valid_diagnostic_rows"] = False
    return {"passed": bool(checks) and all(checks.values()), "checks": checks, "comparison": comparison}


def run_ablations(suite):
    comparisons = []
    for mode in ("lexical", "semantic", "hybrid"):
        config = select_threshold(suite, mode=mode)
        trial = retrieval_trial(suite, "test", config["threshold"], mode=mode,
                                evidence_policy=CALIBRATION_POLICY)
        comparisons.append({"configuration": config, "result": trial})
    threshold = comparisons[-1]["configuration"]["threshold"]
    uncached = retrieval_trial(suite, "test", threshold, cache=False, evidence_policy=CALIBRATION_POLICY)
    raw = []
    for index, (content, timestamp) in enumerate((
        ("偏好：输出保持简洁，直接给结论。", "2025-01-01T00:00:00+00:00"),
        ("用户偏好：今后需要详细说明并给出原因。", "2026-01-01T00:00:00+00:00"),
    )):
        raw.append({"id": f"decay-{index}", "source_type": "manual_config",
                    "content": content, "timestamp": timestamp})
    records = DataIngestionPipeline().ingest(raw)
    decay = []
    for half_life in (30.0, None):
        predicted = {p.key: p.value for p in PreferenceExtractor(half_life_days=half_life).extract(records)}
        decay.append({"half_life_days": half_life, "prediction": predicted.get("output.verbosity"),
                      "expected": "detailed", "passed": predicted.get("output.verbosity") == "detailed"})
    service = MemoryService()
    service.ingest([{
        "id": f"policy-{i}", "source_type": "manual_config", "user_id": "ablation",
        "content": content, "timestamp": "2026-01-01T00:00:00+00:00",
        "metadata": {"title": "移动介质安全流程"},
    } for i, content in enumerate((
        "移动介质安全流程允许使用外部存储设备，完成检查并保存审计记录。",
        "移动介质安全流程禁止使用外部存储设备，完成检查并保存审计记录。",
    ))], persist=False)
    pending = {k for k, v in service.store.knowledge.items() if v.status.value == "conflict_pending"}
    isolation = []
    for include in (False, True):
        results = service.store.search_knowledge("移动介质安全流程", tenant_id="default",
                                                user_id="ablation", include_pending=include)
        isolation.append({"include_pending": include,
                          "pending_returned": len(pending & {r.memory_id for r in results})})
    return {"independent_blind": False, "retrieval_comparisons": comparisons,
            "without_cache": uncached, "decay_probe": decay, "decay_diagnostics": decay_diagnostics(),
            "conflict_isolation_probe": isolation,
            "limitations": ["Single-factor diagnostic probes are not broad effectiveness estimates.",
                            "Both decay settings may pass: report ties without claiming improvement.",
                            "The six new decay cases target known edge conditions; they are not official requests.",
                            "Timing is descriptive; encode-call counts measure cache work directly."]}

"""Developer-held evaluation with dev-only threshold selection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter

from .evaluation import build_store_from_raw_records
from .ingestion import DataIngestionPipeline
from .preference import PreferenceExtractor
from .service import MemoryService


def split_rows(suite, section, split):
    return [row for row in suite.get(section, []) if row["split"] == split]


def retrieval_trial(suite, split, threshold, *, mode="hybrid", cache=True, include_pending=False):
    store = build_store_from_raw_records(split_rows(suite, "records", split))
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
        "positive_recall_at_3": round(positive_recall, 4),
        "no_answer_accuracy": round(empty_accuracy, 4),
        "balanced_score": round((positive_recall + empty_accuracy) / 2, 4),
        "mean_latency_ms": round(sum(row["latency_ms"] for row in rows) / max(len(rows), 1), 4),
        "query_phase_encode_calls": provider.calls,
        "rows": rows,
    }


def select_threshold(suite, *, mode="hybrid"):
    # Does not inspect test records, queries or labels.
    trials = [retrieval_trial(suite, "dev", value / 100, mode=mode) for value in range(8, 81, 4)]
    best = max(trials, key=lambda row: (row["balanced_score"], row["positive_recall_at_3"], row["threshold"]))
    dev = {section: split_rows(suite, section, "dev") for section in ("records", "retrieval_queries")}
    digest = hashlib.sha256(json.dumps(dev, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {
        "selected_on": "dev", "mode": mode, "threshold": best["threshold"],
        "dev_sha256": digest, "selection": "balanced positive recall and no-answer accuracy",
        "trials": [{k: v for k, v in trial.items() if k not in {"rows", "mean_latency_ms"}} for trial in trials],
    }


def evaluate_frozen(suite):
    config = select_threshold(suite)
    return {
        "dataset": suite["name"], "independent_blind": False, "configuration": config,
        "test": retrieval_trial(suite, "test", config["threshold"]),
        "limitations": suite.get("limitations", []),
    }


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_ablations(suite):
    comparisons = []
    for mode in ("lexical", "semantic", "hybrid"):
        config = select_threshold(suite, mode=mode)
        trial = retrieval_trial(suite, "test", config["threshold"], mode=mode)
        comparisons.append({"configuration": config, "result": trial})
    threshold = comparisons[-1]["configuration"]["threshold"]
    uncached = retrieval_trial(suite, "test", threshold, cache=False)
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
            "without_cache": uncached, "decay_probe": decay, "conflict_isolation_probe": isolation,
            "limitations": ["Single-factor diagnostic probes are not broad effectiveness estimates.",
                            "Both decay settings may pass: report ties without claiming improvement.",
                            "Timing is descriptive; encode-call counts measure cache work directly."]}

"""Frozen, visible-label stress tests with distractors and request-level failures."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
from time import perf_counter

from .benchmark import _percentile
from .provider_config import provider_identity
from .resources import resource_snapshot, resource_usage
from .schemas import KnowledgeMemory, MemoryStatus
from .service import MemoryService
from .memory_store import MemoryStore, _normalize_search_text
from .retrieval_evidence import MIN_COVERAGE, POLICIES

FROZEN_SHA256 = "04b9a5266535e40a4542ae4647a4bba51aabf8edc32bd3a169713a4c4c1f2212"
CONFIGURATION = {"top_k": 3, "min_score": .265, "dimensions": 256, "ngram": 2}
SUITE_PATH = Path("data/eval/complex_retrieval_v1.json")
CONSTRAINT_SUITE_PATH = Path("data/eval/complex_constraints_v1.json")
CONSTRAINT_SHA256 = "9f03254a21bd93d24e217f470524f55569776ce46a263fc4e53ddb48d44cb5fc"
SUITES = {
    "complex_retrieval_v1": (SUITE_PATH, FROZEN_SHA256),
    "complex_constraints_v1": (CONSTRAINT_SUITE_PATH, CONSTRAINT_SHA256),
}
MODES = ("lexical", "semantic", "hybrid")


def _time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def visible(document, query, now):
    return (
        document["status"] == "active"
        and document["tenant_id"] == query["tenant_id"]
        and document["user_id"] in {query["user_id"], "*"}
        and document["scene"] in {query["scene"], "default", "global"}
        and (not document.get("valid_from") or _time(document["valid_from"]) <= now)
        and (not document.get("valid_to") or now < _time(document["valid_to"]))
    )


def validate_suite(suite, *, now=None):
    now = now or datetime.now(timezone.utc)
    if suite.get("schema_version") != 1 or suite.get("configuration") != CONFIGURATION:
        raise ValueError("unexpected complex suite schema or frozen configuration")
    if not _time(suite["clock_window"]["start"]) <= now < _time(suite["clock_window"]["end"]):
        raise ValueError("suite clock window expired; create a new version instead of changing fixtures")
    documents, queries = suite["documents"], suite["queries"]
    for rows in (documents, queries):
        if not rows or len({row["id"] for row in rows}) != len(rows):
            raise ValueError("empty or duplicate complex IDs")
    fingerprints = [
        (row["query"], row["tenant_id"], row["user_id"], row["scene"]) for row in queries
    ]
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("duplicate complex request input")
    by_id = {row["id"]: row for row in documents}
    for row in documents:
        if row.get("valid_to") and _time(row["valid_to"]) <= _time(row["valid_from"]):
            raise ValueError("document validity interval is inverted")
    for row in queries:
        expected = row["expected"]
        if (row["kind"] not in {"positive", "no_answer", "scope"}
                or bool(expected) != (row["kind"] == "positive")
                or len(set(expected)) != len(expected) or len(expected) > CONFIGURATION["top_k"]
                or not set(expected) <= by_id.keys()
                or not row["query"].strip()):
            raise ValueError("invalid complex relevance labels")
        if not all(visible(by_id[key], row, now) for key in expected):
            raise ValueError("positive label is not visible in its requested scope")
        if "required_terms" in row:
            constraints = MemoryStore._evidence_constraints(row["required_terms"])
            text = _normalize_search_text(row["query"]).lower()
            if not constraints or not all(pattern.search(text) for _term, pattern in constraints):
                raise ValueError("explicit constraints must be present in the request, not derived from labels")
    return suite


def make_corpus(suite, size, hard_fraction):
    if type(size) is not int or size < len(suite["documents"]):
        raise ValueError("size must include every labeled and fixed distractor document")
    if type(hard_fraction) not in (int, float) or not math.isfinite(hard_fraction) or not 0 <= hard_fraction <= 1:
        raise ValueError("hard_fraction must be finite and between zero and one")
    documents = [dict(row) for row in suite["documents"]]
    count = size - len(documents)
    hard_count = math.floor(count * hard_fraction)
    topics = suite["filler_topics"]
    easy_topics = (
        "园区花坛养护记录", "公开食堂菜谱汇总", "大厅休息区家具清单", "文化展板更新登记",
        "运动场照明检查", "公用雨具借还登记", "公共饮水机维护表", "庭院标识牌清洁记录",
        "周末开放时间通知", "公开阅读角书目", "空闲活动室物资表", "大厅植物换盆计划",
    )
    for index in range(count):
        # Spread both classes throughout the corpus instead of grouping by insertion order.
        hard = ((index + 1) * hard_count // count > index * hard_count // count) if count else False
        topic = topics[index % len(topics)]
        entity = f"{topic['secondary']}分组{index:05d}"
        title = entity + "操作说明" if hard else easy_topics[index % len(easy_topics)] + f" {index:05d}"
        if hard:
            content = topic["content"].replace(topic["secondary"], entity)
            content += f" 本条仅适用于{entity}，批次{index:05d}，适用范围与其他业务区分。"
            if index % 7 == 0:
                content += ("交接记录包括办理时间、终端状态、复核意见和下一班处理人。"
                            "处理期间其他窗口的提示只用于参考，不构成本条业务的授权。") * 3
        else:
            content = f"{title}：本次巡检登记数量{index % 53 + 1}，整理公开说明，交由值班人员签收。"
        documents.append({
            "id": f"filler-{index:05d}", "title": title, "content": content,
            "tenant_id": "complex-eval", "user_id": "operator", "scene": "default",
            "status": "active", "authority": .65 + (index % 4) * .1,
            "valid_from": "2026-01-01T00:00:00+00:00", "valid_to": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
            "tags": ["procedure" if hard else "public-notice"], "role": "hard-filler" if hard else "easy-filler",
        })
    digest = hashlib.sha256(json.dumps(documents, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return documents, {
        "records": len(documents), "fixed_documents": len(suite["documents"]), "generated_fillers": count,
        "requested_hard_fraction_of_fillers": hard_fraction, "hard_fillers": hard_count,
        "actual_hard_fraction_of_fillers": hard_count / count if count else 0.0,
        "roles": dict(sorted(Counter(row["role"] for row in documents).items())), "sha256": digest,
    }


def make_service(documents):
    service = MemoryService()
    for row in documents:
        service.store.knowledge[row["id"]] = KnowledgeMemory(
            **{key: value for key, value in row.items() if key not in {"role", "status"}},
            source_ids=[row["id"]], version=1, status=MemoryStatus(row["status"]),
        )
    service.store.rebuild_index()
    return service


def score_request(query, returned, *, elapsed_ms, invalid_ids=(), error_type=None):
    expected = set(query["expected"])
    identifiers = [row["memory_id"] for row in returned]
    duplicate = len(set(identifiers)) != len(identifiers)
    if duplicate and error_type is None:
        error_type = "DuplicateResult"
    matched = expected.intersection(identifiers) if not error_type else set()
    recall = len(matched) / len(expected) if expected else None
    ranks = [rank for rank, key in enumerate(identifiers, 1) if key in matched]
    dcg = sum(1 / math.log2(rank + 1) for rank in ranks)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(expected), 3) + 1))
    return {
        "id": query["id"], "scenario": query["scenario"], "category": query["category"],
        "kind": query["kind"], "query": query["query"], "expected": query["expected"],
        "returned": identifiers, "scores": [row["score"] for row in returned],
        "elapsed_ms": elapsed_ms, "error_type": error_type, "invalid_ids": list(invalid_ids),
        "recall_at_3": recall, "precision_at_3": len(matched) / 3 if expected else None,
        "mrr_at_3": 1 / ranks[0] if ranks else 0.0,
        "ndcg_at_3": dcg / ideal if ideal else None,
        "irrelevant_returned": len(identifiers) - len(matched) if expected else None,
        "passed": not error_type and not invalid_ids and (matched == expected if expected else not identifiers),
    }


def summarize_rows(rows):
    positives = [row for row in rows if row["kind"] == "positive"]
    negatives = [row for row in rows if row["kind"] == "no_answer"]
    scoped = [row for row in rows if row["kind"] == "scope"]
    latencies = [row["elapsed_ms"] for row in rows]
    returned = sum(len(row["returned"]) for row in positives)
    irrelevant = sum(row["irrelevant_returned"] for row in positives)
    errors = sum(row["error_type"] is not None for row in rows)
    def mean(key):
        return sum(row[key] for row in positives) / len(positives) if positives else None
    return {
        "requests": len(rows), "positive_requests": len(positives), "no_answer_requests": len(negatives),
        "scope_requests": len(scoped), "errors": errors,
        "macro_recall_at_3": mean("recall_at_3"), "precision_at_3": mean("precision_at_3"),
        "mrr_at_3": mean("mrr_at_3"), "ndcg_at_3": mean("ndcg_at_3"),
        "full_evidence_correct": sum(row["passed"] for row in positives),
        "full_evidence_accuracy": sum(row["passed"] for row in positives) / len(positives) if positives else None,
        "no_answer_correct": sum(row["passed"] for row in negatives),
        "no_answer_accuracy": sum(row["passed"] for row in negatives) / len(negatives) if negatives else None,
        "false_answers": sum(bool(row["returned"]) for row in negatives),
        "false_answer_rate": sum(bool(row["returned"]) for row in negatives) / len(negatives) if negatives else None,
        "irrelevant_returned": irrelevant, "positive_results_returned": returned,
        "distractor_return_rate": irrelevant / returned if returned else 0.0,
        "scope_empty_correct": sum(row["passed"] for row in scoped),
        "leak_requests": sum(bool(row["invalid_ids"]) for row in rows),
        "leaked_records": sum(len(row["invalid_ids"]) for row in rows),
        "p50_ms": _percentile(latencies, .5), "p95_ms": _percentile(latencies, .95),
        "p99_ms": _percentile(latencies, .99), "max_ms": max(latencies, default=0.0),
        "latency_valid": bool(rows) and errors == 0,
        "failed_ids": [row["id"] for row in rows if not row["passed"]],
    }


def grouped_summaries(rows):
    return {
        field: {value: summarize_rows([row for row in rows if row[field] == value])
                for value in sorted({row[field] for row in rows})}
        for field in ("kind", "scenario")
    }


def run_profile(suite, *, size, hard_fraction, mode, rounds, use_constraints=False,
                evidence_policy="similarity"):
    if (mode not in MODES or type(rounds) is not int or rounds <= 0
            or type(use_constraints) is not bool or evidence_policy not in POLICIES):
        raise ValueError("invalid retrieval mode or repetition count")
    resources_before = resource_snapshot()
    started = perf_counter()
    documents, corpus = make_corpus(suite, size, hard_fraction)
    by_id = {row["id"]: row for row in documents}
    service = make_service(documents)
    build_ms = (perf_counter() - started) * 1000
    measurements = []
    for repeat in range(rounds):
        rows = []
        for query in suite["queries"]:
            now = datetime.now(timezone.utc)
            started = perf_counter()
            returned, error = [], None
            try:
                returned = service.search(
                    query["query"], tenant_id=query["tenant_id"], user_id=query["user_id"],
                    scene=query["scene"], top_k=3, min_score=.265, retrieval_mode=mode,
                    required_terms=query.get("required_terms") if use_constraints else None,
                    evidence_policy=evidence_policy,
                )
            except Exception as exc:
                error = type(exc).__name__
            elapsed_ms = (perf_counter() - started) * 1000
            invalid = [row["memory_id"] for row in returned
                       if row["memory_id"] not in by_id or not visible(by_id[row["memory_id"]], query, now)]
            rows.append(score_request(query, returned, elapsed_ms=elapsed_ms, invalid_ids=invalid, error_type=error))
        categories = {category: summarize_rows([row for row in rows if row["category"] == category])
                      for category in sorted({row["category"] for row in rows})}
        measurements.append({
            "round": repeat + 1, "phase": "first_pass_no_query_warmup" if repeat == 0 else "subsequent_pass",
            "first_query_ms": rows[0]["elapsed_ms"], "summary": summarize_rows(rows),
            "categories": categories, "groups": grouped_summaries(rows), "rows": rows,
        })
    quality = all(row["summary"]["macro_recall_at_3"] >= .85 and row["summary"]["no_answer_accuracy"] >= .85
                  for row in measurements)
    safety = all(row["summary"]["leaked_records"] == 0 and row["summary"]["errors"] == 0 for row in measurements)
    latency = all(row["summary"]["latency_valid"] and row["summary"]["p95_ms"] <= 500 for row in measurements)
    result = {
        "corpus": corpus, "mode": mode, "configuration": CONFIGURATION,
        "provider": provider_identity(service.store.embedding), "build_ms": build_ms, "rounds": measurements,
        "resources": resource_usage(resources_before, resource_snapshot()),
        "quality_targets_met": quality, "safety_passed": safety, "latency_target_met": latency,
        "all_targets_met": quality and safety and latency,
        "evidence_policy": evidence_policy,
        "minimum_evidence_coverage": MIN_COVERAGE if evidence_policy != "similarity" else None,
    }
    if any("required_terms" in query for query in suite["queries"]):
        result["required_terms_enabled"] = use_constraints
    return result


def run_complex_evaluation(root, *, sizes=(1000, 10000), hard_fractions=(0.0, .75),
                           rounds=3, modes=("hybrid",), progress=None,
                           suite_name="complex_retrieval_v1", constraint_modes=(False,),
                           evidence_policies=("similarity",)):
    root = Path(root)
    suite_path, suite_sha256 = SUITES[suite_name]
    if (not constraint_modes or any(type(value) is not bool for value in constraint_modes)
            or (suite_name == "complex_retrieval_v1" and tuple(constraint_modes) != (False,))):
        raise ValueError("constraint modes must be explicit and cannot change the original frozen suite")
    payload = (root / suite_path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != suite_sha256:
        raise ValueError("complex dataset bytes differ from the frozen version")
    suite = validate_suite(json.loads(payload))
    source_snapshot = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in sorted((root / "src").rglob("*.py"))}
    profiles = []
    if not evidence_policies or any(value not in POLICIES for value in evidence_policies):
        raise ValueError("unknown or empty evidence policies")
    combinations = [(size, fraction, mode, constrained, policy)
                    for size in sizes for fraction in hard_fractions for mode in modes
                    for constrained in constraint_modes for policy in evidence_policies]
    if not combinations or len(set(combinations)) != len(combinations):
        raise ValueError("empty or duplicate evaluation profiles")
    for size, fraction, mode, constrained, policy in combinations:
        if progress:
            progress(f"start size={size} hard_fraction={fraction} mode={mode} "
                     f"constraints={constrained} evidence_policy={policy}")
        profiles.append(run_profile(suite, size=size, hard_fraction=fraction, mode=mode,
                                    rounds=rounds, use_constraints=constrained, evidence_policy=policy))
        if progress:
            summary = profiles[-1]["rounds"][0]["summary"]
            progress(f"done recall={summary['macro_recall_at_3']:.4f} "
                     f"no_answer={summary['no_answer_accuracy']:.4f} p95_ms={summary['p95_ms']:.3f}")
    evaluator_files = (suite_path, Path("src/os_agent_memory/complex_retrieval.py"),
                       Path("scripts/evaluate_complex_retrieval.py"))
    unchanged = source_snapshot == {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / "src").rglob("*.py"))
    }
    return {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "public_complex_retrieval_regression_not_official_acceptance",
        "dataset": {"path": suite_path.as_posix(), "sha256": suite_sha256,
                    "documents": len(suite["documents"]), "distinct_requests": len(suite["queries"]),
                    "kinds": dict(Counter(row["kind"] for row in suite["queries"]))},
        "environment": {
            "system": platform.system(), "release": platform.release(), "machine": platform.machine(),
            "python": platform.python_version(), "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(), "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
            "host_fingerprint": hashlib.sha256(platform.node().encode()).hexdigest(),
        },
        "source_sha256": source_snapshot, "source_unchanged_during_run": unchanged,
        "evaluator_sha256": {path.as_posix(): hashlib.sha256((root / path).read_bytes()).hexdigest()
                            for path in evaluator_files},
        "method": {
            "boundary": "MemoryService.search: lock, query encoding, retrieval, reranking, serialization; no HTTP/Agent",
            "filler_fraction_denominator": "generated fillers only; fixed difficult documents always present",
            "percentile": "nearest_rank", "rounds": rounds, "query_order": "frozen file order, no query warmup",
            "repetition_is_independent_sample": False, "controlled_snapshot_bypasses_ingestion": True,
            "quality_thresholds": {"macro_recall_at_3": .85, "no_answer_accuracy": .85, "p95_ms": 500},
            "evidence_policies": list(evidence_policies),
            **({"constraint_modes": list(constraint_modes),
                "constraint_source": "explicit input terms; never generated from relevance labels"}
               if suite_name != "complex_retrieval_v1" else {}),
        },
        "profiles": profiles, "quality_targets_met": all(row["quality_targets_met"] for row in profiles),
        "safety_passed": all(row["safety_passed"] for row in profiles),
        "latency_target_met": all(row["latency_target_met"] for row in profiles),
        "all_targets_met": unchanged and all(row["all_targets_met"] for row in profiles),
        "competition_ready": False, "independent_blind": False,
        "limitations": suite["limitations"] + [
            "HashEmbedding only; not native SDK performance or a new V11 verification.",
            "Fixed .265 across local ablations is diagnostic, not a separately optimized threshold for each mode.",
            "RSS is current process; high-water mark covers process lifetime and excludes external model servers.",
            "Optional content_coverage_v1 is lexical abstention, not entailment; it can reject supported paraphrases.",
        ],
    }

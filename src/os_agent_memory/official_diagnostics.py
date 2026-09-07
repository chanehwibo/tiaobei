"""Map honest internal evidence to the official rubric, retaining sample gaps."""
from __future__ import annotations
import hashlib
import json
import platform
from time import perf_counter
from .benchmark import _benchmark_memory, _percentile
from .evaluation import run_evaluation_suite, precision_recall_f1, load_evaluation_suite
from .experiments import evaluate_frozen
from .memory_store import MemoryStore
from .official_contract import assess_official_metrics
from .security import SensitiveFilter


def sensitive_diagnostic(suite):
    rows = suite["cases"]
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("empty or duplicate sensitive case ids")
    fingerprints = [json.dumps(row["value"], sort_keys=True, ensure_ascii=False) for row in rows]
    if len(set(fingerprints)) != len(rows):
        raise ValueError("duplicate sensitive requests")
    tp = fp = fn = tn = 0
    details = []
    for row in rows:
        if type(row["sensitive"]) is not bool:
            raise ValueError("sensitive labels must be boolean")
        _, hits = SensitiveFilter().redact_structure(row["value"])
        actual, expected = bool(hits), row["sensitive"]
        tp += actual and expected
        fp += actual and not expected
        fn += not actual and expected
        tn += not actual and not expected
        details.append({"id": row["id"], "expected": expected, "actual": actual, "passed": actual == expected})
    scores = precision_recall_f1(tp, fp, fn)
    return {"requests": len(rows), "positive": tp + fn, "negative": fp + tn,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn, **scores, "rows": details,
        "definition": "request-level sensitive classification; NOT entity/span-level F1"}


def diverse_latency(*, size=1000, requests=50):
    if requests < 50 or requests > 97 or size < requests:
        raise ValueError("use 50..97 distinct topic queries and at least that many records")
    store = MemoryStore()
    for index in range(size):
        memory = _benchmark_memory(index)
        store.knowledge[memory.id] = memory
    store.rebuild_index()
    rows = []
    for index in range(requests):
        query = f"专项主题 topic{index:03d} 办公审批流程"
        start = perf_counter()
        hits = store.search_knowledge(query, tenant_id="benchmark", user_id="benchmark-user", top_k=5)
        rows.append({"id": f"latency-{index:03d}", "query": query,
            "elapsed_ms": (perf_counter() - start) * 1000, "results": len(hits)})
    elapsed = [row["elapsed_ms"] for row in rows]
    return {"records": size, "requests": requests, "unique_queries": len({row["query"] for row in rows}),
        "p95_ms": _percentile(elapsed, .95), "p99_ms": _percentile(elapsed, .99),
        "cold_first_ms": elapsed[0], "rows": rows, "provider": "HashEmbedding",
        "system": platform.system(), "machine": platform.machine(), "python": platform.python_version(),
        "method": f"nearest-rank P95; {requests} distinct topic IDs, one query per topic after index build; no warmup",
        "limitations": "single synthetic template; varied query IDs do not establish task diversity; in-process not HTTP/SDK latency"}


def run_official_diagnostics(root, *, size=1000):
    data = root / "data/eval"
    old_path = data / "office_memory_eval_v2.json"
    old = run_evaluation_suite(old_path, split="test")
    old_suite = load_evaluation_suite(old_path, split="test")
    frozen = evaluate_frozen(json.loads((data / "office_memory_eval_v3.json").read_text(encoding="utf-8")))
    sensitive_path = data / "sensitive_official_diagnostic.json"
    sensitive = sensitive_diagnostic(json.loads(sensitive_path.read_text(encoding="utf-8")))
    latency = diverse_latency(size=size)
    metrics = {"preference_accuracy": old["metrics"]["preference_accuracy"],
        "knowledge_recall": frozen["test"]["positive_recall_at_3"],
        "conflict_accuracy": old["metrics"]["conflict_accuracy"],
        "retrieval_p95_ms": latency["p95_ms"], "sensitive_f1": sensitive["f1"]}
    counts = {"preference_accuracy": len(old_suite["preference_labels"]),
        "knowledge_recall": frozen["test"]["positive_queries"],
        "conflict_accuracy": len(old_suite["conflict_cases"]),
        "retrieval_p95_ms": latency["requests"], "sensitive_f1": sensitive["requests"]}
    return {"scope": "internal_development_diagnostics_not_official_validation", "metrics": metrics,
        "observation_counts": counts,
        "count_units": {"preference_accuracy": "labeled slots, NOT independent requests",
                        "knowledge_recall": "positive queries", "conflict_accuracy": "conflict case pairs",
                        "retrieval_p95_ms": "distinct synthetic topic queries", "sensitive_f1": "public synthetic requests"},
        "rubric_diagnostic": assess_official_metrics(metrics, counts),
        "official_validation_ready": False, "independent_blind": False,
        "latency": latency, "sensitive": sensitive,
        "dataset_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (old_path, data / "office_memory_eval_v3.json", sensitive_path)},
        "sources": {"preference_accuracy": "unchanged v2 test labels, through real lifecycle gate",
                    "knowledge_recall": "v3 test Recall@3, dev-only threshold selection",
                    "conflict_accuracy": "v2 test detection plus labeled resolution assertions"},
        "gaps": ["Preference accuracy below 85%; do not weaken lifecycle gates to conceal this.",
            "Preference/retrieval/conflict sets lack 50 independent requests each.",
            "Sensitive F1 is request-level, not a certified official definition.",
            "Public synthetic labels with HashEmbedding; no real SDK/model end-to-end evidence."]}

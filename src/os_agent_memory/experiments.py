"""Developer-held evaluation with dev-only threshold selection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter

from .evaluation import build_store_from_raw_records


def split_rows(suite, section, split):
    return [row for row in suite.get(section, []) if row["split"] == split]


def retrieval_trial(suite, split, threshold, *, mode="hybrid", cache=True, include_pending=False):
    store = build_store_from_raw_records(split_rows(suite, "records", split))
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

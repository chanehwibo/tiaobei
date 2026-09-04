from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .ingestion import DataIngestionPipeline
from .knowledge import KnowledgeExtractor
from .memory_store import MemoryStore
from .preference import PreferenceExtractor
from .schemas import KnowledgeMemory, MemoryStatus, PreferenceMemory, stable_id, utc_now


def precision_recall_f1(true_positive: int, false_positive: int, false_negative: int) -> dict[str, float]:
    """Return safe micro precision/recall/F1 values for count inputs."""

    if min(true_positive, false_positive, false_negative) < 0:
        raise ValueError("metric counts cannot be negative")
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    precision = true_positive / precision_denominator if precision_denominator else 1.0
    recall = true_positive / recall_denominator if recall_denominator else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def preference_accuracy(predicted: list[PreferenceMemory], labels: dict[tuple[str, str], str]) -> float:
    if not labels:
        return 0.0
    current = {(item.user_id, item.key): item.value for item in predicted}
    correct = sum(1 for key, expected_value in labels.items() if current.get(key) == expected_value)
    unexpected = len(set(current) - set(labels))
    return correct / (len(labels) + unexpected)


def recall_at_k(search_fn: Callable[[str, int], list[str]], queries: dict[str, set[str]], k: int = 5) -> float:
    if not queries:
        return 0.0
    total = 0.0
    for query, expected_ids in queries.items():
        returned_ids = set(search_fn(query, k))
        total += len(returned_ids & expected_ids) / len(expected_ids)
    return total / len(queries)


def measure_latency_ms(fn: Callable[[], object], rounds: int = 20) -> float:
    if rounds <= 0:
        raise ValueError("rounds must be positive")
    start = time.perf_counter()
    for _ in range(rounds):
        fn()
    elapsed = time.perf_counter() - start
    return elapsed * 1000 / rounds


def run_smoke_evaluation(store: MemoryStore) -> dict[str, float]:
    latency = measure_latency_ms(lambda: store.search_knowledge("报销流程模板", top_k=3), rounds=10)
    return {
        "knowledge_search_latency_ms": round(latency, 3),
        "knowledge_count": float(store.stats()["knowledge"]),
        "knowledge_conflicts": float(store.stats()["knowledge_conflicts"]),
    }


def load_evaluation_suite(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        suite = json.load(file)
    if not isinstance(suite.get("records"), list):
        raise ValueError("evaluation suite must contain a records list")
    return suite


def build_store_from_raw_records(raw_records: list[dict[str, Any]]) -> MemoryStore:
    ingestion = DataIngestionPipeline()
    records = ingestion.ingest(raw_records)

    store = MemoryStore()
    for memory in PreferenceExtractor().extract(records):
        store.upsert_preference(memory)
    for memory in KnowledgeExtractor().extract(records):
        result = store.upsert_knowledge(memory)
        if result.status == MemoryStatus.CONFLICT_PENDING:
            store.resolve_knowledge_conflict(result.id, strategy="auto")
    return store


def run_evaluation_suite(path: str | Path, top_k: int = 3) -> dict[str, Any]:
    suite_path = Path(path)
    suite = load_evaluation_suite(suite_path)
    raw_records = suite["records"]
    store = build_store_from_raw_records(raw_records)

    preference_labels = {
        (str(item["user_id"]), str(item["key"])): str(item["value"])
        for item in suite.get("preference_labels", [])
    }
    retrieval_queries = suite.get("retrieval_queries", [])
    conflict_cases = suite.get("conflict_cases", [])
    forget_cases = suite.get("forget_cases", [])

    preference_scores = _preference_scores(list(store.preferences.values()), preference_labels)
    retrieval_details = _knowledge_retrieval_details(store, retrieval_queries, top_k)
    retrieval_scores = _retrieval_scores(retrieval_details)
    conflict_details = _conflict_details(conflict_cases)
    conflict_scores = _conflict_scores(conflict_details)
    forget_details = _forget_details(raw_records, forget_cases)
    forget_scores = _forget_scores(forget_details)
    metrics = {
        "preference_accuracy": round(preference_accuracy(list(store.preferences.values()), preference_labels), 4),
        "preference_precision": round(preference_scores["precision"], 4),
        "preference_recall": round(preference_scores["recall"], 4),
        "preference_f1": round(preference_scores["f1"], 4),
        "knowledge_precision_at_k": round(retrieval_scores["precision"], 4),
        "knowledge_recall_at_k": round(retrieval_scores["recall"], 4),
        "knowledge_mrr": round(retrieval_scores["mrr"], 4),
        "knowledge_ndcg_at_k": round(retrieval_scores["ndcg"], 4),
        "knowledge_search_latency_ms": round(
            measure_latency_ms(lambda: store.search_knowledge("报销流程模板", top_k=top_k), rounds=20),
            3,
        ),
        "conflict_accuracy": round(_conflict_accuracy(conflict_cases), 4),
        "conflict_precision": round(conflict_scores["precision"], 4),
        "conflict_recall": round(conflict_scores["recall"], 4),
        "conflict_f1": round(conflict_scores["f1"], 4),
        "forget_accuracy": round(_forget_accuracy(raw_records, forget_cases), 4),
        "forget_precision": round(forget_scores["precision"], 4),
        "forget_recall": round(forget_scores["recall"], 4),
        "forget_f1": round(forget_scores["f1"], 4),
        "forget_misdelete_rate": round(forget_scores["misdelete_rate"], 4),
    }
    details = {
        "preferences": _preference_details(list(store.preferences.values()), preference_labels),
        "retrieval": retrieval_details,
        "conflicts": conflict_details,
        "forget": forget_details,
    }
    stats = store.stats()
    return {
        "suite": suite.get("name", suite_path.stem),
        "top_k": top_k,
        "metrics": metrics,
        "counts": {
            "records": len(raw_records),
            "preferences": stats["preferences"],
            "preference_versions": stats["preference_versions"],
            "knowledge": stats["knowledge"],
            "knowledge_conflicts": stats["knowledge_conflicts"],
        },
        "details": details,
        "targets": _target_status(metrics, suite.get("targets", {})),
    }


def _knowledge_recall_at_k(store: MemoryStore, queries: list[dict[str, Any]], top_k: int) -> float:
    if not queries:
        return 0.0

    return sum(item["recall"] for item in _knowledge_retrieval_details(store, queries, top_k)) / len(queries)


def _preference_scores(
    predicted: list[PreferenceMemory],
    labels: dict[tuple[str, str], str],
) -> dict[str, float]:
    predicted_set = {(item.user_id, item.key, item.value) for item in predicted}
    label_set = {(user_id, key, value) for (user_id, key), value in labels.items()}
    true_positive = len(predicted_set & label_set)
    return precision_recall_f1(
        true_positive,
        len(predicted_set - label_set),
        len(label_set - predicted_set),
    )


def _preference_details(
    predicted: list[PreferenceMemory],
    labels: dict[tuple[str, str], str],
) -> list[dict[str, Any]]:
    current = {(item.user_id, item.key): item for item in predicted}
    details: list[dict[str, Any]] = []
    for user_id, key in sorted(labels):
        memory = current.get((user_id, key))
        expected_value = labels[(user_id, key)]
        predicted_value = memory.value if memory else None
        details.append(
            {
                "user_id": user_id,
                "key": key,
                "expected_value": expected_value,
                "predicted_value": predicted_value,
                "confidence": memory.confidence if memory else None,
                "version": memory.version if memory else None,
                "scenes": memory.scenes if memory else [],
                "evidence_ids": memory.evidence_ids if memory else [],
                "passed": predicted_value == expected_value,
            }
        )
    for user_id, key in sorted(set(current) - set(labels)):
        memory = current[(user_id, key)]
        details.append(
            {
                "user_id": user_id,
                "key": key,
                "expected_value": None,
                "predicted_value": memory.value,
                "confidence": memory.confidence,
                "version": memory.version,
                "scenes": memory.scenes,
                "evidence_ids": memory.evidence_ids,
                "unexpected_prediction": True,
                "passed": False,
            }
        )
    return details


def _knowledge_retrieval_details(store: MemoryStore, queries: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for item in queries:
        expected_titles = [str(title) for title in item.get("expected_titles", [])]
        returned_titles = [
            result.title
            for result in store.search_knowledge(
                str(item["query"]),
                top_k=top_k,
                min_score=float(item.get("min_score", 0.08)),
            )
        ]
        hit_titles = sorted(set(returned_titles) & set(expected_titles))
        expected_empty = bool(item.get("expected_empty", not expected_titles))
        recall = (
            (1.0 if not returned_titles else 0.0)
            if expected_empty
            else len(hit_titles) / len(expected_titles)
        )
        details.append(
            {
                "query": str(item["query"]),
                "expected_titles": expected_titles,
                "returned_titles": returned_titles,
                "hit_titles": hit_titles,
                "expected_empty": expected_empty,
                "precision": round(
                    (1.0 if not returned_titles else 0.0)
                    if expected_empty
                    else len(hit_titles) / len(returned_titles) if returned_titles else 0.0,
                    4,
                ),
                "recall": round(recall, 4),
                "reciprocal_rank": round(_reciprocal_rank(returned_titles, expected_titles, expected_empty), 4),
                "ndcg": round(_ndcg(returned_titles, expected_titles, expected_empty), 4),
                "passed": recall >= 1.0,
            }
        )
    return details


def _reciprocal_rank(returned: list[str], expected: list[str], expected_empty: bool) -> float:
    if expected_empty:
        return 1.0 if not returned else 0.0
    expected_set = set(expected)
    for rank, title in enumerate(returned, start=1):
        if title in expected_set:
            return 1.0 / rank
    return 0.0


def _ndcg(returned: list[str], expected: list[str], expected_empty: bool) -> float:
    if expected_empty:
        return 1.0 if not returned else 0.0
    expected_set = set(expected)
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, title in enumerate(returned, start=1)
        if title in expected_set
    )
    ideal_hits = min(len(expected_set), len(returned))
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def _retrieval_scores(details: list[dict[str, Any]]) -> dict[str, float]:
    if not details:
        return {"precision": 0.0, "recall": 0.0, "mrr": 0.0, "ndcg": 0.0}
    count = len(details)
    return {
        "precision": sum(float(item["precision"]) for item in details) / count,
        "recall": sum(float(item["recall"]) for item in details) / count,
        "mrr": sum(float(item["reciprocal_rank"]) for item in details) / count,
        "ndcg": sum(float(item["ndcg"]) for item in details) / count,
    }


def _conflict_accuracy(cases: list[dict[str, Any]]) -> float:
    if not cases:
        return 0.0

    return sum(1 for item in _conflict_details(cases) if item["passed"]) / len(cases)


def _conflict_details(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for case in cases:
        store = MemoryStore()
        base = _knowledge_from_case(case["base"], stable_id("conflict", str(case.get("id")), "base"))
        incoming = _knowledge_from_case(case["incoming"], stable_id("conflict", str(case.get("id")), "incoming"))
        store.upsert_knowledge(base)
        result = store.upsert_knowledge(incoming)
        is_conflict = result.status == MemoryStatus.CONFLICT_PENDING and bool(result.conflict_with)
        conflict_with_count = len(result.conflict_with)
        expected_conflict = bool(case.get("expected_conflict", False))
        case_correct = is_conflict == expected_conflict

        resolved_status: str | None = None
        base_status = store.knowledge[base.id].status.value
        incoming_status = result.status.value
        resolved_content = result.content
        if case_correct and case.get("resolution_strategy"):
            resolved = store.resolve_knowledge_conflict(result.id, str(case["resolution_strategy"]))
            base_status = store.knowledge[base.id].status.value
            incoming_status = resolved.status.value
            resolved_status = resolved.status.value
            resolved_content = resolved.content
            expected_base_status = case.get("expected_base_status")
            expected_incoming_status = case.get("expected_incoming_status")
            if expected_base_status is not None:
                case_correct = base_status == str(expected_base_status)
            if case_correct and expected_incoming_status is not None:
                case_correct = incoming_status == str(expected_incoming_status)
            if case_correct and case.get("expected_content_contains"):
                case_correct = all(str(text) in resolved_content for text in case["expected_content_contains"])

        details.append(
            {
                "id": str(case.get("id", "")),
                "expected_conflict": expected_conflict,
                "actual_conflict": is_conflict,
                "conflict_with_count": conflict_with_count,
                "resolution_strategy": case.get("resolution_strategy"),
                "base_status": base_status,
                "incoming_status": incoming_status,
                "resolved_status": resolved_status,
                "resolved_content": resolved_content,
                "passed": case_correct,
            }
        )
    return details


def _conflict_scores(details: list[dict[str, Any]]) -> dict[str, float]:
    true_positive = sum(
        1 for item in details if item["expected_conflict"] and item["actual_conflict"]
    )
    false_positive = sum(
        1 for item in details if not item["expected_conflict"] and item["actual_conflict"]
    )
    false_negative = sum(
        1 for item in details if item["expected_conflict"] and not item["actual_conflict"]
    )
    return precision_recall_f1(true_positive, false_positive, false_negative)


def _forget_accuracy(raw_records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> float:
    if not cases:
        return 0.0

    return sum(1 for item in _forget_details(raw_records, cases) if item["passed"]) / len(cases)


def _forget_details(raw_records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for case in cases:
        store = build_store_from_raw_records(raw_records)
        result = store.forget(
            str(case["instruction"]),
            user_id=case.get("user_id"),
            tenant_id=case.get("tenant_id"),
        )
        status_by_title = {memory.title: memory.status for memory in store.knowledge.values()}
        title_by_id = {memory.id: memory.title for memory in store.knowledge.values()}

        expected_forgotten = [str(title) for title in case.get("expected_forgotten_titles", [])]
        expected_retained = [str(title) for title in case.get("expected_retained_titles", [])]
        # Only score memories changed by this operation. Conflict resolution may
        # already have retired older knowledge before the forget request starts.
        actual_forgotten = sorted(
            title_by_id[memory_id]
            for memory_id in result.affected_knowledge_ids
            if memory_id in title_by_id
        )
        missed_forgotten = [
            title for title in expected_forgotten if status_by_title.get(title) != MemoryStatus.FORGOTTEN
        ]
        explicitly_wrong = [
            title for title in expected_retained if status_by_title.get(title) == MemoryStatus.FORGOTTEN
        ]
        unexpected_forgotten = sorted(set(actual_forgotten) - set(expected_forgotten))
        wrongly_forgotten = sorted(set(explicitly_wrong) | set(unexpected_forgotten))
        details.append(
            {
                "instruction": str(case["instruction"]),
                "matched_keywords": result.matched_keywords,
                "expected_forgotten_titles": expected_forgotten,
                "expected_retained_titles": expected_retained,
                "actual_forgotten_titles": actual_forgotten,
                "missed_forgotten_titles": missed_forgotten,
                "unexpected_forgotten_titles": unexpected_forgotten,
                "wrongly_forgotten_titles": wrongly_forgotten,
                "passed": not missed_forgotten and not wrongly_forgotten,
            }
        )
    return details


def _forget_scores(details: list[dict[str, Any]]) -> dict[str, float]:
    true_positive = sum(
        len(set(item["actual_forgotten_titles"]) & set(item["expected_forgotten_titles"]))
        for item in details
    )
    false_positive = sum(len(item["unexpected_forgotten_titles"]) for item in details)
    false_negative = sum(len(item["missed_forgotten_titles"]) for item in details)
    scores = precision_recall_f1(true_positive, false_positive, false_negative)
    deletion_count = true_positive + false_positive
    scores["misdelete_rate"] = false_positive / deletion_count if deletion_count else 0.0
    return scores


def _knowledge_from_case(item: dict[str, Any], memory_id: str) -> KnowledgeMemory:
    timestamp = str(item.get("valid_from") or utc_now())
    return KnowledgeMemory(
        id=memory_id,
        title=str(item["title"]),
        content=str(item["content"]),
        tags=[str(tag) for tag in item.get("tags", ["general"])],
        source_ids=[memory_id],
        version=1,
        created_at=timestamp,
        updated_at=timestamp,
        authority=float(item.get("authority", 0.5)),
        valid_from=timestamp,
    )


def _target_status(metrics: dict[str, float], targets: dict[str, Any]) -> dict[str, bool]:
    status: dict[str, bool] = {}
    for metric_name, target in targets.items():
        if metric_name not in metrics or not isinstance(target, dict):
            continue
        value = metrics[metric_name]
        if "min" in target:
            status[metric_name] = value >= float(target["min"])
        elif "max" in target:
            status[metric_name] = value <= float(target["max"])
    return status

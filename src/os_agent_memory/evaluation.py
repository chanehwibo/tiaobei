from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .ingestion import DataIngestionPipeline
from .knowledge import KnowledgeExtractor
from .memory_store import MemoryStore
from .preference import PreferenceExtractor
from .schemas import KnowledgeMemory, MemoryStatus, PreferenceMemory, stable_id, utc_now


def preference_accuracy(predicted: list[PreferenceMemory], labels: dict[tuple[str, str], str]) -> float:
    if not labels:
        return 0.0
    correct = 0
    current = {(item.user_id, item.key): item.value for item in predicted}
    for key, expected_value in labels.items():
        if current.get(key) == expected_value:
            correct += 1
    return correct / len(labels)


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

    metrics = {
        "preference_accuracy": round(preference_accuracy(list(store.preferences.values()), preference_labels), 4),
        "knowledge_recall_at_k": round(_knowledge_recall_at_k(store, retrieval_queries, top_k), 4),
        "knowledge_search_latency_ms": round(
            measure_latency_ms(lambda: store.search_knowledge("报销流程模板", top_k=top_k), rounds=20),
            3,
        ),
        "conflict_accuracy": round(_conflict_accuracy(conflict_cases), 4),
        "forget_accuracy": round(_forget_accuracy(raw_records, forget_cases), 4),
    }
    details = {
        "preferences": _preference_details(list(store.preferences.values()), preference_labels),
        "retrieval": _knowledge_retrieval_details(store, retrieval_queries, top_k),
        "conflicts": _conflict_details(conflict_cases),
        "forget": _forget_details(raw_records, forget_cases),
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
    return details


def _knowledge_retrieval_details(store: MemoryStore, queries: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for item in queries:
        expected_titles = [str(title) for title in item.get("expected_titles", [])]
        returned_titles = [result.title for result in store.search_knowledge(str(item["query"]), top_k=top_k)]
        hit_titles = sorted(set(returned_titles) & set(expected_titles))
        recall = len(hit_titles) / len(expected_titles) if expected_titles else 0.0
        details.append(
            {
                "query": str(item["query"]),
                "expected_titles": expected_titles,
                "returned_titles": returned_titles,
                "hit_titles": hit_titles,
                "recall": round(recall, 4),
                "passed": recall >= 1.0,
            }
        )
    return details


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


def _forget_accuracy(raw_records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> float:
    if not cases:
        return 0.0

    return sum(1 for item in _forget_details(raw_records, cases) if item["passed"]) / len(cases)


def _forget_details(raw_records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for case in cases:
        store = build_store_from_raw_records(raw_records)
        result = store.forget(str(case["instruction"]), user_id=case.get("user_id"))
        status_by_title = {memory.title: memory.status for memory in store.knowledge.values()}

        expected_forgotten = [str(title) for title in case.get("expected_forgotten_titles", [])]
        expected_retained = [str(title) for title in case.get("expected_retained_titles", [])]
        actual_forgotten = sorted(title for title, status in status_by_title.items() if status == MemoryStatus.FORGOTTEN)
        missed_forgotten = [
            title for title in expected_forgotten if status_by_title.get(title) != MemoryStatus.FORGOTTEN
        ]
        wrongly_forgotten = [
            title for title in expected_retained if status_by_title.get(title) == MemoryStatus.FORGOTTEN
        ]
        details.append(
            {
                "instruction": str(case["instruction"]),
                "matched_keywords": result.matched_keywords,
                "expected_forgotten_titles": expected_forgotten,
                "expected_retained_titles": expected_retained,
                "actual_forgotten_titles": actual_forgotten,
                "missed_forgotten_titles": missed_forgotten,
                "wrongly_forgotten_titles": wrongly_forgotten,
                "passed": not missed_forgotten and not wrongly_forgotten,
            }
        )
    return details


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

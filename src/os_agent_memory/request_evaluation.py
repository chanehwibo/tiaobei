"""Request-level public regression; extraction is distinct from durable consent."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from time import perf_counter

from .benchmark import _benchmark_memory, _percentile
from .evaluation import precision_recall_f1
from .ingestion import DataIngestionPipeline
from .memory_store import MemoryStore
from .official_contract import assess_official_metrics
from .preference import PreferenceExtractor
from .provider_config import provider_identity
from .schemas import KnowledgeMemory, MemoryStatus
from .security import SensitiveFilter
from .service import MemoryService

TENANT, USER = "request-eval", "request-user"
STAMP = "2026-09-01T00:00:00+00:00"


def validate_suite(suite):
    if suite.get("schema_version") != 1:
        raise ValueError("unsupported request suite")
    for section in ("preferences", "documents", "queries", "conflicts", "sensitive"):
        rows = suite.get(section, [])
        ids = [row["id"] for row in rows]
        if not rows or len(set(ids)) != len(ids):
            raise ValueError("empty or duplicate IDs in " + section)
        if section == "preferences":
            payloads = [row["records"] for row in rows]
        elif section == "queries":
            payloads = [{"query": row["query"], "tenant_id": row.get("tenant_id", TENANT),
                         "user_id": row.get("user_id", USER)} for row in rows]
        elif section == "sensitive":
            payloads = [row["text"] for row in rows]
        elif section == "documents":
            payloads = [row["content"] for row in rows]
        else:
            payloads = [{k: row[k] for k in ("base", "incoming")} for row in rows]
        fingerprints = [json.dumps(value, sort_keys=True, ensure_ascii=False) for value in payloads]
        if len(set(fingerprints)) != len(fingerprints):
            raise ValueError("duplicate request content in " + section)
    documents = {row["id"] for row in suite["documents"]}
    for row in suite["queries"]:
        if not set(row["expected"]).issubset(documents):
            raise ValueError("unknown relevance label")
    for row in suite["sensitive"]:
        for entity in row["entities"]:
            if not entity["value"] or entity["value"] not in row["text"]:
                raise ValueError("entity label is absent from input")
    return suite


def evaluate_preferences(rows):
    details = []
    tp = fp = fn = 0
    for row in rows:
        records = [{"tenant_id": TENANT, "user_id": USER, "id": f"{row['id']}-{i}", **raw}
                   for i, raw in enumerate(row["records"])]
        normalized = DataIngestionPipeline().ingest_with_report(records)
        predictions = PreferenceExtractor().extract(normalized.records)
        actual = {p.key: p.value for p in predictions}
        expected = row["expected"]
        predicted_set, label_set = set(actual.items()), set(expected.items())
        tp += len(predicted_set & label_set)
        fp += len(predicted_set - label_set)
        fn += len(label_set - predicted_set)
        result = {"id": row["id"], "category": row["category"], "expected": expected, "actual": actual,
                  "passed": actual == expected and not normalized.issues}
        if "durable_expected" in row:
            service = MemoryService()
            for raw in records:
                service.ingest([raw])
            durable = {p["key"]: p["value"] for p in service.preferences(tenant_id=TENANT, user_id=USER)}
            result.update(durable_actual=durable, durable_expected=row["durable_expected"],
                          durable_passed=durable == row["durable_expected"])
        details.append(result)
    return {"requests": len(rows), "correct": sum(row["passed"] for row in details),
            "accuracy": sum(row["passed"] for row in details) / len(rows),
            "slot_scores": precision_recall_f1(tp, fp, fn),
            "durable_checks_passed": all(row.get("durable_passed", True) for row in details),
            "definition": "exact per-request key/value set match, extra or missing slots fail; normalized extraction, not permission to persist",
            "rows": details}


def evaluate_retrieval(suite, *, size, embedding_config=None):
    if size < len(suite["documents"]):
        raise ValueError("retrieval corpus size is smaller than labeled documents")
    service = MemoryService(embedding_config=embedding_config)
    records = [{"id": row["id"], "source_type": "imported_document", "authority": .95,
                "tenant_id": TENANT, "user_id": USER, "scene": row["category"],
                "timestamp": STAMP, "content": row["content"],
                "metadata": {"title": row["title"]}} for row in suite["documents"]]
    result = service.ingest(records)
    id_by_memory = {memory.id: memory.source_ids[0] for memory in service.store.knowledge.values()}
    stored_ids = {source_id for memory in service.store.knowledge.values() for source_id in memory.source_ids}
    missing = sorted(row["id"] for row in suite["documents"] if row["id"] not in stored_ids)
    ingestion = {"expected_documents": len(records), "accepted_records": result["accepted_records"],
                 "knowledge_records": len(service.store.knowledge), "missing_document_ids": missing,
                 "issues": result["issues"], "promotion_decisions": result["promotion_decisions"],
                 "passed": result["accepted_records"] == len(records) and not missing and not result["issues"]}
    # Missing labeled documents remain misses; filler only maintains the measured corpus size.
    for index in range(size - len(service.store.knowledge)):
        memory = _benchmark_memory(index)
        memory.tenant_id, memory.user_id = TENANT, USER
        service.store.knowledge[memory.id] = memory
    service.store.rebuild_index()
    details = []
    for row in suite["queries"]:
        start = perf_counter()
        results = service.search(row["query"], tenant_id=row.get("tenant_id", TENANT),
                                 user_id=row.get("user_id", USER), top_k=3)
        elapsed_ms = (perf_counter() - start) * 1000
        returned = [id_by_memory.get(item["memory_id"], "distractor:" + item["memory_id"]) for item in results]
        expected = set(row["expected"])
        recall = len(expected.intersection(returned)) / len(expected) if expected else None
        details.append({"id": row["id"], "category": row["category"], "query": row["query"],
                        "expected": sorted(expected), "returned": returned, "recall_at_3": recall,
                        "passed": recall == 1 if expected else not returned, "elapsed_ms": elapsed_ms})
    positive = [row for row in details if row["expected"]]
    negative = [row for row in details if not row["expected"] and row["category"] != "scope"]
    scoped = [row for row in details if row["category"] == "scope"]
    return {"records": len(service.store.knowledge), "top_k": 3, "requests": len(details), "positive_requests": len(positive),
            "positive_recall_at_3": sum(row["recall_at_3"] for row in positive) / len(positive),
            "ingestion": ingestion,
            "no_answer_requests": len(negative),
            "no_answer_accuracy": sum(row["passed"] for row in negative) / len(negative) if negative else 0,
            "scope_requests": len(scoped), "scope_leaks": sum(not row["passed"] for row in scoped),
            "p95_ms": _percentile([row["elapsed_ms"] for row in details], .95),
            "p99_ms": _percentile([row["elapsed_ms"] for row in details], .99),
            "cold_first_ms": details[0]["elapsed_ms"],
            "provider": provider_identity(service.store.embedding), "threshold": MemoryStore.DEFAULT_MIN_SCORE,
            "method": "production MemoryService.search including lock and serialization; 60 positive topics, 12 no-answer and 8 scope requests; no per-query thresholds or warmup; nearest-rank percentile",
            "limitations": "synthetic distractors; in-process service, not HTTP/network or Agent reasoning time",
            "rows": details}


def _knowledge(raw, memory_id):
    return KnowledgeMemory(id=memory_id, title=raw["title"], content=raw["content"], tags=["policy"],
                           source_ids=[memory_id], version=1, created_at=STAMP, updated_at=STAMP,
                           tenant_id=raw.get("tenant_id", TENANT), user_id=raw.get("user_id", USER),
                           scene=raw.get("scene", "default"), authority=raw.get("authority", .75),
                           valid_from=raw.get("valid_from", STAMP))


def evaluate_conflicts(rows):
    details = []
    for row in rows:
        service = MemoryService()
        base = service.store.upsert_knowledge(_knowledge(row["base"], "base"))
        incoming = service.store.upsert_knowledge(_knowledge(row["incoming"], "incoming"))
        detected = incoming.status == MemoryStatus.CONFLICT_PENDING and bool(incoming.conflict_with)
        if detected:
            service.resolve_conflict(incoming.id, tenant_id=incoming.tenant_id, user_id=incoming.user_id)
        passed = (detected == row["expected_conflict"]
                  and base.status.value == row["expected_base_status"]
                  and incoming.status.value == row["expected_incoming_status"])
        details.append({"id": row["id"], "category": row["category"], "expected_conflict": row["expected_conflict"],
                        "actual_conflict": detected, "base_status": base.status.value,
                        "incoming_status": incoming.status.value, "passed": passed})
    return {"requests": len(rows), "correct": sum(row["passed"] for row in details),
            "accuracy": sum(row["passed"] for row in details) / len(rows),
            "definition": "independent stores; detection AND authority/recency/manual-queue outcome must match",
            "rows": details}


def evaluate_sensitive(rows):
    tp = fp = fn = 0
    details = []
    for row in rows:
        redacted, hits = SensitiveFilter().redact(row["text"])
        actual = Counter((hit.kind, hit.value) for hit in hits)
        expected = Counter((item["kind"], item["value"]) for item in row["entities"])
        correct = sum((actual & expected).values())
        extra, missed = sum((actual - expected).values()), sum((expected - actual).values())
        tp += correct
        fp += extra
        fn += missed
        leaked = any(item["value"] in redacted for item in row["entities"])
        details.append({"id": row["id"], "tp": correct, "fp": extra, "fn": missed,
                        "redaction_leak": leaked, "passed": not extra and not missed and not leaked})
    return {"requests": len(rows), "tp": tp, "fp": fp, "fn": fn, **precision_recall_f1(tp, fp, fn),
            "redaction_leaks": sum(row["redaction_leak"] for row in details), "rows": details,
            "definition": "micro entity-type + exact-value occurrence multiset; duplicate/overlapping detections penalized; not third-party span certification"}


def run_request_evaluation(root: Path, *, size=10000, suite_path=None, embedding_config=None):
    suite_path = Path(suite_path) if suite_path else root / "data/eval/request_regression_v1.json"
    payload = suite_path.read_bytes()
    suite = validate_suite(json.loads(payload))
    preference = evaluate_preferences(suite["preferences"])
    retrieval = evaluate_retrieval(suite, size=size, embedding_config=embedding_config)
    conflict = evaluate_conflicts(suite["conflicts"])
    sensitive = evaluate_sensitive(suite["sensitive"])
    metrics = {"preference_accuracy": preference["accuracy"], "knowledge_recall": retrieval["positive_recall_at_3"],
               "conflict_accuracy": conflict["accuracy"], "retrieval_p95_ms": retrieval["p95_ms"],
               "sensitive_f1": sensitive["f1"]}
    counts = {"preference_accuracy": preference["requests"], "knowledge_recall": retrieval["positive_requests"],
              "conflict_accuracy": conflict["requests"], "retrieval_p95_ms": retrieval["requests"],
              "sensitive_f1": sensitive["requests"]}
    rubric = assess_official_metrics(metrics, counts)
    safety = {"durable_preferences": preference["durable_checks_passed"],
              "knowledge_ingestion": retrieval["ingestion"]["passed"],
              "no_scope_leaks": retrieval["scope_leaks"] == 0,
              "no_answer_85": retrieval["no_answer_accuracy"] >= .85, "no_redaction_leaks": sensitive["redaction_leaks"] == 0}
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "scope": "public_request_regression_not_independent_blind_or_official_certification",
            "environment": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(),
                            "python": platform.python_version(), "embedding_provider": retrieval["provider"]},
            "dataset": {"name": suite["name"], "sha256": hashlib.sha256(payload).hexdigest(),
                        "provenance": suite["provenance"]},
            "source_sha256": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((root / "src").rglob("*.py"))},
            "metrics": metrics, "observation_counts": counts, "rubric_diagnostic": rubric, "safety_checks": safety,
            "all_targets_met": rubric["all_targets_met"] and all(safety.values()),
            "official_validation_ready": False, "independent_blind": False,
            "preference": preference, "retrieval": retrieval, "conflict": conflict, "sensitive": sensitive}

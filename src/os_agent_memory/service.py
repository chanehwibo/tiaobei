from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from copy import deepcopy
from functools import wraps
from threading import RLock

from .ingestion import DataIngestionPipeline
from .knowledge import KnowledgeExtractor
from .memory_store import MemoryStore
from .persistence import SQLiteMemoryPersistence
from .preference import PreferenceExtractor
from .lifecycle import MemoryLifecycleManager
from .schemas import DataRecord, SourceType, ToolStatus, ForgetPlan, IngestionIssue, stable_id
from .provider_config import create_provider, provider_identity
from .demo import DEMO_TENANT, DEMO_USER, scenario_records


def to_primitive(value: Any) -> Any:
    """Convert service results into JSON-safe primitives."""

    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return to_primitive(asdict(value))
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_primitive(item) for item in value]
    return value


def synchronized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


def atomic_mutation(method):
    """Serialize state transitions and restore all mutable state on failure."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            state = deepcopy({k: v for k, v in vars(self.store).items() if k != "embedding"})
            lifecycle = deepcopy({k: v for k, v in vars(self.lifecycle).items() if k != "store"})
            ingestion = deepcopy(self.ingestion)
            seen, receipts = deepcopy((self._seen_events, self._forget_results))
            try:
                return method(self, *args, **kwargs)
            except Exception:
                provider = self.store.embedding
                vars(self.store).clear()
                vars(self.store).update(state, embedding=provider)
                vars(self.lifecycle).clear()
                vars(self.lifecycle).update(lifecycle, store=self.store)
                self.ingestion = ingestion
                self._seen_events, self._forget_results = seen, receipts
                raise
    return wrapped


class MemoryService:
    """Stable application boundary for memory management clients."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        database_path: str | Path | None = None,
        embedding_config=None,
    ) -> None:
        self._lock = RLock()
        self.persistence = SQLiteMemoryPersistence(database_path) if database_path else None
        if store is not None:
            self.store = store
        elif self.persistence is not None:
            self.store = self.persistence.load(embedding=create_provider(embedding_config))
        else:
            self.store = MemoryStore(embedding=create_provider(embedding_config))
        self.ingestion = DataIngestionPipeline()
        self.preference_extractor = PreferenceExtractor()
        self.knowledge_extractor = KnowledgeExtractor()
        self.lifecycle = MemoryLifecycleManager(self.store)
        state = self.store.runtime_state
        self._seen_events = dict(state.get("seen_events", {}))
        self._forget_results = dict(state.get("forget_results", {}))
        for raw in state.get("lifecycle_records", []):
            record = DataRecord(**{**raw, "source_type": SourceType(raw["source_type"]),
                                  "tool_status": ToolStatus(raw["tool_status"])})
            self.lifecycle.short_term.add(record)
            self.lifecycle.medium_term.add(record)
        self.lifecycle.short_term.expire()
        self.store.pending_forget_plans = {
            raw["id"]: ForgetPlan(**raw) for raw in state.get("pending_plans", [])
        }

    @atomic_mutation
    def ingest(self, raw_records: Iterable[dict[str, Any]], *, persist: bool = True) -> dict[str, Any]:
        batch = self.ingestion.ingest_with_report(raw_records)
        fresh = []
        fingerprints = set(self._seen_events.values())
        for record in batch.records:
            key = stable_id(record.tenant_id, record.user_id, record.id)
            fingerprint = stable_id(record.tenant_id, record.user_id, record.scene,
                                    record.source_type.value, record.timestamp, record.content)
            if key in self._seen_events or fingerprint in fingerprints:
                if key in self._seen_events and self._seen_events[key] != fingerprint:
                    batch.issues.append(IngestionIssue(index=0, record_id=record.id, reason="event_id_conflict"))
                else:
                    batch.duplicate_count += 1
                continue
            self._seen_events[key] = fingerprint
            fingerprints.add(fingerprint)
            fresh.append(record)
        batch.records = fresh
        decisions = self.lifecycle.process(batch.records)
        evidence_ids = {record.id for record in batch.records}
        preferences = [item for item in self.store.preferences.values()
                       if evidence_ids.intersection(item.evidence_ids)]
        knowledge = [item for item in self.store.knowledge.values()
                     if evidence_ids.intersection(item.source_ids)]
        self._save_if_requested(persist)
        return to_primitive(
            {
                "accepted_records": len(batch.records),
                "rejected_records": len(batch.issues),
                "duplicate_records": batch.duplicate_count,
                "issues": batch.issues,
                "preferences": preferences,
                "knowledge": knowledge,
                "promotion_decisions": decisions,
                "stats": self.store.stats(),
            }
        )

    @synchronized
    def preferences(self, *, tenant_id: str, user_id: str, scene: str | None = None) -> list[dict[str, Any]]:
        return to_primitive(self.store.list_preferences(tenant_id, user_id, scene=scene))

    @synchronized
    def search(
        self,
        query: str,
        *,
        tenant_id: str,
        user_id: str,
        scene: str | None = None,
        top_k: int = 5,
        min_score: float = MemoryStore.DEFAULT_MIN_SCORE,
        include_pending: bool = False,
        retrieval_mode: str = "hybrid",
        required_terms: list[str] | tuple[str, ...] | None = None,
        evidence_policy: str = "similarity",
    ) -> list[dict[str, Any]]:
        results = self.store.search_knowledge(
            query,
            top_k=top_k,
            tenant_id=tenant_id,
            user_id=user_id,
            scene=scene,
            min_score=min_score,
            include_pending=include_pending,
            retrieval_mode=retrieval_mode,
            required_terms=required_terms,
            evidence_policy=evidence_policy,
        )
        return to_primitive(results)

    @synchronized
    def conflicts(self, *, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        pending = [
            memory
            for memory in self.store.knowledge.values()
            if memory.tenant_id == tenant_id
            and memory.user_id == user_id
            and memory.status.value == "conflict_pending"
        ]
        return to_primitive(sorted(pending, key=lambda item: (item.updated_at, item.id), reverse=True))

    @atomic_mutation
    def resolve_conflict(
        self,
        memory_id: str,
        *,
        tenant_id: str,
        user_id: str,
        strategy: str = "auto",
        persist: bool = True,
    ) -> dict[str, Any]:
        memory = self.store.knowledge.get(memory_id)
        self._check_owner(memory, tenant_id, user_id)
        resolved = self.store.resolve_knowledge_conflict(memory_id, strategy=strategy)
        self._save_if_requested(persist)
        return to_primitive(resolved)

    @synchronized
    def forget_preview(
        self,
        instruction: str,
        *,
        tenant_id: str,
        user_id: str,
        hard_delete: bool = False,
        ttl_seconds: int = 300,
    ) -> dict[str, Any]:
        plan = self.store.plan_forget(
            instruction,
            tenant_id=tenant_id,
            user_id=user_id,
            hard_delete=hard_delete,
            ttl_seconds=ttl_seconds,
        )
        return to_primitive(plan)

    @atomic_mutation
    def forget_confirm(self, plan_id: str, *, tenant_id: str, user_id: str, persist: bool = True) -> dict[str, Any]:
        self._check_owner(self.store.pending_forget_plans.get(plan_id), tenant_id, user_id)
        if plan_id in self._forget_results:
            return deepcopy(self._forget_results[plan_id])
        plan = self.store.pending_forget_plans.get(plan_id)
        if plan is None:
            raise KeyError("forget plan not found")
        sources = {source for key in plan.knowledge_ids if key in self.store.knowledge
                   for source in self.store.knowledge[key].source_ids}
        sources.update(source for item in self.store.preferences.values() if item.id in plan.preference_ids
                       for source in item.evidence_ids)
        result = self.store.confirm_forget(plan_id)
        for key, records in list(self.lifecycle.medium_term._records.items()):
            remaining = [r for r in records if not (
                r.tenant_id == plan.tenant_id and r.user_id == plan.user_id and r.id in sources)]
            if remaining:
                self.lifecycle.medium_term._records[key] = remaining
            else:
                del self.lifecycle.medium_term._records[key]
        for key, entry in list(self.lifecycle.short_term._entries.items()):
            if entry.record.tenant_id == plan.tenant_id and entry.record.user_id == plan.user_id and entry.record.id in sources:
                del self.lifecycle.short_term._entries[key]
        self._forget_results[plan_id] = to_primitive(result)
        self._save_if_requested(persist)
        return to_primitive(result)

    @synchronized
    def stats(self) -> dict[str, Any]:
        return {
            **self.store.stats(),
            "pending_forget_plans": sum(
                1 for plan in self.store.pending_forget_plans.values() if not plan.confirmed
            ),
            "audit_events": len(self.store.audit_events),
            "conflict_decisions": len(self.store.conflict_decisions),
        }

    @staticmethod
    def _check_owner(target, tenant_id, user_id):
        if (not isinstance(tenant_id, str) or not tenant_id.strip()
                or not isinstance(user_id, str) or not user_id.strip()):
            raise ValueError("tenant_id and user_id must be non-empty strings")
        if target is None or (target.tenant_id, target.user_id) != (tenant_id, user_id):
            raise PermissionError("target is unavailable in this scope")

    @synchronized
    def overview(self, *, tenant_id: str, user_id: str):
        def owned(item):
            return (item.tenant_id, item.user_id) == (tenant_id, user_id)
        knowledge = [to_primitive(item) for item in self.store.knowledge.values() if owned(item)]
        for item in knowledge:
            item.pop("embedding", None)
        return {
            "knowledge": knowledge,
            "preferences": self.preferences(tenant_id=tenant_id, user_id=user_id),
            "history": to_primitive([item for item in self.store.preference_history if owned(item)]),
            "medium": to_primitive(self.lifecycle.medium_term.clusters(tenant_id=tenant_id, user_id=user_id)),
        }

    @atomic_mutation
    def demo_scenario(self, name, *, reset=False):
        if reset:
            # This reserved namespace contains synthetic, disposable demonstration data only.
            for key, item in list(self.store.knowledge.items()):
                if item.tenant_id == DEMO_TENANT:
                    self.store._remove_knowledge_index(key)
                    del self.store.knowledge[key]
            self.store.preferences = {k: v for k, v in self.store.preferences.items() if v.tenant_id != DEMO_TENANT}
            self.store.preference_history = [v for v in self.store.preference_history if v.tenant_id != DEMO_TENANT]
            self.lifecycle.medium_term._records = {k: v for k, v in self.lifecycle.medium_term._records.items()
                                                    if v[0].tenant_id != DEMO_TENANT}
            self.lifecycle.short_term._entries = {k: v for k, v in self.lifecycle.short_term._entries.items()
                                                  if v.record.tenant_id != DEMO_TENANT}
            for scenario in ("baseline", "preference", "conflict"):
                for raw in scenario_records(scenario):
                    self._seen_events.pop(stable_id(DEMO_TENANT, DEMO_USER, raw["id"]), None)
            removed = {k for k, v in self.store.pending_forget_plans.items() if v.tenant_id == DEMO_TENANT}
            self.store.pending_forget_plans = {k: v for k, v in self.store.pending_forget_plans.items() if k not in removed}
            self._forget_results = {k: v for k, v in self._forget_results.items() if k not in removed}
        result = self.ingest(scenario_records(name), persist=False)
        self._save_if_requested(True)
        return {"tenant_id": DEMO_TENANT, "user_id": DEMO_USER, "scene": "office", "result": result}

    @synchronized
    def save(self) -> None:
        if self.persistence is None:
            raise RuntimeError("database_path was not configured")
        self._save_if_requested(True)

    def _save_if_requested(self, persist: bool) -> None:
        self.store.runtime_state = {
            "embedding_identity": provider_identity(self.store.embedding),
            "seen_events": self._seen_events, "forget_results": self._forget_results,
            "lifecycle_records": [to_primitive(record) for records in self.lifecycle.medium_term._records.values()
                                  for record in records],
            "pending_plans": [{**to_primitive(plan), "instruction": ""}
                              for plan in self.store.pending_forget_plans.values()],
        }
        if persist and self.persistence is not None:
            self.persistence.save(self.store)

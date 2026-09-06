from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from .ingestion import DataIngestionPipeline
from .knowledge import KnowledgeExtractor
from .memory_store import MemoryStore
from .persistence import SQLiteMemoryPersistence
from .preference import PreferenceExtractor
from .lifecycle import MemoryLifecycleManager


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


class MemoryService:
    """Stable application boundary for memory management clients."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        database_path: str | Path | None = None,
    ) -> None:
        self.persistence = SQLiteMemoryPersistence(database_path) if database_path else None
        if store is not None:
            self.store = store
        elif self.persistence is not None:
            self.store = self.persistence.load()
        else:
            self.store = MemoryStore()
        self.ingestion = DataIngestionPipeline()
        self.preference_extractor = PreferenceExtractor()
        self.knowledge_extractor = KnowledgeExtractor()
        self.lifecycle = MemoryLifecycleManager(self.store)

    def ingest(self, raw_records: Iterable[dict[str, Any]], *, persist: bool = True) -> dict[str, Any]:
        batch = self.ingestion.ingest_with_report(raw_records)
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

    def preferences(self, *, tenant_id: str, user_id: str, scene: str | None = None) -> list[dict[str, Any]]:
        return to_primitive(self.store.list_preferences(tenant_id, user_id, scene=scene))

    def search(
        self,
        query: str,
        *,
        tenant_id: str,
        user_id: str,
        scene: str | None = None,
        top_k: int = 5,
        min_score: float = 0.08,
        include_pending: bool = False,
    ) -> list[dict[str, Any]]:
        results = self.store.search_knowledge(
            query,
            top_k=top_k,
            tenant_id=tenant_id,
            user_id=user_id,
            scene=scene,
            min_score=min_score,
            include_pending=include_pending,
        )
        return to_primitive(results)

    def conflicts(self, *, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        pending = [
            memory
            for memory in self.store.knowledge.values()
            if memory.tenant_id == tenant_id
            and memory.user_id == user_id
            and memory.status.value == "conflict_pending"
        ]
        return to_primitive(sorted(pending, key=lambda item: (item.updated_at, item.id), reverse=True))

    def resolve_conflict(
        self,
        memory_id: str,
        *,
        strategy: str = "auto",
        persist: bool = True,
    ) -> dict[str, Any]:
        resolved = self.store.resolve_knowledge_conflict(memory_id, strategy=strategy)
        self._save_if_requested(persist)
        return to_primitive(resolved)

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

    def forget_confirm(self, plan_id: str, *, persist: bool = True) -> dict[str, Any]:
        result = self.store.confirm_forget(plan_id)
        self._save_if_requested(persist)
        return to_primitive(result)

    def stats(self) -> dict[str, Any]:
        return {
            **self.store.stats(),
            "pending_forget_plans": sum(
                1 for plan in self.store.pending_forget_plans.values() if not plan.confirmed
            ),
            "audit_events": len(self.store.audit_events),
            "conflict_decisions": len(self.store.conflict_decisions),
        }

    def save(self) -> None:
        if self.persistence is None:
            raise RuntimeError("database_path was not configured")
        self.persistence.save(self.store)

    def _save_if_requested(self, persist: bool) -> None:
        if persist and self.persistence is not None:
            self.persistence.save(self.store)

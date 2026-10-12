from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from statistics import fmean

from .knowledge import KnowledgeExtractor
from .memory_store import MemoryStore
from .preference import PreferenceExtractor
from .schemas import DataRecord, MemoryStatus, MemoryTier, PromotionDecision, stable_id


def _as_datetime(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(slots=True)
class ShortTermEntry:
    record: DataRecord
    expires_at: str


class ShortTermMemoryBuffer:
    """Session-scoped memory buffer with deterministic TTL expiry."""

    def __init__(self, default_ttl_seconds: int = 1800) -> None:
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be positive")
        self.default_ttl_seconds = default_ttl_seconds
        self._entries: dict[tuple[str, str, str], ShortTermEntry] = {}

    def add(self, record: DataRecord) -> ShortTermEntry:
        ttl_seconds = record.ttl_seconds or self.default_ttl_seconds
        expires_at = _as_datetime(record.timestamp) + timedelta(seconds=ttl_seconds)
        entry = ShortTermEntry(record=record, expires_at=expires_at.isoformat(timespec="seconds"))
        self._entries[(record.tenant_id, record.user_id, record.id)] = entry
        return entry

    def active(
        self,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str | None = None,
        now: str | datetime | None = None,
    ) -> list[DataRecord]:
        self.expire(now=now)
        records = [
            entry.record
            for entry in self._entries.values()
            if entry.record.tenant_id == tenant_id
            and entry.record.user_id == user_id
            and (session_id is None or entry.record.session_id == session_id)
        ]
        return sorted(records, key=lambda record: record.timestamp)

    def expire(self, now: str | datetime | None = None) -> list[str]:
        point = _as_datetime(now)
        expired = [
            record_id
            for record_id, entry in self._entries.items()
            if _as_datetime(entry.expires_at) <= point
        ]
        for record_id in expired:
            del self._entries[record_id]
        return sorted(key[2] for key in expired)

    def remove(self, record_id: str, *, tenant_id: str, user_id: str) -> bool:
        return self._entries.pop((tenant_id, user_id, record_id), None) is not None

    def __len__(self) -> int:
        return len(self._entries)


@dataclass(slots=True)
class MediumTermCluster:
    id: str
    tenant_id: str
    user_id: str
    scene: str
    topic: str
    record_ids: list[str]
    occurrence_count: int
    source_types: list[str]
    first_seen: str
    last_seen: str
    average_quality: float
    average_authority: float
    risk_flags: list[str]
    representative_content: str
    promotion_score: float


class MediumTermMemory:
    """Aggregate related events and compute evidence-based promotion scores."""

    def __init__(self) -> None:
        self._records: dict[str, list[DataRecord]] = {}

    def add(self, record: DataRecord) -> MediumTermCluster:
        topic = self._topic(record)
        cluster_id = stable_id("medium", record.tenant_id, record.user_id, record.scene, topic)
        bucket = self._records.setdefault(cluster_id, [])
        if all(existing.id != record.id for existing in bucket):
            bucket.append(record)
            bucket.sort(key=lambda item: item.timestamp)
        return self._build_cluster(cluster_id, bucket)

    def aggregate(self, records: list[DataRecord]) -> list[MediumTermCluster]:
        touched: set[str] = set()
        for record in records:
            cluster = self.add(record)
            touched.add(cluster.id)
        return [self.get(cluster_id) for cluster_id in sorted(touched)]

    def get(self, cluster_id: str) -> MediumTermCluster:
        records = self._records.get(cluster_id)
        if not records:
            raise KeyError(f"medium-term cluster not found: {cluster_id}")
        return self._build_cluster(cluster_id, records)

    def records_for(self, cluster_id: str) -> list[DataRecord]:
        records = self._records.get(cluster_id)
        if not records:
            raise KeyError(f"medium-term cluster not found: {cluster_id}")
        return list(records)

    def clusters(self, *, tenant_id: str, user_id: str) -> list[MediumTermCluster]:
        return sorted(
            (
                self._build_cluster(cluster_id, records)
                for cluster_id, records in self._records.items()
                if records[0].tenant_id == tenant_id and records[0].user_id == user_id
            ),
            key=lambda item: (item.scene, item.topic),
        )

    @staticmethod
    def _topic(record: DataRecord) -> str:
        for key in ("intent", "topic", "title", "event"):
            value = str(record.metadata.get(key, "")).strip()
            if value:
                return value.lower()
        compact = "".join(record.content.lower().split())
        return compact[:32] or "general"

    @staticmethod
    def _promotion_score(records: list[DataRecord]) -> float:
        average_quality = fmean(record.quality_score for record in records)
        average_authority = fmean(record.authority for record in records)
        repetition = min(len(records) / 3.0, 1.0)
        source_diversity = min(len({record.source_type.value for record in records}) / 3.0, 1.0)
        score = (
            0.3 * average_quality
            + 0.3 * average_authority
            + 0.25 * repetition
            + 0.15 * source_diversity
        )
        if any(record.risk_flags for record in records):
            score *= 0.35
        return round(min(score, 1.0), 4)

    def _build_cluster(self, cluster_id: str, records: list[DataRecord]) -> MediumTermCluster:
        representative = max(
            records,
            key=lambda record: (record.authority * record.quality_score, record.timestamp),
        )
        return MediumTermCluster(
            id=cluster_id,
            tenant_id=representative.tenant_id,
            user_id=representative.user_id,
            scene=representative.scene,
            topic=self._topic(representative),
            record_ids=[record.id for record in records],
            occurrence_count=len(records),
            source_types=sorted({record.source_type.value for record in records}),
            first_seen=records[0].timestamp,
            last_seen=records[-1].timestamp,
            average_quality=round(fmean(record.quality_score for record in records), 4),
            average_authority=round(fmean(record.authority for record in records), 4),
            risk_flags=sorted({flag for record in records for flag in record.risk_flags}),
            representative_content=representative.content,
            promotion_score=self._promotion_score(records),
        )


class MemoryLifecycleManager:
    """Connect short, medium and long-term memory with explainable gates."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        promotion_threshold: float = 0.65,
        minimum_evidence: int = 2,
    ) -> None:
        if not 0.0 <= promotion_threshold <= 1.0:
            raise ValueError("promotion_threshold must be between zero and one")
        if minimum_evidence <= 0:
            raise ValueError("minimum_evidence must be positive")
        self.short_term = ShortTermMemoryBuffer()
        self.medium_term = MediumTermMemory()
        self.store = store or MemoryStore()
        self.promotion_threshold = promotion_threshold
        self.minimum_evidence = minimum_evidence
        self.decisions: list[PromotionDecision] = []

    def process(self, records: list[DataRecord]) -> list[PromotionDecision]:
        for record in records:
            self.short_term.add(record)
        clusters = self.medium_term.aggregate(records)
        return [self.promote(cluster.id) for cluster in clusters]

    def evaluate(self, cluster_id: str) -> PromotionDecision:
        cluster = self.medium_term.get(cluster_id)
        reasons = [
            f"promotion_score={cluster.promotion_score:.4f}",
            f"evidence_count={cluster.occurrence_count}",
            f"average_authority={cluster.average_authority:.4f}",
        ]
        accepted = True
        if cluster.risk_flags:
            accepted = False
            reasons.append("rejected:risk_flags=" + ",".join(cluster.risk_flags))
        if cluster.promotion_score < self.promotion_threshold:
            accepted = False
            reasons.append("rejected:score_below_threshold")
        enough_evidence = cluster.occurrence_count >= self.minimum_evidence
        explicit_authority = cluster.average_authority >= 0.9
        if not enough_evidence and not explicit_authority:
            accepted = False
            reasons.append("rejected:insufficient_evidence")
        if accepted:
            reasons.append("accepted:promotion_gate_passed")
        return PromotionDecision(
            record_id=cluster_id,
            from_tier=MemoryTier.MEDIUM,
            to_tier=MemoryTier.LONG if accepted else None,
            score=cluster.promotion_score,
            accepted=accepted,
            reasons=reasons,
        )

    def promote(self, cluster_id: str) -> PromotionDecision:
        decision = self.evaluate(cluster_id)
        if decision.accepted:
            records = self.medium_term.records_for(cluster_id)
            for preference in PreferenceExtractor().extract(records):
                self.store.upsert_preference(replace(preference, tier=MemoryTier.LONG))
            for knowledge in KnowledgeExtractor().extract(records):
                self.store.upsert_knowledge(replace(knowledge, tier=MemoryTier.LONG))
        self.decisions.append(decision)
        return decision

    def expire_long_term(
        self,
        *,
        before: str | datetime,
    ) -> list[str]:
        cutoff = _as_datetime(before)
        expired: list[str] = []
        for key, preference in list(self.store.preferences.items()):
            if preference.status != MemoryStatus.ACTIVE:
                continue
            timestamp = preference.valid_from or preference.updated_at
            if _as_datetime(timestamp) < cutoff:
                expired_memory = replace(
                    preference,
                    status=MemoryStatus.EXPIRED,
                    valid_to=cutoff.isoformat(timespec="seconds"),
                    updated_at=cutoff.isoformat(timespec="seconds"),
                )
                self.store.preferences[key] = expired_memory
                self.store._replace_history_version(expired_memory)
                expired.append(preference.id)
        for knowledge in self.store.knowledge.values():
            if knowledge.status != MemoryStatus.ACTIVE:
                continue
            timestamp = knowledge.valid_from or knowledge.updated_at
            if _as_datetime(timestamp) < cutoff:
                knowledge.status = MemoryStatus.EXPIRED
                knowledge.valid_to = cutoff.isoformat(timespec="seconds")
                knowledge.updated_at = cutoff.isoformat(timespec="seconds")
                expired.append(knowledge.id)
        return sorted(expired)

    def demote_knowledge(self, memory_id: str, reason: str) -> None:
        memory = self.store.knowledge.get(memory_id)
        if memory is None:
            raise KeyError(f"knowledge memory not found: {memory_id}")
        memory.tier = MemoryTier.MEDIUM
        memory.status = MemoryStatus.QUARANTINED
        memory.updated_at = utc_now_iso()
        self.decisions.append(
            PromotionDecision(
                record_id=memory_id,
                from_tier=MemoryTier.LONG,
                to_tier=MemoryTier.MEDIUM,
                score=0.0,
                accepted=False,
                reasons=[f"demoted:{reason}"],
            )
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import fmean

from .schemas import DataRecord, stable_id


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
        self._entries: dict[str, ShortTermEntry] = {}

    def add(self, record: DataRecord) -> ShortTermEntry:
        ttl_seconds = record.ttl_seconds or self.default_ttl_seconds
        expires_at = _as_datetime(record.timestamp) + timedelta(seconds=ttl_seconds)
        entry = ShortTermEntry(record=record, expires_at=expires_at.isoformat(timespec="seconds"))
        self._entries[record.id] = entry
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
        return sorted(expired)

    def remove(self, record_id: str) -> bool:
        return self._entries.pop(record_id, None) is not None

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

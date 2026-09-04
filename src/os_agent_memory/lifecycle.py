from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .schemas import DataRecord


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

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .schemas import DataRecord, SourceType, stable_id, utc_now
from .security import SensitiveFilter


class DataIngestionPipeline:
    """Normalize multi-source OS Agent events into a stable record format."""

    def __init__(self, sensitive_filter: SensitiveFilter | None = None) -> None:
        self.sensitive_filter = sensitive_filter or SensitiveFilter()

    def load_jsonl(self, path: str | Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        with Path(path).open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    records.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON at line {line_number}: {exc}") from exc
        return records

    def ingest(self, raw_records: Iterable[dict[str, Any]]) -> list[DataRecord]:
        normalized: list[DataRecord] = []
        for raw in raw_records:
            record = self.normalize_record(raw)
            if self.validate(record):
                normalized.append(record)
        return normalized

    def normalize_record(self, raw: dict[str, Any]) -> DataRecord:
        source_type = SourceType(raw.get("source_type", SourceType.USER_BEHAVIOR.value))
        user_id = str(raw.get("user_id", "default_user"))
        scene = str(raw.get("scene", "default"))
        content = self.clean_text(str(raw.get("content", "")))
        content, sensitive_hits = self.sensitive_filter.redact(content)
        timestamp = str(raw.get("timestamp") or utc_now())
        metadata = dict(raw.get("metadata") or {})
        if sensitive_hits:
            metadata["sensitive_hits"] = [hit.kind for hit in sensitive_hits]
        record_id = str(raw.get("id") or stable_id(source_type.value, user_id, scene, timestamp, content))
        quality_score = self.quality_score(content, metadata)
        return DataRecord(
            id=record_id,
            source_type=source_type,
            user_id=user_id,
            scene=scene,
            content=content,
            timestamp=timestamp,
            metadata=metadata,
            quality_score=quality_score,
        )

    @staticmethod
    def clean_text(text: str) -> str:
        text = text.replace("\u3000", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def quality_score(content: str, metadata: dict[str, Any]) -> float:
        if not content:
            return 0.0
        score = 0.45
        if len(content) >= 12:
            score += 0.25
        if metadata:
            score += 0.15
        if any(ch in content for ch in "。；;,.，"):
            score += 0.15
        return min(score, 1.0)

    @staticmethod
    def validate(record: DataRecord) -> bool:
        return bool(record.content) and record.quality_score >= 0.45


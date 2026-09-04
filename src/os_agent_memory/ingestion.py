from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .schemas import DataRecord, IngestionBatch, IngestionIssue, SourceType, ToolStatus, stable_id, utc_now
from .security import SensitiveFilter


class DataIngestionPipeline:
    """Normalize multi-source OS Agent events into a stable record format."""

    def __init__(self, sensitive_filter: SensitiveFilter | None = None) -> None:
        self.sensitive_filter = sensitive_filter or SensitiveFilter()
        self.last_batch = IngestionBatch()
        self.last_load_issues: list[IngestionIssue] = []

    def load_jsonl(self, path: str | Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        self.last_load_issues = []
        with Path(path).open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    value = json.loads(stripped)
                    if not isinstance(value, dict):
                        raise ValueError("JSON value is not an object")
                    records.append(value)
                except (json.JSONDecodeError, ValueError) as exc:
                    self.last_load_issues.append(
                        IngestionIssue(index=line_number, reason=f"invalid_json: {exc}")
                    )
        return records

    def ingest(self, raw_records: Iterable[dict[str, Any]]) -> list[DataRecord]:
        return self.ingest_with_report(raw_records).records

    def ingest_with_report(self, raw_records: Iterable[dict[str, Any]]) -> IngestionBatch:
        batch = IngestionBatch(issues=list(self.last_load_issues))
        seen_ids: set[str] = set()
        seen_fingerprints: set[str] = set()
        for index, raw in enumerate(raw_records, start=1):
            try:
                if not isinstance(raw, dict):
                    raise ValueError("record must be an object")
                record = self.normalize_record(raw)
                if not self.validate(record):
                    batch.issues.append(
                        IngestionIssue(index=index, reason="quality_below_threshold", record_id=record.id)
                    )
                    continue
                fingerprint = stable_id(
                    record.tenant_id,
                    record.user_id,
                    record.source_type.value,
                    record.scene,
                    record.timestamp,
                    record.content,
                )
                if record.id in seen_ids or fingerprint in seen_fingerprints:
                    batch.duplicate_count += 1
                    continue
                seen_ids.add(record.id)
                seen_fingerprints.add(fingerprint)
                batch.records.append(record)
            except (TypeError, ValueError) as exc:
                raw_id = raw.get("id") if isinstance(raw, dict) else None
                batch.issues.append(
                    IngestionIssue(index=index, reason=str(exc), record_id=str(raw_id) if raw_id else None)
                )
        self.last_batch = batch
        return batch

    def normalize_record(self, raw: dict[str, Any]) -> DataRecord:
        try:
            source_type = SourceType(raw.get("source_type", SourceType.USER_BEHAVIOR.value))
        except ValueError as exc:
            raise ValueError(f"unsupported_source_type: {raw.get('source_type')!r}") from exc
        user_id = str(raw.get("user_id", "default_user")).strip()
        tenant_id = str(raw.get("tenant_id", "default")).strip()
        scene = str(raw.get("scene", "default")).strip() or "default"
        session_id = str(raw.get("session_id", "")).strip()
        if not user_id or not tenant_id:
            raise ValueError("tenant_id and user_id must be non-empty")
        content = self.clean_text(str(raw.get("content", "")))
        content, sensitive_hits = self.sensitive_filter.redact(content)
        timestamp = self.normalize_timestamp(str(raw.get("timestamp") or utc_now()))
        raw_metadata = raw.get("metadata") or {}
        if not isinstance(raw_metadata, dict):
            raise ValueError("metadata must be an object")
        metadata = dict(raw_metadata)
        if sensitive_hits:
            metadata["sensitive_hits"] = [hit.kind for hit in sensitive_hits]
        tool_status = self.normalize_tool_status(raw.get("tool_status", metadata.get("status")))
        authority = self.normalize_authority(raw.get("authority"), source_type, tool_status)
        privacy_level = str(raw.get("privacy_level", "internal")).strip().lower()
        if privacy_level not in {"public", "internal", "confidential", "restricted"}:
            raise ValueError(f"unsupported_privacy_level: {privacy_level!r}")
        ttl_seconds = raw.get("ttl_seconds")
        if ttl_seconds is not None:
            ttl_seconds = int(ttl_seconds)
            if ttl_seconds <= 0:
                raise ValueError("ttl_seconds must be positive")
        record_id = str(
            raw.get("id")
            or stable_id(source_type.value, tenant_id, user_id, scene, timestamp, content)
        )
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
            tenant_id=tenant_id,
            session_id=session_id,
            tool_status=tool_status,
            authority=authority,
            privacy_level=privacy_level,
            ttl_seconds=ttl_seconds,
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
        score = 0.15
        if len(content) >= 4:
            score += 0.2
        if len(content) >= 12:
            score += 0.25
        if metadata:
            score += 0.2
        if any(ch in content for ch in "。；;,.，"):
            score += 0.2
        return min(score, 1.0)

    @staticmethod
    def validate(record: DataRecord) -> bool:
        return bool(record.content) and record.quality_score >= 0.55

    @staticmethod
    def normalize_timestamp(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid_timestamp: {value!r}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def normalize_tool_status(value: object) -> ToolStatus:
        normalized = str(value or "unknown").strip().lower()
        aliases = {
            "success": ToolStatus.SUCCEEDED,
            "succeeded": ToolStatus.SUCCEEDED,
            "ok": ToolStatus.SUCCEEDED,
            "failed": ToolStatus.FAILED,
            "failure": ToolStatus.FAILED,
            "error": ToolStatus.FAILED,
            "cancelled": ToolStatus.CANCELLED,
            "canceled": ToolStatus.CANCELLED,
        }
        return aliases.get(normalized, ToolStatus.UNKNOWN)

    @staticmethod
    def normalize_authority(
        value: object,
        source_type: SourceType,
        tool_status: ToolStatus,
    ) -> float:
        if value is not None:
            try:
                return max(0.0, min(float(value), 1.0))
            except (TypeError, ValueError) as exc:
                raise ValueError("authority must be numeric") from exc
        defaults = {
            SourceType.MANUAL_CONFIG: 0.95,
            SourceType.TOOL_RESULT: 0.75,
            SourceType.SYSTEM_EVENT: 0.7,
            SourceType.IMPORTED_DOCUMENT: 0.65,
            SourceType.USER_BEHAVIOR: 0.55,
            SourceType.SESSION_CONTEXT: 0.45,
        }
        authority = defaults[source_type]
        if source_type == SourceType.TOOL_RESULT and tool_status in {ToolStatus.FAILED, ToolStatus.CANCELLED}:
            authority = 0.15
        return authority

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any


class SourceType(str, Enum):
    TOOL_RESULT = "tool_result"
    USER_BEHAVIOR = "user_behavior"
    MANUAL_CONFIG = "manual_config"
    SESSION_CONTEXT = "session_context"
    SYSTEM_EVENT = "system_event"
    IMPORTED_DOCUMENT = "imported_document"


class ToolStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class MemoryTier(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    CONFLICT_PENDING = "conflict_pending"
    FORGOTTEN = "forgotten"
    EXPIRED = "expired"
    QUARANTINED = "quarantined"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(*parts: str) -> str:
    text = "::".join(part.strip() for part in parts if part is not None)
    return sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class DataRecord:
    id: str
    source_type: SourceType
    user_id: str
    scene: str
    content: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)
    quality_score: float = 1.0
    tenant_id: str = "default"
    session_id: str = ""
    tool_status: ToolStatus = ToolStatus.UNKNOWN
    authority: float = 0.5
    privacy_level: str = "internal"
    ttl_seconds: int | None = None
    risk_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PreferenceMemory:
    id: str
    user_id: str
    key: str
    value: str
    confidence: float
    version: int
    scenes: list[str]
    evidence_ids: list[str]
    updated_at: str
    status: MemoryStatus = MemoryStatus.ACTIVE
    tenant_id: str = "default"
    valid_from: str = ""
    valid_to: str | None = None
    tier: MemoryTier = MemoryTier.LONG
    score_components: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class KnowledgeMemory:
    id: str
    title: str
    content: str
    tags: list[str]
    source_ids: list[str]
    version: int
    created_at: str
    updated_at: str
    status: MemoryStatus = MemoryStatus.ACTIVE
    conflict_with: list[str] = field(default_factory=list)
    tenant_id: str = "default"
    user_id: str = "default_user"
    knowledge_type: str = "general"
    scene: str = "default"
    authority: float = 0.5
    privacy_level: str = "internal"
    valid_from: str = ""
    valid_to: str | None = None
    tier: MemoryTier = MemoryTier.LONG
    embedding: list[float] = field(default_factory=list, repr=False)


@dataclass(slots=True)
class SearchResult:
    memory_id: str
    score: float
    title: str
    content: str
    tags: list[str]
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    status: MemoryStatus = MemoryStatus.ACTIVE
    character_score: float = 0.0


@dataclass(slots=True)
class ForgetResult:
    preference_count: int
    knowledge_count: int
    matched_keywords: list[str]
    plan_id: str | None = None
    confirmed: bool = False
    affected_preference_ids: list[str] = field(default_factory=list)
    affected_knowledge_ids: list[str] = field(default_factory=list)
    audit_id: str | None = None


@dataclass(slots=True)
class IngestionIssue:
    index: int
    reason: str
    record_id: str | None = None


@dataclass(slots=True)
class IngestionBatch:
    records: list[DataRecord] = field(default_factory=list)
    issues: list[IngestionIssue] = field(default_factory=list)
    duplicate_count: int = 0


@dataclass(slots=True)
class PromotionDecision:
    record_id: str
    from_tier: MemoryTier
    to_tier: MemoryTier | None
    score: float
    accepted: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ForgetPlan:
    id: str
    tenant_id: str
    user_id: str | None
    instruction: str
    matched_keywords: list[str]
    preference_ids: list[str]
    knowledge_ids: list[str]
    created_at: str
    expires_at: str
    hard_delete: bool = False
    confirmed: bool = False


@dataclass(slots=True)
class AuditEvent:
    id: str
    action: str
    tenant_id: str
    user_id: str | None
    target_ids: list[str]
    created_at: str
    details: dict[str, Any] = field(default_factory=dict)

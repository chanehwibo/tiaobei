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


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    CONFLICT_PENDING = "conflict_pending"
    FORGOTTEN = "forgotten"


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


@dataclass(slots=True)
class SearchResult:
    memory_id: str
    score: float
    title: str
    content: str
    tags: list[str]


@dataclass(slots=True)
class ForgetResult:
    preference_count: int
    knowledge_count: int
    matched_keywords: list[str]


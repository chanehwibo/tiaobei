from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SensitiveHit:
    kind: str
    value: str


class SensitiveFilter:
    """Simple local sensitive information detector for the prototype."""

    PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
        ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
        ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[PHONE]"),
        ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[ID_CARD]"),
        ("api_key", re.compile(r"(?i)\b(?:api[_-]?key|token|secret)\s*[:=]\s*[A-Za-z0-9_\-]{8,}"), "[SECRET]"),
    )

    def detect(self, text: str) -> list[SensitiveHit]:
        hits: list[SensitiveHit] = []
        for kind, pattern, _replacement in self.PATTERNS:
            for match in pattern.finditer(text):
                hits.append(SensitiveHit(kind=kind, value=match.group(0)))
        return hits

    def redact(self, text: str) -> tuple[str, list[SensitiveHit]]:
        hits = self.detect(text)
        redacted = text
        for _kind, pattern, replacement in self.PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted, hits


from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SensitiveHit:
    kind: str
    value: str


class SensitiveFilter:
    """Local sensitive-data filter for content and nested metadata."""

    PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
        ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
        ("phone", re.compile(r"(?<![A-Za-z0-9_])1[3-9]\d{9}(?![A-Za-z0-9_])"), "[PHONE]"),
        ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[ID_CARD]"),
        ("bank_card", re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)"), "[BANK_CARD]"),
        (
            "ipv4",
            re.compile(r"(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)"),
            "[IP_ADDRESS]",
        ),
        ("api_key", re.compile(r"(?i)(?<![A-Za-z0-9_])(?:api[_-]?key|token|secret)\s*[:=]\s*[A-Za-z0-9_.~+/@=-]{8,}"), "[SECRET]"),
        ("bearer_token", re.compile(r"(?i)(?<![A-Za-z0-9_])bearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer [SECRET]"),
        ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
                                    r"(?:[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----)?"), "[PRIVATE_KEY_BLOCK]"),
    )
    SECRET_KEYS = {
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "token",
        "secret",
        "password",
        "authorization",
        "cookie",
    }
    RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "prompt_injection",
            re.compile(
                r"(?i)(ignore\s+(all\s+)?previous|override\s+(system|developer)|"
                r"忽略.{0,8}(之前|以上|系统).{0,8}(指令|规则)|覆盖.{0,8}(系统|安全).{0,8}(指令|规则))"
            ),
        ),
        (
            "system_prompt_exfiltration",
            re.compile(r"(?i)(reveal|show|print|泄露|显示|输出).{0,12}(system prompt|系统提示词|开发者指令)"),
        ),
        (
            "forced_memory_write",
            re.compile(r"(?i)(remember|store|记住|写入).{0,12}(forever|permanently|永久|长期记忆)"),
        ),
    )

    def _spans(self, text: str):
        candidates = []
        for priority, (kind, pattern, replacement) in enumerate(self.PATTERNS):
            for match in pattern.finditer(text):
                candidates.append((match.start(), match.end(), priority, kind, replacement))
        selected = []
        # A complete entity owns contained generic matches (ID versus bank number,
        # or a token containing an address). Count and redact the same spans.
        for candidate in sorted(candidates, key=lambda span: (span[0] - span[1], span[2], span[0])):
            start, end = candidate[:2]
            if not any(start < existing[1] and existing[0] < end for existing in selected):
                selected.append(candidate)
        return sorted(selected)

    def detect(self, text: str) -> list[SensitiveHit]:
        return [SensitiveHit(kind=kind, value=text[start:end])
                for start, end, _priority, kind, _replacement in self._spans(text)]

    def redact(self, text: str) -> tuple[str, list[SensitiveHit]]:
        parts, hits, cursor = [], [], 0
        for start, end, _priority, kind, replacement in self._spans(text):
            parts.extend((text[cursor:start], replacement))
            hits.append(SensitiveHit(kind=kind, value=text[start:end]))
            cursor = end
        parts.append(text[cursor:])
        return "".join(parts), hits

    def redact_structure(self, value: Any, key: str = "") -> tuple[Any, list[SensitiveHit]]:
        """Recursively redact metadata without retaining secret field values."""

        normalized_key = key.strip().lower().replace("-", "_")
        if normalized_key in self.SECRET_KEYS and value is not None and value != "":
            return "[SECRET]", [SensitiveHit(kind="secret_field", value="[REDACTED]")]
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            redacted_mapping: dict[str, Any] = {}
            hits: list[SensitiveHit] = []
            for child_key, child_value in value.items():
                child_redacted, child_hits = self.redact_structure(child_value, str(child_key))
                redacted_mapping[str(child_key)] = child_redacted
                hits.extend(child_hits)
            return redacted_mapping, hits
        if isinstance(value, list):
            redacted_items: list[Any] = []
            hits = []
            for item in value:
                redacted_item, child_hits = self.redact_structure(item)
                redacted_items.append(redacted_item)
                hits.extend(child_hits)
            return redacted_items, hits
        if isinstance(value, tuple):
            redacted_items, hits = self.redact_structure(list(value))
            return tuple(redacted_items), hits
        return value, []

    def assess_memory_risk(self, text: str) -> list[str]:
        """Return non-sensitive risk labels for memory-poisoning controls."""

        return [kind for kind, pattern in self.RISK_PATTERNS if pattern.search(text)]

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import re

from .schemas import DataRecord, PreferenceMemory, SourceType, ToolStatus, stable_id, utc_now


class PreferenceExtractor:
    """Conservative rule extraction with explicit-setting precedence."""

    def __init__(self, *, half_life_days: float | None = 30.0):
        if half_life_days is not None and half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        self.half_life_days = half_life_days

    OUTPUT_PREFERENCE_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("output.language", "zh-CN", ("中文", "汉语", "Chinese")),
        ("output.language", "en", ("英文", "英语", "English")),
        ("output.verbosity", "brief", ("简洁", "简短", "精简", "少解释", "直接给结论", "不要展开",
                                       "不要长篇大论", "concise", "brief", "briefly")),
        ("output.verbosity", "detailed", ("详细", "展开说明", "给出原因", "完整解释", "detailed", "in detail")),
        ("output.format", "table", ("表格", "列表对比", "table")),
        ("output.format", "json", ("JSON",)),
        ("output.format", "markdown", ("Markdown",)),
        ("output.format", "plain_text", ("纯文本", "plain text")),
        ("output.structure", "step_by_step", ("分步骤", "步骤", "一步一步", "逐步", "step by step")),
    )
    SECURITY_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("security.processing", "local_only", ("本地处理", "本机处理", "本地完成", "不要上传", "不上传",
                                               "离线", "端侧", "offline", "locally", "local only")),
        ("security.redaction", "required", ("脱敏", "过滤敏感", "redact", "mask sensitive")),
        ("security.confirmation", "required", ("执行前确认", "先询问", "不要直接执行", "高风险命令前确认",
                                                "ask before", "confirm before")),
    )
    CLAUSE_BREAK = re.compile(r"[，。；;,.!?！？\n]")
    INTENT = re.compile(
        r"请|要求|希望|偏好|喜欢|选择|选用|采用|改成|改用|改为|换成|使用|用|保持|需要|必须|应当|尽量|"
        r"回答|回复|输出|内容要|分析要|直接给结论|少解释|分步骤|一步一步|逐步|只在|仅在|"
        r"执行前|命令前|先询问|不要|不上传|"
        r"\b(?:please|prefer|respond|answer|reply|use|be|provide|explain|must|always|never|redact|ask|confirm)\b",
        re.IGNORECASE,
    )
    NEGATION = re.compile(r"不要|不想|不需要|不再|禁止|避免|别|不用|不使用|不喜欢|不希望|取消|"
                          r"\b(?:do not|don't|never|not|no)\b", re.IGNORECASE)
    CORRECTION = re.compile(r"改为|改用|换成|而是|还是|但(?:是)?|instead", re.IGNORECASE)

    def extract(self, records: list[DataRecord]) -> list[PreferenceMemory]:
        if not records:
            return []
        ordered = sorted(records, key=lambda record: record.timestamp)
        reference_time = max(self._parse_timestamp(record.timestamp) for record in ordered)
        rule_candidates: list[PreferenceMemory] = []
        rule_candidates.extend(self._extract_output_style(ordered, reference_time))
        rule_candidates.extend(self._extract_security_policy(ordered, reference_time))
        return [*self._aggregate_candidates(rule_candidates), *self._extract_tool_choice(ordered, reference_time)]

    def _extract_output_style(
        self,
        records: list[DataRecord],
        reference_time: datetime,
    ) -> list[PreferenceMemory]:
        return self._extract_rule_preferences(
            records,
            self.OUTPUT_PREFERENCE_RULES,
            reference_time,
            allowed_sources={SourceType.MANUAL_CONFIG, SourceType.USER_BEHAVIOR, SourceType.SESSION_CONTEXT},
        )

    def _extract_security_policy(
        self,
        records: list[DataRecord],
        reference_time: datetime,
    ) -> list[PreferenceMemory]:
        return self._extract_rule_preferences(
            records,
            self.SECURITY_RULES,
            reference_time,
            allowed_sources={SourceType.MANUAL_CONFIG, SourceType.USER_BEHAVIOR, SourceType.SYSTEM_EVENT},
        )

    def _extract_rule_preferences(
        self,
        records: list[DataRecord],
        rules: tuple[tuple[str, str, tuple[str, ...]], ...],
        reference_time: datetime,
        allowed_sources: set[SourceType],
    ) -> list[PreferenceMemory]:
        memories: list[PreferenceMemory] = []
        for record in records:
            if record.source_type not in allowed_sources or record.risk_flags:
                continue
            selected = {}
            content = self._unquoted_text(record.content)
            for key, value, keywords in rules:
                positions = self._positive_positions(content, keywords)
                if positions and (key not in selected or max(positions) > selected[key][0]):
                    selected[key] = (max(positions), value)
            for key, (_position, value) in selected.items():
                if value:
                    score, components = self._record_score(record, reference_time)
                    memories.append(
                        self._build_memory(
                            record=record,
                            key=key,
                            value=value,
                            confidence=score,
                            score_components=components,
                        )
                    )
        return memories

    def _extract_tool_choice(
        self,
        records: list[DataRecord],
        reference_time: datetime,
    ) -> list[PreferenceMemory]:
        buckets: dict[tuple[str, str, str], dict[str, list[tuple[DataRecord, float]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for record in records:
            if record.source_type != SourceType.TOOL_RESULT or record.risk_flags:
                continue
            if record.tool_status in {ToolStatus.FAILED, ToolStatus.CANCELLED}:
                continue
            tool_name = str(record.metadata.get("tool_name", "")).strip()
            if not tool_name or bool(record.metadata.get("user_rejected", False)):
                continue
            score, _components = self._record_score(record, reference_time)
            outcome_weight = 1.0 if record.tool_status == ToolStatus.SUCCEEDED else 0.65
            feedback_weight = 1.25 if bool(record.metadata.get("user_selected", False)) else 1.0
            weighted_score = score * outcome_weight * feedback_weight
            buckets[(record.tenant_id, record.user_id, record.scene)][tool_name].append(
                (record, weighted_score)
            )

        memories: list[PreferenceMemory] = []
        for (tenant_id, user_id, scene), tools in buckets.items():
            totals = {tool_name: sum(score for _record, score in evidence) for tool_name, evidence in tools.items()}
            tool_name = max(
                totals,
                key=lambda name: (
                    totals[name],
                    max(record.timestamp for record, _score in tools[name]),
                    name,
                ),
            )
            source_records = [record for record, _score in tools[tool_name]]
            representative = max(source_records, key=lambda record: record.timestamp)
            margin = totals[tool_name] / max(sum(totals.values()), 1e-9)
            mean_score = totals[tool_name] / len(source_records)
            confidence = min(0.99, 0.7 * mean_score + 0.3 * margin)
            memories.append(
                self._build_memory(
                    record=representative,
                    key=f"preferred_tool:{scene}",
                    value=tool_name,
                    confidence=confidence,
                    evidence_ids=[item.id for item in source_records],
                    score_components={
                        "evidence_weight": round(totals[tool_name], 4),
                        "selection_margin": round(margin, 4),
                        "evidence_count": float(len(source_records)),
                    },
                )
            )
        return memories

    def _aggregate_candidates(self, candidates: list[PreferenceMemory]) -> list[PreferenceMemory]:
        grouped: dict[tuple[str, str, str], dict[str, list[PreferenceMemory]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for memory in candidates:
            grouped[(memory.tenant_id, memory.user_id, memory.key)][memory.value].append(memory)

        selected: list[PreferenceMemory] = []
        for (tenant_id, user_id, key), values in grouped.items():
            totals = {
                value: sum(item.confidence for item in evidence)
                for value, evidence in values.items()
            }
            explicit = [item for evidence in values.values() for item in evidence
                        if item.score_components.get("explicitness") == 1.0]
            latest_explicit = max(explicit, key=lambda item: (item.valid_from, item.confidence, item.value)) if explicit else None
            winning_value = latest_explicit.value if latest_explicit else max(
                totals, key=lambda value: (totals[value], max(item.valid_from for item in values[value]), value))
            evidence = values[winning_value]
            representative = latest_explicit or max(evidence, key=lambda item: item.valid_from)
            total_weight = sum(totals.values())
            margin = totals[winning_value] / max(total_weight, 1e-9)
            mean_score = totals[winning_value] / len(evidence)
            confidence = min(0.99, 0.7 * mean_score + 0.3 * margin)
            selected.append(
                PreferenceMemory(
                    id=stable_id("preference", tenant_id, user_id, key, winning_value),
                    user_id=user_id,
                    key=key,
                    value=winning_value,
                    confidence=round(confidence, 3),
                    version=1,
                    scenes=sorted({scene for item in evidence for scene in item.scenes}),
                    evidence_ids=sorted({evidence_id for item in evidence for evidence_id in item.evidence_ids}),
                    updated_at=utc_now(),
                    tenant_id=tenant_id,
                    valid_from=representative.valid_from,
                    score_components={
                        "evidence_weight": round(totals[winning_value], 4),
                        "selection_margin": round(margin, 4),
                        "evidence_count": float(len(evidence)),
                        "explicitness": representative.score_components.get("explicitness", 0.0),
                        "explicit_event_time": representative.score_components.get("explicit_event_time", 0.0),
                    },
                )
            )
        return selected

    @staticmethod
    def _build_memory(
        record: DataRecord,
        key: str,
        value: str,
        confidence: float,
        evidence_ids: list[str] | None = None,
        score_components: dict[str, float] | None = None,
    ) -> PreferenceMemory:
        return PreferenceMemory(
            id=stable_id("preference", record.user_id, key, value),
            user_id=record.user_id,
            key=key,
            value=value,
            confidence=round(min(confidence, 0.99), 3),
            version=1,
            scenes=[record.scene],
            evidence_ids=evidence_ids or [record.id],
            updated_at=utc_now(),
            tenant_id=record.tenant_id,
            valid_from=record.timestamp,
            score_components={
                **(score_components or {}),
            },
        )

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _record_score(self, record: DataRecord, reference_time: datetime) -> tuple[float, dict[str, float]]:
        event_time = self._parse_timestamp(record.timestamp)
        age_days = max((reference_time - event_time).total_seconds() / 86400.0, 0.0)
        recency = 0.5 ** (age_days / self.half_life_days) if self.half_life_days else 1.0
        explicitness = {
            SourceType.MANUAL_CONFIG: 1.0,
            SourceType.USER_BEHAVIOR: 0.8,
            SourceType.SYSTEM_EVENT: 0.7,
            SourceType.SESSION_CONTEXT: 0.6,
            SourceType.TOOL_RESULT: 0.55,
            SourceType.IMPORTED_DOCUMENT: 0.5,
        }[record.source_type]
        score = (
            0.3 * record.quality_score
            + 0.35 * record.authority
            + 0.2 * recency
            + 0.15 * explicitness
        )
        return min(score, 0.99), {
            "quality": round(record.quality_score, 4),
            "authority": round(record.authority, 4),
            "recency": round(recency, 4),
            "explicitness": round(explicitness, 4),
            "explicit_event_time": event_time.timestamp() if record.source_type == SourceType.MANUAL_CONFIG else 0.0,
        }

    @staticmethod
    def _has_unnegated_keyword(content: str, keywords: tuple[str, ...]) -> bool:
        return bool(PreferenceExtractor._positive_positions(content, keywords))

    @staticmethod
    def _unquoted_text(content: str) -> str:
        quoted = r'["“][^"”]*["”]|‘[^’]*’|`[^`]*`|(?:引用|原文)(?:一句话)?[：:][^。；\n]*'
        return re.sub(quoted, lambda match: " " * len(match.group()), content)

    @classmethod
    def _positive_positions(cls, content: str, keywords: tuple[str, ...]) -> list[int]:
        positions = []
        normalized = content.casefold()
        for keyword in keywords:
            pattern = re.escape(keyword.casefold())
            if keyword.isascii():
                pattern = r"(?<![a-z0-9_])" + pattern + r"(?![a-z0-9_])"
            for match in re.finditer(pattern, normalized):
                prefix = cls.CLAUSE_BREAK.split(normalized[:match.start()])[-1]
                suffix = cls.CLAUSE_BREAK.split(normalized[match.end():])[0]
                clause = prefix + match.group() + suffix
                if not cls.INTENT.search(clause):
                    continue
                if re.search(r"(?:他|她|他们|文档|文章)(?:更|都)?喜欢|(?:标题|日志)(?:为|是|包含)|"
                             r"什么是|\bwhat (?:is|are)\b", clause):
                    continue
                # A format discussed as the subject of an explanation is not an output instruction.
                if re.search(r"(?:解释|讨论|介绍|比较)(?!.*(?:用|采用)).*$", prefix):
                    continue
                negatives = list(cls.NEGATION.finditer(prefix))
                if negatives and not cls.CORRECTION.search(prefix[negatives[-1].end():]):
                    continue
                positions.append(match.start())
        return positions

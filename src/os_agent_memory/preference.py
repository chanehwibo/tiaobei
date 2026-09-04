from __future__ import annotations

from collections import Counter

from .schemas import DataRecord, PreferenceMemory, SourceType, stable_id, utc_now


class PreferenceExtractor:
    """Rule-based preference extractor used as a baseline for evaluation."""

    OUTPUT_PREFERENCE_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("output.language", "zh-CN", ("中文", "使用中文")),
        ("output.verbosity", "brief", ("简洁", "少解释", "直接给结论", "不要展开")),
        ("output.verbosity", "detailed", ("详细", "展开说明", "给出原因", "完整解释")),
        ("output.format", "table", ("表格", "列表对比", "用表")),
        ("output.structure", "step_by_step", ("分步骤", "步骤", "一步一步")),
    )
    SECURITY_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("security.processing", "local_only", ("本地处理", "不要上传", "离线", "端侧")),
        ("security.redaction", "required", ("脱敏", "过滤敏感", "隐私", "身份证", "手机号")),
        ("security.confirmation", "required", ("执行前确认", "先询问", "不要直接执行", "高风险命令前确认")),
    )

    def extract(self, records: list[DataRecord]) -> list[PreferenceMemory]:
        preferences: list[PreferenceMemory] = []
        preferences.extend(self._extract_output_style(records))
        preferences.extend(self._extract_security_policy(records))
        preferences.extend(self._extract_tool_choice(records))
        return preferences

    def _extract_output_style(self, records: list[DataRecord]) -> list[PreferenceMemory]:
        memories: list[PreferenceMemory] = []
        for record in records:
            for key, value, keywords in self.OUTPUT_PREFERENCE_RULES:
                if any(keyword in record.content for keyword in keywords):
                    memories.append(
                        self._build_memory(
                            record=record,
                            key=key,
                            value=value,
                            confidence=0.78 + 0.1 * min(record.quality_score, 1.0),
                        )
                    )
        return memories

    def _extract_security_policy(self, records: list[DataRecord]) -> list[PreferenceMemory]:
        memories: list[PreferenceMemory] = []
        for record in records:
            for key, value, keywords in self.SECURITY_RULES:
                if any(keyword in record.content for keyword in keywords):
                    memories.append(
                        self._build_memory(
                            record=record,
                            key=key,
                            value=value,
                            confidence=0.82 + 0.08 * min(record.quality_score, 1.0),
                        )
                    )
        return memories

    def _extract_tool_choice(self, records: list[DataRecord]) -> list[PreferenceMemory]:
        by_user_scene: dict[tuple[str, str], Counter[str]] = {}
        evidence: dict[tuple[str, str, str], list[DataRecord]] = {}
        for record in records:
            if record.source_type != SourceType.TOOL_RESULT:
                continue
            tool_name = str(record.metadata.get("tool_name", "")).strip()
            if not tool_name:
                continue
            bucket_key = (record.user_id, record.scene)
            by_user_scene.setdefault(bucket_key, Counter())[tool_name] += 1
            evidence.setdefault((record.user_id, record.scene, tool_name), []).append(record)

        memories: list[PreferenceMemory] = []
        for (user_id, scene), counter in by_user_scene.items():
            tool_name, count = counter.most_common(1)[0]
            source_records = evidence[(user_id, scene, tool_name)]
            representative = source_records[-1]
            confidence = min(0.62 + count * 0.12, 0.9)
            memories.append(
                self._build_memory(
                    record=representative,
                    key=f"preferred_tool:{scene}",
                    value=tool_name,
                    confidence=confidence,
                    evidence_ids=[item.id for item in source_records],
                )
            )
        return memories

    @staticmethod
    def _build_memory(
        record: DataRecord,
        key: str,
        value: str,
        confidence: float,
        evidence_ids: list[str] | None = None,
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
                "quality": round(record.quality_score, 3),
                "authority": round(record.authority, 3),
            },
        )

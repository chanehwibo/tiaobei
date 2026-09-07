from __future__ import annotations

import re

from .schemas import DataRecord, KnowledgeMemory, stable_id, utc_now


class KnowledgeExtractor:
    """Extract structured reusable knowledge from normalized records."""

    TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("workflow", ("流程", "步骤", "SOP", "处理顺序")),
        ("case", ("案例", "故障", "问题", "复盘")),
        ("template", ("模板", "格式", "范文")),
        ("tool", ("工具", "脚本", "命令")),
        ("policy", ("安全", "合规", "权限", "隐私", "规则", "规范", "制度")),
    )

    KNOWLEDGE_HINTS = ("流程", "步骤", "案例", "模板", "复盘", "解决方案", "总结", "命令", "脚本",
                       "规则", "规范", "制度")

    def extract(self, records: list[DataRecord]) -> list[KnowledgeMemory]:
        memories: list[KnowledgeMemory] = []
        for record in records:
            if record.risk_flags or not self._looks_like_knowledge(record.content):
                continue
            title = self._make_title(record)
            tags = self._tag(record.content)
            memories.append(
                KnowledgeMemory(
                    id=stable_id(
                        "knowledge",
                        record.tenant_id,
                        record.user_id,
                        title,
                        record.content,
                    ),
                    title=title,
                    content=record.content,
                    tags=tags,
                    source_ids=[record.id],
                    version=1,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    tenant_id=record.tenant_id,
                    user_id=record.user_id,
                    knowledge_type=str(record.metadata.get("knowledge_type") or tags[0]),
                    scene=record.scene,
                    authority=record.authority,
                    privacy_level=record.privacy_level,
                    valid_from=record.timestamp,
                )
            )
        return memories

    def _looks_like_knowledge(self, content: str) -> bool:
        if len(content) < 16:
            return False
        return any(hint in content for hint in self.KNOWLEDGE_HINTS)

    def _make_title(self, record: DataRecord) -> str:
        explicit_title = record.metadata.get("title")
        if explicit_title:
            return str(explicit_title)[:48]
        first_sentence = re.split(r"[。；;.!?？]", record.content, maxsplit=1)[0]
        if len(first_sentence) > 32:
            first_sentence = first_sentence[:32] + "..."
        return first_sentence or f"{record.scene} 知识"

    def _tag(self, content: str) -> list[str]:
        tags: list[str] = []
        for tag, keywords in self.TAG_RULES:
            if any(keyword in content for keyword in keywords):
                tags.append(tag)
        return tags or ["general"]

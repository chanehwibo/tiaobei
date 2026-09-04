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
        ("policy", ("安全", "合规", "权限", "隐私")),
    )

    KNOWLEDGE_HINTS = ("流程", "步骤", "案例", "模板", "复盘", "解决方案", "总结", "命令", "脚本")

    def extract(self, records: list[DataRecord]) -> list[KnowledgeMemory]:
        memories: list[KnowledgeMemory] = []
        for record in records:
            if not self._looks_like_knowledge(record.content):
                continue
            title = self._make_title(record)
            memories.append(
                KnowledgeMemory(
                    id=stable_id("knowledge", title, record.content),
                    title=title,
                    content=record.content,
                    tags=self._tag(record.content),
                    source_ids=[record.id],
                    version=1,
                    created_at=utc_now(),
                    updated_at=utc_now(),
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


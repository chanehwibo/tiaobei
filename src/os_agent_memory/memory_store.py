from __future__ import annotations

import re
from collections import Counter

from .embeddings import EmbeddingProvider, HashEmbedding
from .schemas import ForgetResult, KnowledgeMemory, MemoryStatus, PreferenceMemory, SearchResult, stable_id, utc_now


class MemoryStore:
    """In-memory store for prototype preference and knowledge memory."""

    FORGET_ATOMS = {
        "报销",
        "模板",
        "流程",
        "案例",
        "工具",
        "安全",
        "隐私",
        "手机号",
        "身份证",
        "邮箱",
        "审批",
    }
    CONTRADICTION_PAIRS: tuple[tuple[str, str], ...] = (
        ("允许", "禁止"),
        ("开启", "关闭"),
        ("保留", "删除"),
        ("上传", "不要上传"),
        ("详细", "简洁"),
    )

    def __init__(self, embedding: EmbeddingProvider | None = None) -> None:
        self.embedding = embedding or HashEmbedding()
        self.preferences: dict[tuple[str, str], PreferenceMemory] = {}
        self.preference_history: list[PreferenceMemory] = []
        self.knowledge: dict[str, KnowledgeMemory] = {}

    def upsert_preference(self, memory: PreferenceMemory) -> PreferenceMemory:
        key = (memory.user_id, memory.key)
        current = self.preferences.get(key)
        if current is None:
            self.preferences[key] = memory
            self.preference_history.append(memory)
            return memory

        merged_scenes = sorted(set(current.scenes + memory.scenes))
        merged_evidence = sorted(set(current.evidence_ids + memory.evidence_ids))
        if current.value == memory.value:
            updated = PreferenceMemory(
                id=current.id,
                user_id=current.user_id,
                key=current.key,
                value=current.value,
                confidence=max(current.confidence, memory.confidence),
                version=current.version,
                scenes=merged_scenes,
                evidence_ids=merged_evidence,
                updated_at=utc_now(),
                status=current.status,
            )
        else:
            updated = PreferenceMemory(
                id=stable_id("preference", memory.user_id, memory.key, memory.value, str(current.version + 1)),
                user_id=memory.user_id,
                key=memory.key,
                value=memory.value,
                confidence=memory.confidence,
                version=current.version + 1,
                scenes=merged_scenes,
                evidence_ids=merged_evidence,
                updated_at=utc_now(),
                status=memory.status,
            )
        self.preferences[key] = updated
        self.preference_history.append(updated)
        return updated

    def upsert_knowledge(self, memory: KnowledgeMemory) -> KnowledgeMemory:
        conflicts = self._find_conflicts(memory)
        if conflicts:
            memory.status = MemoryStatus.CONFLICT_PENDING
            memory.conflict_with = conflicts
        self.knowledge[memory.id] = memory
        return memory

    def resolve_knowledge_conflict(self, memory_id: str, strategy: str = "accept_incoming") -> KnowledgeMemory:
        memory = self.knowledge.get(memory_id)
        if memory is None:
            raise KeyError(f"knowledge memory not found: {memory_id}")

        normalized_strategy = strategy.strip().lower()
        if normalized_strategy in {"accept_incoming", "accept_newer"}:
            for conflict_id in memory.conflict_with:
                existing = self.knowledge.get(conflict_id)
                if existing is None:
                    continue
                existing.status = MemoryStatus.FORGOTTEN
                existing.updated_at = utc_now()
            memory.status = MemoryStatus.ACTIVE
            memory.conflict_with = []
        elif normalized_strategy == "keep_existing":
            memory.status = MemoryStatus.FORGOTTEN
        elif normalized_strategy == "keep_both":
            memory.status = MemoryStatus.ACTIVE
            memory.conflict_with = []
        elif normalized_strategy in {"merge", "evidence_merge"}:
            self._merge_conflicts(memory)
        elif normalized_strategy in {"manual_review", "manual_queue"}:
            memory.status = MemoryStatus.CONFLICT_PENDING
        else:
            raise ValueError(
                "strategy must be accept_incoming, keep_existing, keep_both, merge, or manual_review"
            )

        memory.updated_at = utc_now()
        return memory

    def search_knowledge(self, query: str, top_k: int = 5) -> list[SearchResult]:
        scored: list[SearchResult] = []
        for item in self.knowledge.values():
            if item.status == MemoryStatus.FORGOTTEN:
                continue
            score = self.embedding.similarity(query, f"{item.title} {item.content} {' '.join(item.tags)}")
            if score <= 0:
                continue
            scored.append(
                SearchResult(
                    memory_id=item.id,
                    score=round(score, 4),
                    title=item.title,
                    content=item.content,
                    tags=item.tags,
                )
            )
        scored.sort(key=lambda result: result.score, reverse=True)
        return scored[:top_k]

    def forget(self, instruction: str, user_id: str | None = None) -> ForgetResult:
        keywords = self._extract_forget_keywords(instruction)
        if not keywords:
            return ForgetResult(preference_count=0, knowledge_count=0, matched_keywords=[])

        preference_count = 0
        for key, preference in list(self.preferences.items()):
            if user_id and preference.user_id != user_id:
                continue
            haystack = f"{preference.key} {preference.value} {' '.join(preference.scenes)}"
            if self._matches_forget_request(haystack, keywords):
                self.preferences[key] = PreferenceMemory(
                    id=preference.id,
                    user_id=preference.user_id,
                    key=preference.key,
                    value=preference.value,
                    confidence=preference.confidence,
                    version=preference.version + 1,
                    scenes=preference.scenes,
                    evidence_ids=preference.evidence_ids,
                    updated_at=utc_now(),
                    status=MemoryStatus.FORGOTTEN,
                )
                preference_count += 1

        knowledge_count = 0
        for item in self.knowledge.values():
            haystack = f"{item.title} {item.content} {' '.join(item.tags)}"
            if self._matches_forget_request(haystack, keywords):
                item.status = MemoryStatus.FORGOTTEN
                item.updated_at = utc_now()
                knowledge_count += 1

        return ForgetResult(preference_count=preference_count, knowledge_count=knowledge_count, matched_keywords=keywords)

    def stats(self) -> dict[str, int]:
        active_preferences = sum(1 for item in self.preferences.values() if item.status == MemoryStatus.ACTIVE)
        active_knowledge = sum(1 for item in self.knowledge.values() if item.status == MemoryStatus.ACTIVE)
        conflict_knowledge = sum(1 for item in self.knowledge.values() if item.status == MemoryStatus.CONFLICT_PENDING)
        return {
            "preferences": active_preferences,
            "preference_versions": len(self.preference_history),
            "knowledge": active_knowledge,
            "knowledge_conflicts": conflict_knowledge,
        }

    def _find_conflicts(self, candidate: KnowledgeMemory) -> list[str]:
        conflicts: list[str] = []
        for item in self.knowledge.values():
            if item.status == MemoryStatus.FORGOTTEN:
                continue
            title_similarity = self.embedding.similarity(candidate.title, item.title)
            shared_tags = set(candidate.tags) & set(item.tags)
            if title_similarity < 0.55 and not shared_tags:
                continue
            if self._has_contradiction(candidate.content, item.content):
                conflicts.append(item.id)
        return conflicts

    def _has_contradiction(self, left: str, right: str) -> bool:
        for a, b in self.CONTRADICTION_PAIRS:
            if (a in left and b in right) or (b in left and a in right):
                return True
        return False

    def _merge_conflicts(self, memory: KnowledgeMemory) -> None:
        conflicting_items = [
            self.knowledge[conflict_id] for conflict_id in memory.conflict_with if conflict_id in self.knowledge
        ]
        for item in conflicting_items:
            item.status = MemoryStatus.FORGOTTEN
            item.updated_at = utc_now()

        previous_content = "\n".join(f"- {item.title}：{item.content}" for item in conflicting_items)
        memory.content = f"{memory.content}\n旧版记忆：\n{previous_content}" if previous_content else memory.content
        memory.tags = sorted(set(memory.tags).union(*(set(item.tags) for item in conflicting_items)))
        memory.source_ids = sorted(set(memory.source_ids).union(*(set(item.source_ids) for item in conflicting_items)))
        memory.version = max([memory.version, *(item.version for item in conflicting_items)], default=memory.version) + 1
        memory.status = MemoryStatus.ACTIVE
        memory.conflict_with = []

    def _extract_forget_keywords(self, instruction: str) -> list[str]:
        text = instruction.strip()
        text = re.sub(r"^(请|帮我|麻烦)?(忘记|删除|清除|遗忘)", "", text)
        text = re.sub(r"(相关)?(记忆|偏好|知识|信息)$", "", text)
        text = re.sub(r"^(关于|所有|全部)", "", text).strip()

        candidates: list[str] = []
        if len(text) >= 2:
            candidates.append(text)
        candidates.extend(atom for atom in sorted(self.FORGET_ATOMS, key=lambda atom: (-len(atom), atom)) if atom in text)

        parts = re.split(r"[，,。；;\s]+", text)
        candidates.extend(part for part in parts if len(part) >= 2 and part not in {"关于", "所有", "全部"})

        counter = Counter(candidates)
        return [keyword for keyword, _count in counter.most_common(8)]

    def _matches_forget_request(self, haystack: str, keywords: list[str]) -> bool:
        phrase_keywords = [keyword for keyword in keywords if keyword not in self.FORGET_ATOMS]
        atom_keywords = [keyword for keyword in keywords if keyword in self.FORGET_ATOMS]
        if any(keyword in haystack for keyword in phrase_keywords):
            return True
        if phrase_keywords and len(atom_keywords) < 2:
            return False
        if atom_keywords and all(keyword in haystack for keyword in atom_keywords):
            return True
        return len(keywords) == 1 and keywords[0] in haystack

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .embeddings import EmbeddingProvider, HashEmbedding, cosine_similarity
from .schemas import (
    ForgetPlan,
    ForgetResult,
    KnowledgeMemory,
    MemoryStatus,
    PreferenceMemory,
    SearchResult,
    stable_id,
    utc_now,
)


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
        ("允许", "不允许"),
        ("可以", "不可以"),
        ("必须", "无需"),
        ("必填", "可选"),
        ("开启", "关闭"),
        ("保留", "删除"),
        ("上传", "不要上传"),
        ("详细", "简洁"),
        ("本地", "云端"),
    )

    def __init__(self, embedding: EmbeddingProvider | None = None) -> None:
        self.embedding = embedding or HashEmbedding()
        self.preferences: dict[tuple[str, str, str], PreferenceMemory] = {}
        self.preference_history: list[PreferenceMemory] = []
        self.knowledge: dict[str, KnowledgeMemory] = {}
        self.conflict_decisions: list[dict[str, object]] = []
        self.pending_forget_plans: dict[str, ForgetPlan] = {}
        self._token_index: dict[str, set[str]] = {}
        self._document_tokens: dict[str, set[str]] = {}

    def upsert_preference(self, memory: PreferenceMemory) -> PreferenceMemory:
        key = (memory.tenant_id, memory.user_id, memory.key)
        current = self.preferences.get(key)
        if not memory.valid_from:
            memory = replace(memory, valid_from=memory.updated_at)
        if current is None:
            self.preferences[key] = memory
            self.preference_history.append(replace(memory))
            return memory

        if current.value != memory.value and self._is_older(memory.valid_from, current.valid_from):
            return current

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
                tenant_id=current.tenant_id,
                valid_from=current.valid_from,
                valid_to=current.valid_to,
                tier=current.tier,
                score_components=self._merge_score_components(
                    current.score_components,
                    memory.score_components,
                ),
            )
            self._replace_history_version(updated)
        else:
            change_time = memory.valid_from or memory.updated_at
            closed_current = replace(current, valid_to=change_time, updated_at=utc_now())
            self._replace_history_version(closed_current)
            updated = PreferenceMemory(
                id=stable_id(
                    "preference",
                    memory.tenant_id,
                    memory.user_id,
                    memory.key,
                    memory.value,
                    str(current.version + 1),
                ),
                user_id=memory.user_id,
                key=memory.key,
                value=memory.value,
                confidence=memory.confidence,
                version=current.version + 1,
                scenes=merged_scenes,
                evidence_ids=merged_evidence,
                updated_at=utc_now(),
                status=memory.status,
                tenant_id=memory.tenant_id,
                valid_from=change_time,
                valid_to=None,
                tier=memory.tier,
                score_components=dict(memory.score_components),
            )
        self.preferences[key] = updated
        if not self.preference_history or self.preference_history[-1].id != updated.id:
            self.preference_history.append(replace(updated))
        return updated

    def get_preference(
        self,
        tenant_id: str,
        user_id: str,
        key: str,
        *,
        version: int | None = None,
        at_time: str | None = None,
    ) -> PreferenceMemory | None:
        if version is None and at_time is None:
            return self.preferences.get((tenant_id, user_id, key))
        candidates = [
            item
            for item in self.preference_history
            if item.tenant_id == tenant_id and item.user_id == user_id and item.key == key
        ]
        if version is not None:
            return next((item for item in reversed(candidates) if item.version == version), None)
        assert at_time is not None
        point = self._parse_time(at_time)
        for item in reversed(candidates):
            starts_before = not item.valid_from or self._parse_time(item.valid_from) <= point
            ends_after = item.valid_to is None or point < self._parse_time(item.valid_to)
            if starts_before and ends_after:
                return item
        return None

    def list_preferences(
        self,
        tenant_id: str,
        user_id: str,
        *,
        scene: str | None = None,
    ) -> list[PreferenceMemory]:
        results = [
            item
            for (stored_tenant, stored_user, _key), item in self.preferences.items()
            if stored_tenant == tenant_id
            and stored_user == user_id
            and item.status == MemoryStatus.ACTIVE
            and (scene is None or not item.scenes or scene in item.scenes)
        ]
        return sorted(results, key=lambda item: item.key)

    def upsert_knowledge(self, memory: KnowledgeMemory) -> KnowledgeMemory:
        if not memory.embedding:
            memory.embedding = self.embedding.encode(self._knowledge_text(memory))
        conflicts = self._find_conflicts(memory)
        if conflicts:
            memory.status = MemoryStatus.CONFLICT_PENDING
            memory.conflict_with = conflicts
        self.knowledge[memory.id] = memory
        self._index_knowledge(memory)
        return memory

    def resolve_knowledge_conflict(self, memory_id: str, strategy: str = "accept_incoming") -> KnowledgeMemory:
        memory = self.knowledge.get(memory_id)
        if memory is None:
            raise KeyError(f"knowledge memory not found: {memory_id}")

        normalized_strategy = strategy.strip().lower()
        if normalized_strategy in {"auto", "authority_recency"}:
            normalized_strategy = self._automatic_conflict_strategy(memory)
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
        self.conflict_decisions.append(
            {
                "memory_id": memory.id,
                "strategy": normalized_strategy,
                "status": memory.status.value,
                "resolved_at": memory.updated_at,
            }
        )
        return memory

    def search_knowledge(
        self,
        query: str,
        top_k: int = 5,
        *,
        include_pending: bool = False,
        candidate_limit: int | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        scene: str | None = None,
        min_score: float = 0.08,
        include_shared: bool = True,
    ) -> list[SearchResult]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        query = query.strip()
        if not query:
            return []
        if candidate_limit is None:
            candidate_limit = max(64, top_k * 12)
        if candidate_limit < top_k:
            raise ValueError("candidate_limit must be greater than or equal to top_k")
        if not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score must be between zero and one")

        allowed_statuses = {MemoryStatus.ACTIVE}
        if include_pending:
            allowed_statuses.add(MemoryStatus.CONFLICT_PENDING)
        tenant_id, user_id = self._resolve_search_scope(tenant_id, user_id, allowed_statuses)
        candidates = [
            item
            for item in self.knowledge.values()
            if item.status in allowed_statuses
            and item.tenant_id == tenant_id
            and (item.user_id == user_id or (include_shared and item.user_id == "*"))
            and (scene is None or item.scene in {scene, "default", "global"})
        ]
        query_tokens = self._lexical_tokens(query)
        lexical_scores = {
            item.id: self._lexical_similarity(query_tokens, self._tokens_for(item))
            for item in candidates
        }
        lexical_matches = [item for item in candidates if lexical_scores[item.id] > 0]
        if lexical_matches:
            candidates = sorted(
                lexical_matches,
                key=lambda item: (lexical_scores[item.id], item.authority, item.updated_at),
                reverse=True,
            )[:candidate_limit]
        elif len(candidates) > candidate_limit:
            candidates = sorted(
                candidates,
                key=lambda item: (item.authority, item.updated_at),
                reverse=True,
            )[:candidate_limit]

        query_embedding = self.embedding.encode(query)
        scored: list[SearchResult] = []
        for item in candidates:
            if not item.embedding:
                item.embedding = self.embedding.encode(self._knowledge_text(item))
            semantic_score = cosine_similarity(query_embedding, item.embedding)
            lexical_score = lexical_scores[item.id]
            score = 0.65 * semantic_score + 0.3 * lexical_score + 0.05 * item.authority
            if score < min_score:
                continue
            scored.append(
                SearchResult(
                    memory_id=item.id,
                    score=round(score, 4),
                    title=item.title,
                    content=item.content,
                    tags=item.tags,
                    lexical_score=round(lexical_score, 4),
                    semantic_score=round(semantic_score, 4),
                    status=item.status,
                )
            )
        scored.sort(key=lambda result: result.score, reverse=True)
        return scored[:top_k]

    def _resolve_search_scope(
        self,
        tenant_id: str | None,
        user_id: str | None,
        allowed_statuses: set[MemoryStatus],
    ) -> tuple[str, str]:
        visible = [item for item in self.knowledge.values() if item.status in allowed_statuses]
        if tenant_id is None:
            tenants = {item.tenant_id for item in visible}
            if len(tenants) > 1:
                raise ValueError("tenant_id is required when the store contains multiple tenants")
            tenant_id = next(iter(tenants), "default")
        if user_id is None:
            users = {item.user_id for item in visible if item.tenant_id == tenant_id and item.user_id != "*"}
            if len(users) > 1:
                raise ValueError("user_id is required when the tenant contains multiple users")
            user_id = next(iter(users), "default_user")
        return tenant_id, user_id

    def rebuild_index(self) -> None:
        self._token_index.clear()
        self._document_tokens.clear()
        for memory in self.knowledge.values():
            if not memory.embedding:
                memory.embedding = self.embedding.encode(self._knowledge_text(memory))
            self._index_knowledge(memory)

    def plan_forget(
        self,
        instruction: str,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        hard_delete: bool = False,
        ttl_seconds: int = 300,
    ) -> ForgetPlan:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        keywords = self._extract_forget_keywords(instruction)
        tenant_id, user_id = self._resolve_forget_scope(tenant_id, user_id)
        preference_ids = [
            preference.id
            for preference in self.preferences.values()
            if preference.tenant_id == tenant_id
            and preference.user_id == user_id
            and preference.status == MemoryStatus.ACTIVE
            and self._matches_forget_request(
                f"{preference.key} {preference.value} {' '.join(preference.scenes)}",
                keywords,
            )
        ]
        knowledge_ids = [
            item.id
            for item in self.knowledge.values()
            if item.tenant_id == tenant_id
            and item.user_id == user_id
            and item.status in {MemoryStatus.ACTIVE, MemoryStatus.CONFLICT_PENDING}
            and self._matches_forget_request(
                f"{item.title} {item.content} {' '.join(item.tags)}",
                keywords,
            )
        ]
        created = datetime.now(timezone.utc)
        plan_id = stable_id(
            "forget-plan",
            tenant_id,
            user_id,
            instruction,
            created.isoformat(timespec="microseconds"),
        )
        plan = ForgetPlan(
            id=plan_id,
            tenant_id=tenant_id,
            user_id=user_id,
            instruction=instruction,
            matched_keywords=keywords,
            preference_ids=sorted(preference_ids),
            knowledge_ids=sorted(knowledge_ids),
            created_at=created.isoformat(timespec="seconds"),
            expires_at=(created + timedelta(seconds=ttl_seconds)).isoformat(timespec="seconds"),
            hard_delete=hard_delete,
        )
        self.pending_forget_plans[plan.id] = plan
        return plan

    def forget(
        self,
        instruction: str,
        user_id: str | None = None,
        *,
        tenant_id: str | None = None,
    ) -> ForgetResult:
        """Compatibility API that immediately applies a scoped soft-delete."""

        plan = self.plan_forget(instruction, tenant_id=tenant_id, user_id=user_id)
        keywords = plan.matched_keywords
        if not keywords:
            return ForgetResult(
                preference_count=0,
                knowledge_count=0,
                matched_keywords=[],
                plan_id=plan.id,
                confirmed=True,
            )

        preference_count = 0
        for key, preference in list(self.preferences.items()):
            if preference.id not in plan.preference_ids:
                continue
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
                    tenant_id=preference.tenant_id,
                    valid_from=preference.valid_from,
                    valid_to=utc_now(),
                    tier=preference.tier,
                    score_components=dict(preference.score_components),
                )
            preference_count += 1

        knowledge_count = 0
        for item in self.knowledge.values():
            if item.id in plan.knowledge_ids:
                item.status = MemoryStatus.FORGOTTEN
                item.updated_at = utc_now()
                knowledge_count += 1

        plan.confirmed = True
        return ForgetResult(
            preference_count=preference_count,
            knowledge_count=knowledge_count,
            matched_keywords=keywords,
            plan_id=plan.id,
            confirmed=True,
            affected_preference_ids=list(plan.preference_ids),
            affected_knowledge_ids=list(plan.knowledge_ids),
        )

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

    def _replace_history_version(self, memory: PreferenceMemory) -> None:
        for index in range(len(self.preference_history) - 1, -1, -1):
            item = self.preference_history[index]
            if (
                item.tenant_id == memory.tenant_id
                and item.user_id == memory.user_id
                and item.key == memory.key
                and item.version == memory.version
            ):
                self.preference_history[index] = replace(memory)
                return
        self.preference_history.append(replace(memory))

    @staticmethod
    def _merge_score_components(
        current: dict[str, float],
        incoming: dict[str, float],
    ) -> dict[str, float]:
        merged = dict(current)
        for key, value in incoming.items():
            if key in {"evidence_weight", "evidence_count"}:
                merged[key] = round(merged.get(key, 0.0) + value, 4)
            else:
                merged[key] = max(merged.get(key, 0.0), value)
        return merged

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @classmethod
    def _is_older(cls, incoming: str, current: str) -> bool:
        if not incoming or not current:
            return False
        return cls._parse_time(incoming) < cls._parse_time(current)

    def _find_conflicts(self, candidate: KnowledgeMemory) -> list[str]:
        conflicts: list[str] = []
        for item in self.knowledge.values():
            if item.status == MemoryStatus.FORGOTTEN:
                continue
            if item.tenant_id != candidate.tenant_id or item.user_id != candidate.user_id:
                continue
            title_similarity = self.embedding.similarity(candidate.title, item.title)
            shared_tags = set(candidate.tags) & set(item.tags)
            if title_similarity < 0.55 and not shared_tags:
                continue
            if self._has_contradiction(candidate.content, item.content):
                conflicts.append(item.id)
        return conflicts

    @staticmethod
    def _knowledge_text(memory: KnowledgeMemory) -> str:
        return f"{memory.title} {memory.content} {' '.join(memory.tags)} {memory.scene} {memory.knowledge_type}"

    def _index_knowledge(self, memory: KnowledgeMemory) -> None:
        old_tokens = self._document_tokens.get(memory.id, set())
        for token in old_tokens:
            bucket = self._token_index.get(token)
            if bucket is not None:
                bucket.discard(memory.id)
                if not bucket:
                    del self._token_index[token]
        tokens = self._lexical_tokens(self._knowledge_text(memory))
        self._document_tokens[memory.id] = tokens
        for token in tokens:
            self._token_index.setdefault(token, set()).add(memory.id)

    def _tokens_for(self, memory: KnowledgeMemory) -> set[str]:
        tokens = self._document_tokens.get(memory.id)
        if tokens is None:
            self._index_knowledge(memory)
            tokens = self._document_tokens[memory.id]
        return tokens

    @staticmethod
    def _lexical_tokens(text: str) -> set[str]:
        normalized = text.lower()
        tokens = set(re.findall(r"[a-z0-9_]+", normalized))
        for segment in re.findall(r"[\u3400-\u9fff]+", normalized):
            if len(segment) <= 4:
                tokens.add(segment)
            tokens.update(segment[index : index + 2] for index in range(max(len(segment) - 1, 0)))
        return tokens

    @staticmethod
    def _lexical_similarity(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        if not intersection:
            return 0.0
        return intersection / ((len(left) * len(right)) ** 0.5)

    def _has_contradiction(self, left: str, right: str) -> bool:
        for a, b in self.CONTRADICTION_PAIRS:
            if (a in left and b in right) or (b in left and a in right):
                return True
        return False

    def _merge_conflicts(self, memory: KnowledgeMemory) -> None:
        conflicting_items = [
            self.knowledge[conflict_id] for conflict_id in memory.conflict_with if conflict_id in self.knowledge
        ]
        if not conflicting_items:
            memory.status = MemoryStatus.ACTIVE
            memory.conflict_with = []
            return

        candidates = [memory, *conflicting_items]
        winner = max(candidates, key=self._knowledge_precedence)
        combined_tags = sorted({tag for item in candidates for tag in item.tags})
        combined_sources = sorted({source_id for item in candidates for source_id in item.source_ids})
        next_version = max(item.version for item in candidates) + 1
        for item in candidates:
            if item is winner:
                item.status = MemoryStatus.ACTIVE
                item.conflict_with = []
                item.tags = combined_tags
                item.source_ids = combined_sources
                item.version = next_version
            else:
                item.status = MemoryStatus.FORGOTTEN
            item.updated_at = utc_now()
        if winner is not memory:
            memory.status = MemoryStatus.FORGOTTEN
        memory.conflict_with = []

    def _automatic_conflict_strategy(self, memory: KnowledgeMemory) -> str:
        existing = [
            self.knowledge[conflict_id]
            for conflict_id in memory.conflict_with
            if conflict_id in self.knowledge
        ]
        if not existing:
            return "keep_both"
        strongest_existing = max(existing, key=self._knowledge_precedence)
        incoming_rank = self._knowledge_precedence(memory)
        existing_rank = self._knowledge_precedence(strongest_existing)
        if memory.authority > strongest_existing.authority + 0.05:
            return "accept_incoming"
        if strongest_existing.authority > memory.authority + 0.05:
            return "keep_existing"
        if incoming_rank[1] > existing_rank[1]:
            return "accept_incoming"
        return "manual_review"

    @staticmethod
    def _knowledge_precedence(memory: KnowledgeMemory) -> tuple[float, str, int]:
        effective_time = memory.valid_from or memory.updated_at or memory.created_at
        return (memory.authority, effective_time, memory.version)

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

    def _resolve_forget_scope(
        self,
        tenant_id: str | None,
        user_id: str | None,
    ) -> tuple[str, str]:
        if tenant_id is None:
            tenants = {
                item.tenant_id for item in self.preferences.values()
            } | {item.tenant_id for item in self.knowledge.values()}
            if len(tenants) > 1:
                raise ValueError("tenant_id is required when the store contains multiple tenants")
            tenant_id = next(iter(tenants), "default")
        if user_id is None:
            users = {
                item.user_id
                for item in self.preferences.values()
                if item.tenant_id == tenant_id
            } | {
                item.user_id
                for item in self.knowledge.values()
                if item.tenant_id == tenant_id and item.user_id != "*"
            }
            if len(users) > 1:
                raise ValueError("user_id is required when the tenant contains multiple users")
            user_id = next(iter(users), "default_user")
        return tenant_id, user_id

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

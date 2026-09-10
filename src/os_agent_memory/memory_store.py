from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from heapq import nlargest, nsmallest

from .embeddings import EmbeddingProvider, HashEmbedding, cosine_similarity
from .focused_evidence import (
    POLICY as FOCUSED_EVIDENCE, body_passages, evidence_text, normalize_quantities,
    focus_request, is_answer_request, lookup_attribution, preserve_subject_text, select_evidence, support_focus,
)
from .retrieval_evidence import DEFAULT_POLICY, MIN_COVERAGE, POLICIES, content_coverage
from .schemas import (
    AuditEvent,
    ForgetPlan,
    ForgetResult,
    KnowledgeMemory,
    MemoryStatus,
    PreferenceMemory,
    SearchResult,
    stable_id,
    utc_now,
)

def _normalize_search_text(text: str) -> str:
    # Preserve punctuation used by the frozen hash scorer. Only width variants
    # of Latin letters, digits and spaces are equivalent at this boundary.
    return re.sub(r"[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a\u3000]+",
                  lambda match: unicodedata.normalize("NFKC", match.group()), text)


class MemoryStore:
    """In-memory store for prototype preference and knowledge memory."""

    # Frozen on v3 dev, not test; recalibrate for a different SDK/domain.
    DEFAULT_MIN_SCORE = 0.265
    SEARCH_TEXT_NORMALIZATION = "latin-width-v1"

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
        self.audit_events: list[AuditEvent] = []
        self._token_index: dict[str, set[str]] = {}
        self._document_tokens: dict[str, set[str]] = {}
        self._character_index: dict[str, set[str]] = {}
        self._document_characters: dict[str, set[str]] = {}
        self._vector_index: dict[tuple[int, bool], set[str]] = {}
        self._vector_keys: dict[str, set[tuple[int, bool]]] = {}
        self.runtime_state: dict[str, object] = {}

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

        if current.value != memory.value and current.score_components.get("explicitness") == 1.0:
            if (memory.score_components.get("explicitness") != 1.0
                    or memory.score_components.get("explicit_event_time", 0.0)
                    < current.score_components.get("explicit_event_time", 0.0)):
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
        current = self.knowledge.get(memory.id)
        if current is not None and current.content == memory.content:
            current.source_ids = sorted(set(current.source_ids + memory.source_ids))
            current.authority = max(current.authority, memory.authority)
            self._index_knowledge(current)
            return current
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
        min_score: float = DEFAULT_MIN_SCORE,
        include_shared: bool = True,
        now: str | None = None,
        retrieval_mode: str = "hybrid",
        required_terms: list[str] | tuple[str, ...] | None = None,
        evidence_policy: str = DEFAULT_POLICY,
    ) -> list[SearchResult]:
        if retrieval_mode not in {"hybrid", "lexical", "semantic"}:
            raise ValueError("unknown retrieval_mode")
        if evidence_policy not in POLICIES:
            raise ValueError("unknown evidence_policy")
        constraints = self._evidence_constraints(required_terms)
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        query = _normalize_search_text(query).strip()
        if not query:
            return []
        focused_answer = evidence_policy == FOCUSED_EVIDENCE and is_answer_request(query)
        if candidate_limit is None:
            candidate_limit = max(64, top_k * 12)
        if candidate_limit < top_k:
            raise ValueError("candidate_limit must be greater than or equal to top_k")
        if not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score must be between zero and one")
        if focused_answer:
            request = focus_request(query, explicit_terms=bool(constraints))
            if request.ambiguous or not request.text:
                return []
            if not constraints:
                constraints = self._evidence_constraints(request.subject_terms)
            query = preserve_subject_text(query, request.text, constraints)

        point = self._parse_time(now or utc_now())
        self.expire_knowledge(now=point.isoformat())
        allowed_statuses = {MemoryStatus.ACTIVE}
        if include_pending:
            allowed_statuses.add(MemoryStatus.CONFLICT_PENDING)
        tenant_id, user_id = self._resolve_search_scope(tenant_id, user_id, allowed_statuses)
        candidates = [
            item
            for item in self.knowledge.values()
            if item.status in allowed_statuses
            and (not item.valid_from or self._parse_time(item.valid_from) <= point)
            and item.tenant_id == tenant_id
            and (item.user_id == user_id or (include_shared and item.user_id == "*"))
            and (scene is None or item.scene in {scene, "default", "global"})
        ]
        if constraints:
            # Narrow before top-k so a high-scoring near-match cannot crowd out
            # the requested entity/version. Metadata alone is not evidence.
            postings = []
            for term, _pattern in constraints:
                postings.extend(self._token_index.get(token, set())
                                for token in re.findall(r"[a-z0-9_]+", term))
                for segment in re.findall(r"[\u3400-\u9fff]+", term):
                    if len(segment) == 1:
                        postings.append(self._character_index.get(segment, set()))
                    else:
                        postings.extend(self._token_index.get(segment[index:index + 2], set())
                                        for index in range(len(segment) - 1))
            matched_ids = {item.id for item in candidates}
            for posting in sorted(postings, key=len):
                matched_ids.intersection_update(posting)
                if not matched_ids:
                    return []
            candidates = [item for item in candidates if item.id in matched_ids
                          and self._supports_constraints(item, constraints)]
        # Do not start a model process for an empty authorized candidate set.
        if not candidates:
            return []
        query_tokens = self._lexical_tokens(query)
        query_characters = self._chinese_characters(query)
        if not query_tokens and not query_characters:
            return []
        query_embedding = self.embedding.encode(query) if retrieval_mode != "lexical" else []
        eligible = {item.id: item for item in candidates}
        lexical_postings = [self._token_index.get(token, ()) for token in query_tokens]
        # Keep the original set iteration for stable candidate ties. Count shared
        # postings once instead of allocating one token intersection per record.
        lexical_ids = set().union(*lexical_postings)
        lexical_ids &= eligible.keys()
        lexical_counts = Counter()
        for posting in lexical_postings:
            lexical_counts.update(posting)
        lexical_scores = {
            key: lexical_counts[key] / ((len(query_tokens) * len(self._tokens_for(eligible[key]))) ** 0.5)
            for key in lexical_ids
        }
        lexical_matches = [eligible[key] for key in lexical_ids]
        character_scores = {}
        if retrieval_mode == "hybrid" and query_characters:
            character_counts = Counter()
            for character in query_characters:
                character_counts.update(self._character_index.get(character, ()))
            character_scores = {
                key: character_counts[key] / ((len(query_characters) * len(self._document_characters[key])) ** 0.5)
                for key in character_counts.keys() & eligible.keys()
            }
        if lexical_matches and retrieval_mode != "semantic":
            candidates = nlargest(
                candidate_limit,
                lexical_matches,
                key=lambda item: (lexical_scores[item.id], item.authority, item.updated_at),
            )
        elif len(candidates) > candidate_limit and retrieval_mode != "semantic":
            candidates = nlargest(
                candidate_limit,
                candidates,
                key=lambda item: (item.authority, item.updated_at),
            )

        # Union lexical candidates with an independent approximate semantic path.
        # Top signed dimensions are cheap postings; exact reranking follows.
        if retrieval_mode == "hybrid":
            votes = Counter()
            for key in self._projection_keys(query_embedding):
                votes.update(self._vector_index.get(key, set()) & eligible.keys())
            semantic_ids = nsmallest(candidate_limit, votes, key=lambda key: (-votes[key], key))
            character_ids = nsmallest(candidate_limit, character_scores,
                                      key=lambda key: (-character_scores[key], key))
            candidates = list({item.id: item for item in [
                *candidates, *(eligible[key] for key in semantic_ids),
                *(eligible[key] for key in character_ids)
            ]}.values())

        scored: list[tuple[float, KnowledgeMemory, float, float, float]] = []
        direct_details = {}
        if focused_answer:
            focused = evidence_text(support_focus(query.lower()))
            focused_tokens = self._lexical_tokens(focused)
            focused_characters = self._chinese_characters(focused)
        for item in candidates:
            if not item.embedding and retrieval_mode != "lexical":
                item.embedding = self.embedding.encode(self._knowledge_text(item))
            semantic_score = cosine_similarity(query_embedding, item.embedding) if query_embedding else 0.0
            lexical_score = lexical_scores.get(item.id, 0.0)
            score = 0.65 * semantic_score + 0.3 * lexical_score + 0.05 * item.authority
            character_score = character_scores.get(item.id, 0.0)
            if retrieval_mode == "hybrid" and query_characters and self._document_characters.get(item.id):
                # Exact character evidence complements Chinese bigrams. Hash
                # collisions alone should not dominate short paraphrase ranking.
                score = (0.25 * semantic_score + 0.25 * lexical_score
                         + 0.45 * character_score + 0.05 * item.authority)
            if retrieval_mode == "lexical":
                score = lexical_score
            elif retrieval_mode == "semantic":
                score = semantic_score
            if focused_answer:
                document_score = score
                passage_score = score
                if retrieval_mode == "hybrid":
                    for passage in body_passages(item.content):
                        passage = normalize_quantities(passage)
                        lexical = self._lexical_similarity(focused_tokens, self._lexical_tokens(passage))
                        character = self._lexical_similarity(focused_characters, self._chinese_characters(passage))
                        passage_score = max(passage_score, .25 * semantic_score + .25 * lexical
                                            + .45 * character + .05 * item.authority)
                    score = passage_score
                direct_details[item.id] = {"document_score": document_score,
                                          "passage_score": passage_score}
            if score < min_score and not focused_answer:
                continue
            scored.append((score, item, lexical_score, semantic_score, character_score))
        ranked = nsmallest(top_k, scored, key=lambda row: (-row[0], row[1].id))
        evidence = {}
        if focused_answer:
            ranked, evidence = select_evidence(
                query, scored, top_k=top_k, min_score=min_score, constraints=constraints,
                normalize=lambda text: _normalize_search_text(text).lower(),
                direct_details=direct_details,
            )
        elif evidence_policy == FOCUSED_EVIDENCE:
            evidence = lookup_attribution(ranked)
        if evidence_policy == "content_coverage_v1":
            documents = [
                tuple(_normalize_search_text(text).lower() for text in (item.title, item.content))
                for _score, item, *_components in ranked
            ]
            if content_coverage(query.lower(), documents, constraints=constraints) < MIN_COVERAGE:
                return []
        return [
            SearchResult(
                memory_id=item.id,
                score=round(score, 4),
                title=item.title,
                content=item.content,
                tags=item.tags,
                lexical_score=round(lexical_score, 4),
                semantic_score=round(semantic_score, 4),
                character_score=round(character_score, 4),
                status=item.status,
                evidence=evidence.get(item.id, {}),
            )
            for score, item, lexical_score, semantic_score, character_score in ranked
        ]

    def expire_knowledge(self, *, now: str | None = None) -> list[str]:
        """Close expired active/pending records and remove their retrieval data."""
        point = self._parse_time(now or utc_now())
        expired = []
        for item in self.knowledge.values():
            if (item.status in {MemoryStatus.ACTIVE, MemoryStatus.CONFLICT_PENDING}
                    and item.valid_to and self._parse_time(item.valid_to) <= point):
                item.status = MemoryStatus.EXPIRED
                item.embedding = []
                self._remove_knowledge_index(item.id)
                expired.append(item.id)
        return sorted(expired)

    def _resolve_search_scope(
        self,
        tenant_id: str | None,
        user_id: str | None,
        allowed_statuses: set[MemoryStatus],
    ) -> tuple[str, str]:
        if tenant_id is not None and user_id is not None:
            return tenant_id, user_id
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
        self._character_index.clear()
        self._document_characters.clear()
        self._vector_index.clear()
        self._vector_keys.clear()
        for memory in self.knowledge.values():
            if memory.status not in {MemoryStatus.ACTIVE, MemoryStatus.CONFLICT_PENDING}:
                memory.embedding = []
                continue
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
        return self.confirm_forget(plan.id)

    def confirm_forget(self, plan_id: str) -> ForgetResult:
        plan = self.pending_forget_plans.get(plan_id)
        if plan is None:
            raise KeyError(f"forget plan not found: {plan_id}")
        if plan.confirmed:
            raise ValueError("forget plan has already been confirmed")
        if datetime.now(timezone.utc) >= self._parse_time(plan.expires_at):
            del self.pending_forget_plans[plan_id]
            raise ValueError("forget plan has expired")

        preference_count = 0
        for key, preference in list(self.preferences.items()):
            if preference.id not in plan.preference_ids:
                continue
            if plan.hard_delete:
                del self.preferences[key]
                self.preference_history = [
                    item
                    for item in self.preference_history
                    if not (
                        item.tenant_id == preference.tenant_id
                        and item.user_id == preference.user_id
                        and item.key == preference.key
                    )
                ]
            else:
                forgotten_at = utc_now()
                closed = replace(preference, valid_to=forgotten_at, updated_at=forgotten_at)
                self._replace_history_version(closed)
                forgotten = replace(
                    preference,
                    id=stable_id("forgotten", preference.id, str(preference.version + 1)),
                    version=preference.version + 1,
                    status=MemoryStatus.FORGOTTEN,
                    valid_from=forgotten_at,
                    valid_to=None,
                    updated_at=forgotten_at,
                )
                self.preferences[key] = forgotten
                self.preference_history.append(replace(forgotten))
            preference_count += 1

        knowledge_count = 0
        for memory_id in plan.knowledge_ids:
            item = self.knowledge.get(memory_id)
            if item is None:
                continue
            self._remove_knowledge_index(memory_id)
            if plan.hard_delete:
                del self.knowledge[memory_id]
            else:
                item.status = MemoryStatus.FORGOTTEN
                item.updated_at = utc_now()
                item.embedding = []
            knowledge_count += 1

        plan.confirmed = True
        audit = self._append_audit(
            action="memory_hard_delete" if plan.hard_delete else "memory_soft_delete",
            tenant_id=plan.tenant_id,
            user_id=plan.user_id,
            target_ids=[*plan.preference_ids, *plan.knowledge_ids],
            details={
                "plan_id": plan.id,
                "preference_count": preference_count,
                "knowledge_count": knowledge_count,
                "hard_delete": plan.hard_delete,
            },
        )
        return ForgetResult(
            preference_count=preference_count,
            knowledge_count=knowledge_count,
            matched_keywords=list(plan.matched_keywords),
            plan_id=plan.id,
            confirmed=True,
            affected_preference_ids=list(plan.preference_ids),
            affected_knowledge_ids=list(plan.knowledge_ids),
            audit_id=audit.id,
        )

    def cancel_forget(self, plan_id: str) -> bool:
        plan = self.pending_forget_plans.get(plan_id)
        if plan is None or plan.confirmed:
            return False
        del self.pending_forget_plans[plan_id]
        self._append_audit(
            action="memory_forget_cancelled",
            tenant_id=plan.tenant_id,
            user_id=plan.user_id,
            target_ids=[],
            details={"plan_id": plan.id},
        )
        return True

    def audit_receipt(self, audit_id: str) -> AuditEvent:
        event = next((item for item in self.audit_events if item.id == audit_id), None)
        if event is None:
            raise KeyError(f"audit event not found: {audit_id}")
        return event

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
    @lru_cache(maxsize=4096)
    def _parse_time(value: str) -> datetime:
        # Cache immutable parsing only, never time-dependent record eligibility.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @classmethod
    def _is_older(cls, incoming: str, current: str) -> bool:
        if not incoming or not current:
            return False
        return cls._parse_time(incoming) < cls._parse_time(current)

    def _find_conflicts(self, candidate: KnowledgeMemory) -> list[str]:
        conflicts: list[str] = []
        for item in self.knowledge.values():
            if item.id == candidate.id or item.status not in {MemoryStatus.ACTIVE, MemoryStatus.CONFLICT_PENDING}:
                continue
            if item.tenant_id != candidate.tenant_id or item.user_id != candidate.user_id:
                continue
            if item.scene != candidate.scene and not {item.scene, candidate.scene} & {"default", "global"}:
                continue
            if not self._has_contradiction(candidate.content, item.content):
                continue
            shared_tags = set(candidate.tags) & set(item.tags)
            if not shared_tags and self.embedding.similarity(candidate.title, item.title) < 0.55:
                continue
            conflicts.append(item.id)
        return conflicts

    @staticmethod
    def _knowledge_text(memory: KnowledgeMemory) -> str:
        text = f"{memory.title} {memory.content} {' '.join(memory.tags)} {memory.scene} {memory.knowledge_type}"
        return _normalize_search_text(text)

    def _index_knowledge(self, memory: KnowledgeMemory) -> None:
        if memory.status not in {MemoryStatus.ACTIVE, MemoryStatus.CONFLICT_PENDING}:
            self._remove_knowledge_index(memory.id)
            memory.embedding = []
            return
        self._remove_character_index(memory.id)
        characters = self._chinese_characters(f"{memory.title} {memory.content}")
        self._document_characters[memory.id] = characters
        for character in characters:
            self._character_index.setdefault(character, set()).add(memory.id)
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
        for key in self._vector_keys.pop(memory.id, set()):
            self._vector_index[key].discard(memory.id)
        keys = self._projection_keys(memory.embedding)
        self._vector_keys[memory.id] = keys
        for key in keys:
            self._vector_index.setdefault(key, set()).add(memory.id)

    @staticmethod
    def _projection_keys(vector) -> set[tuple[int, bool]]:
        dimensions = sorted(range(len(vector)), key=lambda i: (-abs(vector[i]), i))[:8]
        return {(i, vector[i] >= 0) for i in dimensions if vector[i]}

    def _remove_knowledge_index(self, memory_id: str) -> None:
        self._remove_character_index(memory_id)
        for key in self._vector_keys.pop(memory_id, set()):
            bucket = self._vector_index.get(key, set())
            bucket.discard(memory_id)
            if not bucket:
                self._vector_index.pop(key, None)
        for token in self._document_tokens.pop(memory_id, set()):
            bucket = self._token_index.get(token)
            if bucket is None:
                continue
            bucket.discard(memory_id)
            if not bucket:
                del self._token_index[token]

    @staticmethod
    def _chinese_characters(text: str) -> set[str]:
        return set(re.findall(r"[\u3400-\u9fff]", text))

    def _remove_character_index(self, memory_id: str) -> None:
        for character in self._document_characters.pop(memory_id, set()):
            bucket = self._character_index.get(character, set())
            bucket.discard(memory_id)
            if not bucket:
                self._character_index.pop(character, None)

    def _tokens_for(self, memory: KnowledgeMemory) -> set[str]:
        tokens = self._document_tokens.get(memory.id)
        if tokens is None:
            self._index_knowledge(memory)
            tokens = self._document_tokens[memory.id]
        return tokens

    @staticmethod
    def _lexical_tokens(text: str) -> set[str]:
        normalized = _normalize_search_text(text).lower()
        tokens = set(re.findall(r"[a-z0-9_]+", normalized))
        for segment in re.findall(r"[\u3400-\u9fff]+", normalized):
            if len(segment) <= 4:
                tokens.add(segment)
            tokens.update(segment[index : index + 2] for index in range(max(len(segment) - 1, 0)))
        return tokens

    @staticmethod
    def _evidence_constraints(required_terms):
        if required_terms is None:
            return []
        if not isinstance(required_terms, (list, tuple)) or len(required_terms) > 16:
            raise ValueError("required_terms must be an array of at most 16 non-empty strings")
        constraints = {}
        for value in required_terms:
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 128:
                raise ValueError("each required term must contain 1..128 characters")
            term = _normalize_search_text(value).strip().lower()
            if not re.search(r"[a-z0-9_\u3400-\u9fff]", term):
                raise ValueError("required terms must contain searchable letters or digits")
            pattern = re.escape(term)
            if re.match(r"[a-z0-9_]", term[0]):
                pattern = r"(?<![a-z0-9_.-])" + pattern
            if re.match(r"[a-z0-9_]", term[-1]):
                pattern += r"(?![a-z0-9_-]|\.[a-z0-9])"
            constraints[term] = re.compile(pattern)
        return list(constraints.items())

    @staticmethod
    def _supports_constraints(memory, constraints):
        fields = [_normalize_search_text(text).lower() for text in (memory.title, memory.content)]
        return all(any(pattern.search(text) for text in fields) for _term, pattern in constraints)

    @staticmethod
    def _lexical_similarity(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        if not intersection:
            return 0.0
        return intersection / ((len(left) * len(right)) ** 0.5)

    def _has_contradiction(self, left: str, right: str) -> bool:
        if left == right:
            return False
        # Distinct explicit preconditions must not be collapsed into one rule.
        conditions = [re.search(r"(?:如果|仅在|当)([^，,；;。]+)", text) for text in (left, right)]
        if all(conditions) and conditions[0].group(1) != conditions[1].group(1):
            return False
        numeric = r"([0-9]+(?:\.[0-9]+)?)(天|小时|元|次|%)"
        normalize_rule = lambda text: re.sub(r"旧版|新版|更新|旧|新|\s", "", text)
        if re.search(numeric, left) and re.search(numeric, right):
            if (re.sub(numeric, r"#\2", normalize_rule(left)) ==
                    re.sub(numeric, r"#\2", normalize_rule(right))):
                if re.findall(numeric, left) != re.findall(numeric, right):
                    return True
        for a, b in self.CONTRADICTION_PAIRS:
            for first, second in ((left, right), (right, left)):
                if a in first and b in second and b not in first:
                    first_tokens = self._lexical_tokens(normalize_rule(first.replace(a, "")))
                    second_tokens = self._lexical_tokens(normalize_rule(second.replace(b, "")))
                    if self._lexical_similarity(first_tokens, second_tokens) >= 0.35:
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

    def _append_audit(
        self,
        *,
        action: str,
        tenant_id: str,
        user_id: str | None,
        target_ids: list[str],
        details: dict[str, object],
    ) -> AuditEvent:
        created_at = utc_now()
        audit = AuditEvent(
            id=stable_id("audit", action, tenant_id, user_id or "", created_at, *sorted(target_ids)),
            action=action,
            tenant_id=tenant_id,
            user_id=user_id,
            target_ids=sorted(target_ids),
            created_at=created_at,
            details=dict(details),
        )
        self.audit_events.append(audit)
        return audit

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

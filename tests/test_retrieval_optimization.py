"""Independent full-sort/set-intersection reference for bounded retrieval."""
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.embeddings import cosine_similarity
from os_agent_memory.memory_store import MemoryStore, _normalize_search_text
from os_agent_memory.schemas import KnowledgeMemory, MemoryStatus

NOW = "2027-06-01T00:00:00+00:00"


def full_sort_reference(store, query, *, mode, top_k, limit, threshold, pending=False, shared=True, scene="office"):
    query = _normalize_search_text(query).strip()
    point = datetime.fromisoformat(NOW)
    statuses = {MemoryStatus.ACTIVE, MemoryStatus.CONFLICT_PENDING} if pending else {MemoryStatus.ACTIVE}
    candidates = [
        item for item in store.knowledge.values()
        if item.status in statuses and item.tenant_id == "tenant" and
        (item.user_id == "user" or (shared and item.user_id == "*")) and
        (scene is None or item.scene in {scene, "default", "global"}) and
        (not item.valid_from or datetime.fromisoformat(item.valid_from) <= point) and
        (not item.valid_to or point < datetime.fromisoformat(item.valid_to))
    ]
    tokens, characters = store._lexical_tokens(query), store._chinese_characters(query)
    if not tokens and not characters:
        return []
    embedding = store.embedding.encode(query) if mode != "lexical" else []
    eligible = {item.id: item for item in candidates}
    lexical_ids = set().union(*(store._token_index.get(token, set()) for token in tokens))
    lexical_ids &= eligible.keys()
    lexical_scores = {key: store._lexical_similarity(tokens, store._tokens_for(eligible[key]))
                      for key in lexical_ids}
    character_scores = {}
    if mode == "hybrid" and characters:
        character_ids = set().union(*(store._character_index.get(c, set()) for c in characters))
        character_scores = {key: store._lexical_similarity(characters, store._document_characters[key])
                            for key in character_ids & eligible.keys()}
    if lexical_ids and mode != "semantic":
        candidates = sorted((eligible[key] for key in lexical_ids),
                            key=lambda item: (lexical_scores[item.id], item.authority, item.updated_at),
                            reverse=True)[:limit]
    elif len(candidates) > limit and mode != "semantic":
        candidates = sorted(candidates, key=lambda item: (item.authority, item.updated_at), reverse=True)[:limit]
    if mode == "hybrid":
        votes = Counter()
        for key in store._projection_keys(embedding):
            votes.update(store._vector_index.get(key, set()) & eligible.keys())
        semantic_ids = sorted(votes, key=lambda key: (-votes[key], key))[:limit]
        character_ids = sorted(character_scores, key=lambda key: (-character_scores[key], key))[:limit]
        candidates = list({item.id: item for item in [
            *candidates, *(eligible[key] for key in semantic_ids), *(eligible[key] for key in character_ids)
        ]}.values())
    scored = []
    for item in candidates:
        semantic = cosine_similarity(embedding, item.embedding) if embedding else 0.0
        lexical, character = lexical_scores.get(item.id, 0.0), character_scores.get(item.id, 0.0)
        score = .65 * semantic + .3 * lexical + .05 * item.authority
        if mode == "hybrid" and characters and store._document_characters.get(item.id):
            score = .25 * semantic + .25 * lexical + .45 * character + .05 * item.authority
        if mode == "lexical":
            score = lexical
        elif mode == "semantic":
            score = semantic
        if score >= threshold:
            scored.append((score, item.id, round(lexical, 4), round(semantic, 4), round(character, 4)))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [(key, round(score, 4), lexical, semantic, character)
            for score, key, lexical, semantic, character in scored[:top_k]]


class RetrievalOptimizationTest(unittest.TestCase):
    def make_store(self):
        store, rng = MemoryStore(), random.Random(712)
        words = ["archive", "policy", "pdf", "report", "export", "audit",
                 "项目归档", "审批", "离线授权", "过期凭证", "流程记录"]
        for index in range(240):
            item = KnowledgeMemory(
                id=f"item-{index:03d}", title="policy", content=" ".join(rng.choices(words, k=6)),
                tags=["audit"], source_ids=[], version=1,
                created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
                tenant_id="other" if index % 11 == 0 else "tenant",
                user_id="*" if index % 5 == 0 else ("other" if index % 7 == 0 else "user"),
                scene=("office", "default", "global", "restricted")[index % 4],
                authority=(.5, .8, 1.0)[index % 3],
                status=(MemoryStatus.CONFLICT_PENDING if index % 13 == 0 else MemoryStatus.ACTIVE),
                valid_from="2099-01-01T00:00:00+00:00" if index % 17 == 0 else "2026-01-01T00:00:00+00:00",
                valid_to="2026-12-01T00:00:00+00:00" if index % 19 == 0 else None,
            )
            store.knowledge[item.id] = item
        store.rebuild_index()
        return store

    def assert_reference(self, store):
        for mode in ("lexical", "semantic", "hybrid"):
            for query in ("审批项目离线授权", "ＰＤＦ　export policy", "xyz_unmatched", "！"):
                for top_k, limit, threshold in ((1, 1, 0), (3, 3, .265), (5, 64, .1), (10, 300, .8)):
                    for pending, shared, scene in ((False, True, "office"), (True, False, None)):
                        with self.subTest(mode=mode, query=query, limit=limit, pending=pending):
                            expected = full_sort_reference(
                                store, query, mode=mode, top_k=top_k, limit=limit, threshold=threshold,
                                pending=pending, shared=shared, scene=scene,
                            )
                            hits = store.search_knowledge(
                                query, retrieval_mode=mode, top_k=top_k, candidate_limit=limit, min_score=threshold,
                                include_pending=pending, include_shared=shared, scene=scene,
                                tenant_id="tenant", user_id="user", now=NOW,
                                evidence_policy="similarity",
                            )
                            self.assertEqual(expected, [(hit.memory_id, hit.score, hit.lexical_score,
                                                         hit.semantic_score, hit.character_score) for hit in hits])

    def test_full_sort_reference_all_routes_scopes_limits_and_ties(self):
        self.assert_reference(self.make_store())

    def test_replacement_hard_delete_and_rebuild_keep_reference_results(self):
        store = self.make_store()
        store.knowledge["item-001"].content = "更新审批 PDF policy"
        store.knowledge["item-001"].embedding = []
        store.knowledge["item-009"].status = MemoryStatus.FORGOTTEN
        store.rebuild_index()
        plan = store.plan_forget("删除更新审批", tenant_id="tenant", user_id="user", hard_delete=True)
        store.confirm_forget(plan.id)
        self.assertNotIn("item-001", store.knowledge)
        self.assert_reference(store)

    def test_time_parse_cache_is_bounded_and_does_not_cache_visibility(self):
        store = self.make_store()
        item = store.knowledge["item-001"]
        item.valid_to = "2027-06-02T00:00:00+00:00"
        store.search_knowledge("policy", tenant_id="tenant", user_id="user", now=NOW)
        self.assertEqual(item.status, MemoryStatus.ACTIVE)
        store.search_knowledge("policy", tenant_id="tenant", user_id="user", now=item.valid_to)
        self.assertEqual(item.status, MemoryStatus.EXPIRED)
        self.assertEqual(item.embedding, [])
        self.assertNotIn(item.id, store._document_tokens)
        start = datetime.fromisoformat(NOW)
        for index in range(4200):
            store._parse_time((start + timedelta(seconds=index)).isoformat())
        self.assertLessEqual(store._parse_time.cache_info().currsize, 4096)

    def test_explicit_and_implicit_scope_rules_unchanged(self):
        store = self.make_store()
        with self.assertRaisesRegex(ValueError, "tenant_id"):
            store.search_knowledge("policy")
        with self.assertRaisesRegex(ValueError, "user_id"):
            store.search_knowledge("policy", tenant_id="tenant")
        self.assertEqual(store.search_knowledge("policy", tenant_id="nonexistent", user_id="user"), [])

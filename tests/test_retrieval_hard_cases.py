import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.memory_store import MemoryStore, _normalize_search_text
from os_agent_memory.schemas import KnowledgeMemory, MemoryStatus


def memory(identifier, content, scene="office"):
    return KnowledgeMemory(id=identifier, title=identifier, content=content, tags=["policy"],
                           source_ids=[identifier], version=1, created_at="2026-01-01T00:00:00+00:00",
                           updated_at="2026-01-01T00:00:00+00:00", scene=scene)


class RetrievalHardCaseTest(unittest.TestCase):
    def test_character_candidates_without_shared_bigrams(self):
        class UninformativeProvider:
            def encode(self, text):
                return [0.0, 1.0] if "记录" in text else [1.0, 0.0]
        store = MemoryStore(embedding=UninformativeProvider())
        store.upsert_knowledge(memory("target", "甲乙丙丁记录"))
        store.upsert_knowledge(memory("distractor", "无关事项"))
        hits = store.search_knowledge("丁丙乙甲", candidate_limit=1, top_k=1, min_score=.2)
        self.assertEqual(hits[0].memory_id, "target")
        self.assertEqual(hits[0].lexical_score, 0)
        self.assertGreater(hits[0].character_score, .8)

    def test_character_index_replacement_deletion_and_rebuild(self):
        store = MemoryStore()
        store.upsert_knowledge(memory("one", "甲乙丙丁记录"))
        store.upsert_knowledge(memory("one", "春夏秋冬资料"))
        self.assertNotIn("甲", store._character_index)
        store.knowledge["one"].status = MemoryStatus.FORGOTTEN
        store.rebuild_index()
        self.assertEqual(store._character_index, {})
        self.assertEqual(store._document_characters, {})
        self.assertEqual(store.search_knowledge("春夏资料"), [])

    def test_metadata_and_invisible_owners_do_not_supply_character_evidence(self):
        store = MemoryStore()
        item = memory("public", "天气晴朗")
        item.tags = ["工资薪酬"]
        store.upsert_knowledge(item)
        private = memory("private", "工资薪酬")
        private.user_id = "another-user"
        store.upsert_knowledge(private)
        hits = store.search_knowledge("工资薪酬", tenant_id="default", user_id=item.user_id, min_score=0)
        self.assertTrue(all(hit.memory_id != "private" for hit in hits))
        self.assertTrue(all(hit.character_score == 0 for hit in hits))
        self.assertEqual(store.search_knowledge("  !!! ", tenant_id="default", user_id=item.user_id), [])

    def test_semantic_candidate_survives_unrelated_lexical_match(self):
        class Provider:
            def encode(self, text):
                return [1.0, 0.0] if "automobile" in text or "汽车" in text else [0.0, 1.0]
            def similarity(self, left, right):
                return 0.0
        store = MemoryStore(embedding=Provider())
        store.upsert_knowledge(memory("target", "汽车的维护记录"))
        store.upsert_knowledge(memory("distractor", "maintenance of plants"))
        result = store.search_knowledge("automobile maintenance", top_k=1)
        self.assertEqual(result[0].memory_id, "target")

    def test_numeric_conditions_and_scene_boundaries(self):
        store = MemoryStore()
        self.assertTrue(store._has_contradiction("审批时限为3天。", "审批时限为5天。"))
        self.assertFalse(store._has_contradiction("审批时限为3天。", "归档时限为5天。"))
        self.assertFalse(store._has_contradiction("如果已授权，允许读取文件。", "如果未授权，禁止读取文件。"))
        self.assertFalse(store._has_contradiction("允许读取文件，禁止上传文件。", "允许读取文件，禁止上传文件。"))
        store.upsert_knowledge(memory("first", "流程允许读取归档文件并保留审计。", "personal"))
        second = store.upsert_knowledge(memory("second", "流程禁止读取归档文件并保留审计。", "restricted"))
        self.assertEqual(second.status.value, "active")

    def test_full_width_query_matches_ascii_without_changing_stored_content(self):
        store = MemoryStore()
        item = memory("target", "Report export procedure with PDF output")
        store.upsert_knowledge(item)
        for mode in ("lexical", "semantic", "hybrid"):
            with self.subTest(mode=mode):
                ascii_hits = store.search_knowledge("PDF report", retrieval_mode=mode)
                width_hits = store.search_knowledge("ＰＤＦ　ｒｅｐｏｒｔ", retrieval_mode=mode)
                self.assertTrue(ascii_hits)
                self.assertEqual(ascii_hits, width_hits)
        original = "ＩＮＶＯＩＣＥ　ＰＤＦ　ｅｘｐｏｒｔ"
        store.upsert_knowledge(memory("wide", original))
        self.assertEqual(store.knowledge["wide"].content, original)
        self.assertEqual(store.search_knowledge("invoice", retrieval_mode="lexical")[0].memory_id, "wide")
        self.assertEqual(_normalize_search_text("ＡＢＣ１２３　保留，。；！"), "ABC123 保留，。；！")

    def test_ranking_uses_unrounded_scores_then_stable_ids_for_exact_ties(self):
        class Provider:
            def encode(self, text):
                return [1.0, 0.0]
        store = MemoryStore(embedding=Provider())
        for identifier, score in (("a-lower", .60001), ("z-higher", .60004), ("y-tied", .60004)):
            item = memory(identifier, "neutral document")
            item.embedding = [score, (1 - score * score) ** .5]
            store.upsert_knowledge(item)
        hits = store.search_knowledge("query", retrieval_mode="semantic", top_k=3)
        self.assertEqual([hit.memory_id for hit in hits], ["y-tied", "z-higher", "a-lower"])
        self.assertEqual([hit.score for hit in hits], [.6, .6, .6])

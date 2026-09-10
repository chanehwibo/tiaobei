from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.embeddings import HashEmbedding
from os_agent_memory.memory_store import MemoryStore
from os_agent_memory.schemas import KnowledgeMemory, MemoryStatus
from os_agent_memory.service import MemoryService

STAMP = "2026-01-01T00:00:00+00:00"


def document(identifier, content, **values):
    return KnowledgeMemory(**{
        "id": identifier, "title": "procedure", "content": content, "tags": ["policy"],
        "source_ids": [identifier], "version": 1, "created_at": STAMP, "updated_at": STAMP,
        "tenant_id": "tenant", "user_id": "operator", "scene": "office", **values,
    })


class EvidenceConstraintsTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()

    def add(self, identifier, content, **values):
        self.store.upsert_knowledge(document(identifier, content, **values))

    def search(self, terms, **values):
        return self.store.search_knowledge(
            "procedure", tenant_id="tenant", user_id="operator",
            min_score=0, required_terms=terms, **values,
        )

    def test_filter_runs_before_candidate_limit_in_all_modes(self):
        for number in range(80):
            self.add(f"noise-{number:03d}", "procedure AE-170 v2.4 deployment")
        self.add("target", "AE-17 v2.4 signed installation requires two approvals", authority=.1)
        for mode in ("hybrid", "semantic", "lexical"):
            hits = self.search(["AE-17", "v2.4"], top_k=1, candidate_limit=1, retrieval_mode=mode)
            self.assertEqual([hit.memory_id for hit in hits], ["target"])

    def test_width_case_and_complete_identifier_boundaries(self):
        self.add("target", "AE-17 v2.4 calibration")
        for number, text in enumerate(("AE-170 v2.4", "OTHER-AE-17 v2.4", "AE-17 v2.40",
                                       "AE-17 v2.4.1", "AE-17 v2.4-rc1", "AE-17 v2.4x")):
            self.add(f"other-{number}", text)
        self.assertEqual([hit.memory_id for hit in self.search(["ＡＥ-１７", "Ｖ２.４"])], ["target"])

    def test_chinese_substrings_and_single_characters_are_searchable(self):
        self.add("target", "\u7532\u7814\u7a76\u5e93\u6062\u590d\u68c0\u67e5")
        self.assertEqual(len(self.search(["\u7814\u7a76\u5e93", "\u7532"])), 1)
        self.assertEqual(self.search(["\u7814\u7a76\u5e93", "\u4e59"]), [])

    def test_metadata_or_cross_field_phrase_cannot_supply_evidence(self):
        self.add("metadata", "neutral text", tags=["AE-17", "v2.4"])
        self.add("split", "17 v2.4", title="AE-")
        self.assertEqual(self.search(["AE-17", "v2.4"]), [])
        self.add("target", "v2.4 verified procedure", title="AE-17")
        self.assertEqual([hit.memory_id for hit in self.search(["AE-17", "v2.4"])], ["target"])

    def test_literal_patterns_are_not_regular_expressions(self):
        self.add("target", "approval (AE-17) and v2.4")
        self.add("wrong", "approval AE-17 and v2x4")
        self.assertEqual([hit.memory_id for hit in self.search(["(AE-17)", "v2.4"])], ["target"])

    def test_expiry_and_scope_still_apply_and_empty_search_skips_provider(self):
        for number, values in enumerate((
            {"tenant_id": "other"}, {"user_id": "other"}, {"scene": "other"},
            {"status": MemoryStatus.CONFLICT_PENDING}, {"status": MemoryStatus.QUARANTINED},
            {"valid_from": "2099-01-01T00:00:00+00:00"},
            {"valid_to": "2025-01-01T00:00:00+00:00"},
        )):
            self.add(f"hidden-{number}", "AE-17 v2.4 procedure", **values)
        provider = Mock(wraps=HashEmbedding())
        self.store.embedding = provider
        self.assertEqual(self.search(["AE-17", "v2.4"], scene="office", now=STAMP), [])
        provider.encode.assert_not_called()

    def test_absent_constraints_skip_provider_but_plain_semantic_search_remains_available(self):
        self.add("existing", "AE-17 v2.4 procedure")
        provider = Mock(wraps=HashEmbedding())
        self.store.embedding = provider
        self.assertEqual(self.search(["missing-identifier"]), [])
        provider.encode.assert_not_called()
        self.assertTrue(self.search(None, retrieval_mode="semantic"))
        provider.encode.assert_called_once()

    def test_empty_scope_skips_provider_without_constraints(self):
        self.store.embedding = Mock(wraps=HashEmbedding())
        self.assertEqual(self.search(None), [])
        self.store.embedding.encode.assert_not_called()

    def test_invalid_values_fail_even_with_an_empty_store(self):
        for value in ("AE-17", {}, 5, [None], [False], [""], ["  "], ["..."], ["x" * 129], ["x"] * 17):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.search(value)
        self.add("target", "AE-17 v2.4 procedure")
        self.assertEqual(self.search(None), self.search([]))
        self.assertEqual(self.search(["AE-17"]), self.search(["AE-17", "ae-17"]))

    def test_replacement_rebuild_and_forget_do_not_leave_stale_matches(self):
        self.add("target", "AE-17 v2.4 procedure")
        self.add("target", "AE-18 v2.5 procedure")
        self.store.rebuild_index()
        self.assertEqual(self.search(["AE-17"]), [])
        self.assertEqual(len(self.search(["AE-18"])), 1)
        plan = self.store.plan_forget("AE-18", tenant_id="tenant", user_id="operator", hard_delete=True)
        self.store.confirm_forget(plan.id)
        self.assertEqual(self.search(["AE-18"]), [])

    def test_service_and_sqlite_roundtrip_preserve_constraints(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.sqlite"
            service = MemoryService(self.store, database_path=path)
            self.add("target", "AE-17 v2.4 procedure")
            service.save()
            loaded = MemoryService(database_path=path)
            kwargs = {"tenant_id": "tenant", "user_id": "operator", "min_score": 0}
            self.assertEqual([row["memory_id"] for row in loaded.search(
                "procedure", required_terms=["AE-17", "v2.4"], **kwargs)], ["target"])
            self.assertEqual(loaded.search("procedure", required_terms=["AE-170"], **kwargs), [])


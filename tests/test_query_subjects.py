from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from os_agent_memory.embeddings import HashEmbedding
from os_agent_memory.focused_evidence import focus_request, preserve_subject_text
from os_agent_memory.memory_store import MemoryStore
from os_agent_memory.schemas import MemoryStatus
from tests.test_evidence_constraints import document


class QuerySubjectsTest(unittest.TestCase):
    def test_inherited_subject_ignores_narrated_neighbor_and_keeps_exact_version(self):
        for version in ("v6.2", "rev8", "r2027.03", "schema-v9"):
            query = (
                f"ZX-31 {version}\u6628\u5929\u544a\u8b66\uff0c\u65c1\u8fb9ZX-310 v99\u6b63\u5e38\uff1b"
                "\u6211\u9700\u8981\u672c\u673a\u6821\u51c6\u6d41\u7a0b"
            )
            with self.subTest(version=version):
                focused = focus_request(query)
                self.assertEqual(focused.subject_terms, ("zx-31", version))
                self.assertFalse(focused.ambiguous)
                self.assertNotIn("99", focused.text)

    def test_explicit_new_target_and_version_replace_background(self):
        for command in ("\u6211\u9700\u8981", "\u67e5\u8be2"):
            focused = focus_request(
                "ZX-31 v6.2\u6628\u5929\u544a\u8b66\uff0c" + command + "ZX-49 v7.1\u6821\u51c6\u6d41\u7a0b"
            )
            self.assertEqual(focused.subject_terms, ("zx-49", "v7.1"))
            self.assertFalse(focused.ambiguous)
        focused = focus_request("ZX-31 v6.2\u6628\u5929\u544a\u8b66\uff1b\u6211\u9700\u8981v7.1\u6821\u51c6\u6d41\u7a0b")
        self.assertEqual(focused.subject_terms, ("zx-31", "v7.1"))

    def test_excluded_reference_is_neither_target_nor_positive_query_evidence(self):
        query = (
            "ZX-31 rev8\u51fa\u73b0\u544a\u8b66\uff1b\u6211\u9700\u8981\u6821\u51c6\u6d41\u7a0b\uff0c"
            "\u4e0d\u80fd\u5957\u7528ZX-310 rev80"
        )
        focused = focus_request(query)
        self.assertEqual(focused.subject_terms, ("zx-31", "rev8"))
        self.assertEqual(focused.text, "\u6821\u51c6\u6d41\u7a0b")
        self.assertEqual(focus_request("what calibration covers ZX-31 rev8, not ZX-310 rev80").subject_terms,
                         ("zx-31", "rev8"))
        prohibition = "\u4e0d\u80fd\u6821\u51c6\u65f6\u5982\u4f55\u6062\u590dZX-31 rev8"
        self.assertEqual(focus_request(prohibition).text, prohibition)

    def test_ambiguous_targets_or_versions_do_not_silently_choose_one(self):
        for query in (
            "what calibration covers ZX-31 and ZX-49",
            "what differs between ZX-31 v6.2 and v7.1",
            "ZX-31\u548cZX-49\u90fd\u51fa\u73b0\u544a\u8b66\uff1b\u6211\u9700\u8981\u672c\u673a\u6821\u51c6\u6d41\u7a0b",
            "ZX-31\u5982\u4f55\u6821\u51c6\uff1b\u6211\u9700\u8981ZX-49\u6821\u51c6\u6d41\u7a0b",
        ):
            with self.subTest(query=query):
                self.assertTrue(focus_request(query).ambiguous)
                explicit = focus_request(query, explicit_terms=True)
                self.assertFalse(explicit.ambiguous)
                self.assertEqual(explicit.subject_terms, ())

    def test_units_plain_keywords_and_hash_names_are_not_subject_identifiers(self):
        for query in ("what is SHA256", "what is the timeout after 40 seconds",
                      "\u5982\u4f55\u68c0\u67e5attempt_id\u548c\u4e09\u6b21\u91cd\u8bd5"):
            self.assertEqual(focus_request(query).subject_terms, ())

    def test_discarded_identity_stays_in_scoring_without_duplication_or_invented_terms(self):
        original = "ZX-31 rev8\u6628\u5929\u544a\u8b66\uff1b\u6211\u9700\u8981\u6821\u51c6\u6d41\u7a0b"
        request = focus_request(original)
        constraints = MemoryStore._evidence_constraints(request.subject_terms)
        retained = preserve_subject_text(original, request.text, constraints)
        self.assertEqual(retained, "zx-31 rev8 \u6821\u51c6\u6d41\u7a0b")
        self.assertEqual(preserve_subject_text(original, retained, constraints), retained)
        unrelated = MemoryStore._evidence_constraints(["zx-310", "rev80"])
        self.assertEqual(preserve_subject_text(original, request.text, unrelated), request.text)

    def test_implicit_identity_filters_before_top_k_and_does_not_relax_boundaries(self):
        store = MemoryStore()
        for index in range(70):
            store.upsert_knowledge(document(f"near-{index}", "ZX-310 rev8 calibration readout procedure"))
        store.upsert_knowledge(document("target", "ZX-31 rev8 calibration readout procedure", authority=.1))
        options = dict(tenant_id="tenant", user_id="operator", min_score=0, top_k=1, candidate_limit=1)
        for query in ("what calibration readout covers ZX-31 rev8",
                      "what calibration readout covers \uff3a\uff38-\uff13\uff11 \uff52\uff45\uff56\uff18"):
            self.assertEqual([row.memory_id for row in store.search_knowledge(query, **options)], ["target"])
        for identity in ("ZX-31 rev8.1", "ZX-31 rev8-unreleased", "ZX-3 rev8"):
            self.assertEqual(store.search_knowledge("what calibration readout covers " + identity, **options), [])
        self.assertEqual(store.search_knowledge("what calibration readout covers ZX-31 and ZX-310", **options), [])
        self.assertTrue(store.search_knowledge("ZX-31 calibration", **options))

    def test_scope_lifecycle_and_metadata_cannot_prove_implicit_identity(self):
        store = MemoryStore()
        store.upsert_knowledge(document("metadata", "calibration readout procedure",
                                        tags=["ZX-31", "rev8"], source_ids=["ZX-31 rev8"]))
        for index, values in enumerate((
            {"tenant_id": "other"}, {"user_id": "other"}, {"scene": "other"},
            {"status": MemoryStatus.CONFLICT_PENDING}, {"status": MemoryStatus.QUARANTINED},
            {"valid_from": "2099-01-01T00:00:00+00:00"}, {"valid_to": "2025-01-01T00:00:00+00:00"},
        )):
            store.upsert_knowledge(document(str(index), "ZX-31 rev8 calibration readout procedure", **values))
        provider = Mock(wraps=HashEmbedding())
        store.embedding = provider
        self.assertEqual(store.search_knowledge(
            "what calibration readout covers ZX-31 rev8", tenant_id="tenant", user_id="operator",
            scene="office", min_score=0), [])
        provider.encode.assert_not_called()

    def test_every_companion_requires_the_inferred_subject_in_title_or_body(self):
        store = MemoryStore()
        store.upsert_knowledge(document("seed", "ZX-31 rev8 calibration readout", title="Sensor procedure"))
        store.upsert_knowledge(document("neighbor", "ZX-310 rev8 insurance settlement currency",
                                        title="Sensor requirements"))
        self.assertEqual(store.search_knowledge(
            "what insurance settlement currency covers ZX-31 rev8",
            tenant_id="tenant", user_id="operator", min_score=0), [])


if __name__ == "__main__":
    unittest.main()

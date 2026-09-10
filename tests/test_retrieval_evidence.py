import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.memory_store import MemoryStore
from os_agent_memory.retrieval_evidence import MIN_COVERAGE, content_coverage
from os_agent_memory.service import MemoryService
from tests.test_evidence_constraints import document
from scripts.evaluate_evidence_development import evaluate


class RetrievalEvidenceTest(unittest.TestCase):
    def test_shared_title_cannot_answer_an_unsupported_relationship(self):
        docs = [("cabinet handover", "sign inventory and record count"),
                ("cabinet handover", "two reviewers check the inventory")]
        self.assertEqual(content_coverage("cabinet handover insurance settlement currency", docs), 0)
        self.assertEqual(content_coverage("cabinet handover", docs), 1)
        self.assertEqual(content_coverage("what is the", docs), 0)
        self.assertEqual(content_coverage("inventory reviewers count", docs), 1)

    def test_fields_and_word_boundaries_do_not_invent_evidence(self):
        docs = [("cabinet handover", "replacement reviewer_count")]
        self.assertEqual(content_coverage("reviewer placement", docs), 0)
        self.assertEqual(content_coverage("\u7532\u4e59", [("\u7532", "\u4e59")]), 0)

    def test_required_entities_do_not_inflate_coverage(self):
        constraints = MemoryStore._evidence_constraints(["BOX-9", "rev3"])
        docs = [("procedure", "BOX-9 rev3 inventory check")]
        self.assertEqual(content_coverage("box-9 rev3 insurance price",
                                         [(t.lower(), c.lower()) for t, c in docs],
                                         constraints=constraints), 0)

    def test_default_is_unchanged_and_guard_only_abstains_without_rescoring(self):
        store = MemoryStore()
        store.upsert_knowledge(document("one", "inventory signoff count", title="cabinet handover"))
        options = {"tenant_id": "tenant", "user_id": "operator", "min_score": 0}
        service = MemoryService(store)
        query = "cabinet handover insurance settlement currency"
        original = service.search(query, **options)
        self.assertTrue(original)
        self.assertEqual(service.search(query, evidence_policy="similarity", **options), original)
        self.assertEqual(service.search(query, evidence_policy="content_coverage_v1", **options), [])
        query = "cabinet handover inventory count"
        self.assertEqual(service.search(query, evidence_policy="content_coverage_v1", **options),
                         service.search(query, **options))

    def test_hidden_records_and_tags_cannot_supply_coverage(self):
        store = MemoryStore()
        store.upsert_knowledge(document("visible", "inventory count", title="cabinet",
                                        tags=["insurance", "settlement", "currency"]))
        store.upsert_knowledge(document("private", "insurance settlement currency", user_id="another"))
        self.assertEqual(store.search_knowledge(
            "cabinet insurance settlement currency", tenant_id="tenant", user_id="operator",
            min_score=0, evidence_policy="content_coverage_v1"), [])

    def test_invalid_policy_and_empty_scope_fail_before_provider_call(self):
        store = MemoryStore(embedding=Mock())
        for policy in (None, "", "unknown", False, []):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                store.search_knowledge("query", evidence_policy=policy)
        self.assertEqual(store.search_knowledge("query", evidence_policy="content_coverage_v1"), [])
        store.embedding.encode.assert_not_called()

    def test_development_cases_are_disjoint_and_fixed_threshold_is_explicit(self):
        suite = json.loads((ROOT / "data/dev/evidence_coverage_v1.json").read_bytes())
        self.assertEqual(MIN_COVERAGE, .5)
        self.assertEqual(len(suite["documents"]), 10)
        self.assertEqual(len(suite["queries"]), 20)
        old = json.loads((ROOT / "data/eval/complex_retrieval_v1.json").read_bytes())
        constrained = json.loads((ROOT / "data/eval/complex_constraints_v1.json").read_bytes())
        old_queries = {row["query"] for data in (old, constrained) for row in data["queries"]}
        self.assertFalse(old_queries.intersection(row["query"] for row in suite["queries"]))

    def test_development_and_challenge_retain_failures_and_separate_denominators(self):
        for challenge, count in ((False, 20), (True, 10)):
            report = evaluate(challenge=challenge)
            self.assertEqual(report["dataset"]["distinct_requests"], count)
            self.assertEqual(report["dataset"]["challenge_added_after_initial_comparison"], challenge)
            self.assertFalse(report["competition_ready"])
            self.assertTrue(report["source_unchanged_during_run"])
            for profile in report["profiles"]:
                self.assertEqual(len(profile["rows"]), count)
                self.assertEqual(profile["summary"]["requests"], count)
                self.assertEqual(profile["summary"]["errors"], 0)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.focused_evidence import (
    POLICY, answer_facets, bundle_supported, normalize_quantities, query_focus, select_evidence, subject_key,
)
from os_agent_memory.memory_store import MemoryStore
from os_agent_memory.schemas import MemoryStatus
from tests.test_evidence_constraints import document


class FocusedEvidenceTest(unittest.TestCase):
    def test_focus_drops_narration_but_not_an_earlier_question(self):
        self.assertEqual(query_focus("\u80cc\u666f\u8bb0\u5f55\uff1b\u6211\u53ea\u67e5\u8be2\u5de5\u5177\u89c4\u5b9a"),
                         "\u5de5\u5177\u89c4\u5b9a")
        query = "\u5982\u4f55\u501f\u7528\uff1b\u6211\u9700\u8981\u5f52\u8fd8\u89c4\u5b9a"
        self.assertEqual(query_focus(query), query)

    def test_exact_subject_preserves_identifiers_and_versions(self):
        self.assertEqual(subject_key("sensor-a7 v3 procedure"), "sensor-a7 v3")
        self.assertNotEqual(subject_key("sensor-a7 v3 procedure"), subject_key("sensor-a70 v3 procedure"))
        self.assertNotEqual(subject_key("sensor-a7 v3 procedure"), subject_key("sensor-a7 v3.1 procedure"))
        self.assertEqual(subject_key("procedure"), "")

    def test_requested_property_cannot_borrow_coverage_from_its_premise(self):
        query = "\u5df2\u6709\u5ba1\u6279\u8bb0\u5f55\u7684\u4fdd\u9669\u8d54\u4ed8\u7f16\u53f7\u662f\u4ec0\u4e48"
        self.assertEqual(answer_facets(query), ["\u4fdd\u9669\u8d54\u4ed8\u7f16\u53f7"])
        self.assertFalse(bundle_supported(query, [("\u5ba1\u6279", "\u5df2\u6709\u5ba1\u6279\u8bb0\u5f55\u5e76\u4fdd\u7559\u7f16\u53f7")]))

    def test_property_words_in_unrelated_passages_do_not_prove_a_relation(self):
        query = "\u4ed3\u5e93\u8bbe\u5907\u7684\u81ea\u52a8\u62a5\u5e9f\u6388\u6743\u662f\u8c01\u6279\u51c6"
        unrelated = [("\u4ed3\u5e93\u8bbe\u5907", "\u6388\u6743\u516c\u5f00\u5ba3\u4f20\u7a3f\u3002\u4e0d\u4f5c\u4e3a\u62a5\u5e9f\u8bbe\u5907\u8bc1\u636e\u3002")]
        supported = [("\u4ed3\u5e93\u8bbe\u5907", "\u81ea\u52a8\u62a5\u5e9f\u6388\u6743\u7531\u8bbe\u5907\u7ec4\u6279\u51c6\u3002")]
        self.assertFalse(bundle_supported(query, unrelated))
        self.assertTrue(bundle_supported(query, supported))

    def test_quantity_equivalence_preserves_units_and_identifiers(self):
        self.assertEqual(normalize_quantities("\u4e24\u5c0f\u65f6\u548c\u4e94\u5206\u949f"), "2\u5c0f\u65f6\u548c5\u5206\u949f")
        self.assertEqual(normalize_quantities("\u4e00\u767e\u96f6\u4e09\u5929"), "103\u5929")
        self.assertNotEqual(normalize_quantities("\u516d\u5206\u949f"), normalize_quantities("\u4e94\u5206\u949f"))
        identity = "sensor-\u4e94 v3.1 \u4e09\u53f7\u67dc"
        self.assertEqual(normalize_quantities(identity), identity)

    def test_same_subject_companion_is_explicitly_labelled_not_a_direct_hit(self):
        seed = document("seed", "sensor calibration readout procedure", title="Sensor H7 procedure")
        companion = document("support", "Sensor H7 requires two reviewers", title="Sensor H7 requirements")
        rows = [(.6, seed, .5, .6, 0), (.2, companion, .1, .2, 0)]
        results, info = select_evidence("sensor h7 calibration readout and reviewers", rows,
                                        top_k=3, min_score=.265)
        self.assertEqual([row[1].id for row in results], ["seed", "support"])
        self.assertEqual(info["support"]["direct_score"], .2)
        self.assertEqual(info["support"]["origin"], "subject_companion")
        self.assertEqual(info["support"]["seed_id"], "seed")

    def test_companions_with_no_new_query_support_do_not_fill_top_k(self):
        seed = document("seed", "calibration readout procedure", title="Sensor H7 procedure")
        duplicate = document("copy", seed.content, title=seed.title)
        unrelated = document("other", "two reviewers sign the annual inventory", title="Sensor H7 requirements")
        rows = [(.6, seed, .5, .6, 0), (.4, duplicate, .1, .2, 0), (.2, unrelated, .1, .2, 0)]
        results, _info = select_evidence("sensor h7 calibration readout", rows, top_k=3, min_score=.265)
        self.assertEqual([row[1].id for row in results], ["seed"])

    def test_short_specific_role_is_not_a_generic_action(self):
        from os_agent_memory.focused_evidence import support_focus
        role = "\u4ea4\u73ed\u65f6\u5e94\u8be5\u627e\u54ea\u4f4d\u8d1f\u8d23\u5b89\u5168\u7684\u540c\u4e8b"
        self.assertEqual(support_focus(role), "\u54ea\u4f4d\u5b89\u5168")
        vague = "\u4eea\u8868\u5931\u6548\u65f6\u5982\u4f55\u5904\u7406"
        self.assertEqual(support_focus(vague), vague)

    def test_omitted_companion_cannot_supply_evidence(self):
        seed = document("seed", "inspect the cabinet count", title="Cabinet H7 procedure")
        support = document("support", "insurance settlement currency is EUR", title="Cabinet H7 requirements")
        rows = [(.6, seed, .5, .6, 0), (.2, support, .1, .2, 0)]
        hits, _info = select_evidence("cabinet h7 insurance settlement currency", rows,
                                     top_k=1, min_score=.265)
        self.assertEqual(hits, [])

    def test_recovery_keeps_prerequisites_even_when_action_words_overlap(self):
        seed = document("seed", "first inspect output, then restore the configuration",
                        title="Sensor H7 recovery")
        prerequisite = document("condition", "restore only if both reviewers approve the change",
                                title="Sensor H7 policy")
        rows = [(.6, seed, .5, .6, 0), (.2, prerequisite, .1, .2, 0)]
        results, _info = select_evidence("sensor h7 restore configuration and prerequisites", rows,
                                         top_k=3, min_score=.265)
        self.assertEqual([row[1].id for row in results], ["seed", "condition"])

    def test_seed_threshold_and_sort_use_unrounded_values(self):
        a = document("a", "inspect inventory", title="Cabinet A7 procedure")
        b = document("b", "inspect inventory", title="Cabinet B7 procedure")
        rows = [(.4, a, .1, .2, 0), (.26501, b, .1, .2, 0)]
        results, _info = select_evidence(
            "inspect inventory", rows, top_k=1, min_score=.265,
            direct_details={"a": {"document_score": .26499}, "b": {"document_score": .26501}},
        )
        self.assertEqual(results[0][1].id, "b")
        self.assertEqual(select_evidence("inspect inventory", [(.26499, a, .1, .2, 0)],
                                         top_k=1, min_score=.265), ([], {}))

    def test_replacement_delete_and_rebuild_do_not_leave_stale_companions(self):
        store = MemoryStore()
        store.upsert_knowledge(document("seed", "inspect cabinet inventory", title="Cabinet H7 procedure"))
        store.upsert_knowledge(document("support", "inventory insurance settlement currency EUR",
                                        title="Cabinet H7 policy"))
        options = dict(tenant_id="tenant", user_id="operator", scene="office",
                       evidence_policy=POLICY, min_score=0)
        query = "cabinet h7 inventory insurance settlement currency"
        self.assertTrue(store.search_knowledge(query, **options))
        store.upsert_knowledge(document("support", "unrelated maintenance diagram", title="Cabinet H7 policy"))
        store.rebuild_index()
        self.assertEqual(store.search_knowledge(query, **options), [])
        store.upsert_knowledge(document("support", "inventory insurance settlement currency EUR",
                                        title="Cabinet H7 policy"))
        plan = store.plan_forget("insurance", tenant_id="tenant", user_id="operator", hard_delete=True)
        store.confirm_forget(plan.id)
        store.rebuild_index()
        self.assertNotIn("support", store.knowledge)
        self.assertEqual(store.search_knowledge(query, **options), [])

    def test_constraints_apply_to_every_companion_before_grouping(self):
        store = MemoryStore()
        store.upsert_knowledge(document("seed", "AE-17 inspect inventory", title="Cabinet H7 procedure"))
        store.upsert_knowledge(document("support", "AE-170 insurance settlement currency",
                                        title="Cabinet H7 policy"))
        self.assertEqual(store.search_knowledge(
            "AE-17 insurance settlement currency", tenant_id="tenant", user_id="operator",
            evidence_policy=POLICY, required_terms=["AE-17"], min_score=0), [])

    def test_scope_lifecycle_and_metadata_cannot_supply_support(self):
        store = MemoryStore()
        store.upsert_knowledge(document("visible", "inspect inventory", title="Cabinet H7 procedure",
                                        tags=["insurance", "settlement", "currency"]))
        for number, values in enumerate((
            {"user_id": "other"}, {"tenant_id": "other"}, {"scene": "other"},
            {"status": MemoryStatus.QUARANTINED}, {"status": MemoryStatus.CONFLICT_PENDING},
            {"valid_from": "2099-01-01T00:00:00+00:00"}, {"valid_to": "2025-01-01T00:00:00+00:00"},
        )):
            store.upsert_knowledge(document(str(number), "insurance settlement currency",
                                            title="Cabinet H7 requirements", **values))
        self.assertEqual(store.search_knowledge(
            "cabinet h7 insurance settlement currency", tenant_id="tenant", user_id="operator",
            scene="office", evidence_policy=POLICY, min_score=0), [])


if __name__ == "__main__":
    unittest.main()

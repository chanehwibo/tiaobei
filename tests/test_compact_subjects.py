import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from os_agent_memory.focused_evidence import focus_request
from os_agent_memory.service import MemoryService
from tests.test_ingestion_scope import event


class CompactSubjectsTest(unittest.TestCase):
    def test_typed_compact_identifiers_keep_their_complete_identity(self):
        for label in ("sensor h7", "device q12", "controller ab4", "model x9", "传感器h7", "型号q12"):
            with self.subTest(label=label):
                self.assertEqual(focus_request("what calibration covers " + label).subject_terms, (label,))
        self.assertEqual(focus_request("what is SHA256 or UTF8").subject_terms, ())
        self.assertEqual(focus_request("what is the timeout after 40 seconds").subject_terms, ())
        # Generic Chinese equipment wording can be followed by a paper size,
        # not a model. Only explicit Chinese model/type cues qualify.
        self.assertEqual(focus_request("共享彩印设备A4双面彩色如何选驱动并预览页数").subject_terms, ())

    def test_inherited_excluded_and_ambiguous_subjects(self):
        self.assertEqual(focus_request("sensor h7告警；我需要校准流程，不能套用sensor h70").subject_terms,
                         ("sensor h7",))
        self.assertTrue(focus_request("what calibration covers sensor h7 and sensor h70").ambiguous)
        self.assertFalse(focus_request("what calibration covers sensor h7 and sensor h70",
                                       explicit_terms=True).ambiguous)

    def test_service_returns_both_target_sections_without_manual_constraints(self):
        service = MemoryService()
        rows = [
            event(id="seed", content="流程说明：calibration readout procedure.",
                  metadata={"title": "Sensor H7 procedure"}),
            event(id="support", content="规则说明：two reviewers approve calibration.",
                  metadata={"title": "Sensor H7 requirements"}),
            event(id="neighbor", content="流程说明：calibration readout requires three reviewers.",
                  metadata={"title": "Sensor H70 procedure"}),
        ]
        self.assertEqual(service.ingest(rows)["accepted_records"], 3)
        options = dict(tenant_id="one", user_id="reader", top_k=3)
        for model in ("sensor h7", "Ｓｅｎｓｏｒ　Ｈ７"):
            hits = service.search("what calibration readout and reviewers are required for " + model, **options)
            self.assertEqual({item["title"] for item in hits}, {"Sensor H7 procedure", "Sensor H7 requirements"})
        self.assertEqual(service.search("what calibration readout covers sensor h700", **options), [])


if __name__ == "__main__":
    unittest.main()

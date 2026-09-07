import hashlib
from pathlib import Path
import unittest

from scripts.generate_round5_materials import BEGIN, END, build_summary, evidence_block, replace_block, render_report

ROOT = Path(__file__).resolve().parents[1]


class EvidenceMaterialsTest(unittest.TestCase):
    def test_current_summary_uses_raw_fifth_round_evidence(self):
        summary = build_summary(ROOT)
        self.assertFalse(summary["competition_ready"])
        self.assertTrue(summary["vm"]["required_v11_verified"])
        self.assertTrue(summary["native"]["real_embedding_executed"])
        self.assertFalse(summary["native"]["model_identity_verified"])
        for name, digest in summary["source_sha256"].items():
            self.assertIn("/round5/", name)
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
        for platform in ("windows", "kylin"):
            requests = summary["requests"][platform]
            self.assertEqual(requests["observation_counts"]["preference_accuracy"], 68)
            self.assertEqual(requests["observation_counts"]["knowledge_recall"], 60)
            self.assertEqual(requests["records"], 10000)

    def test_generated_report_keeps_counts_and_limits(self):
        text = render_report(build_summary(ROOT))
        for value in ("实体", "原生", "INCOMPLETE", "7分钟", "独立", "Recall@3", "500ms"):
            self.assertIn(value, text)
        self.assertNotIn("Ran 65", text)

    def test_evidence_block_replacement_is_bounded(self):
        block = evidence_block(build_summary(ROOT))
        self.assertEqual(replace_block(f"before\n{BEGIN}\nold\n{END}\nafter", block),
                         f"before\n{block}\nafter")
        for text in ("missing", END + BEGIN, BEGIN + END + END):
            with self.assertRaises(ValueError):
                replace_block(text, block)

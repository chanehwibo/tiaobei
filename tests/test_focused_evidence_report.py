from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from os_agent_memory.complex_retrieval import (
    CONSTRAINT_SUITE_PATH, completion_summary, run_complex_evaluation, score_request,
    strict_quality_passed, summarize_rows,
)
from os_agent_memory.focused_evidence import POLICY
from scripts.compare_retrieval_runs import validate_report


class FocusedEvidenceReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = json.loads((ROOT / CONSTRAINT_SUITE_PATH).read_bytes())
        cls.report = run_complex_evaluation(
            ROOT, suite_name="complex_constraints_v1", sizes=(78,), hard_fractions=(0,),
            rounds=1, constraint_modes=(True,),
        )

    def test_recounts_complete_evidence_separately_from_average_recall(self):
        rows = []
        for index in range(10):
            query = {"id": str(index), "query": "fixture", "kind": "positive", "scenario": "fixture",
                     "category": "fixture", "expected": ["one", "two"]}
            returned = [{"memory_id": key, "score": .5} for key in (["one"] if index == 0 else ["one", "two"])]
            rows.append(score_request(query, returned, elapsed_ms=1))
        rows.append(score_request(
            {"id": "absent", "query": "unknown", "kind": "no_answer", "scenario": "fixture",
             "category": "fixture", "expected": []}, [], elapsed_ms=1))
        self.assertGreater(summarize_rows(rows)["macro_recall_at_3"], .85)
        completion = completion_summary(rows)
        self.assertEqual(completion["multi_document_requests"], 10)
        self.assertEqual(completion["multi_document_correct"], 9)
        self.assertFalse(completion["full_evidence_passed"])
        self.assertFalse(completion["multi_document_passed"])
        self.assertFalse(strict_quality_passed(completion))

    def test_current_evidence_is_recountable_with_no_quality_failures(self):
        validate_report(self.report, self.suite)
        self.assertEqual(self.report["schema_version"], 2)
        self.assertEqual(self.report["method"]["evidence_policies"], [POLICY])
        self.assertTrue(self.report["strict_quality_targets_met"])
        self.assertFalse(self.report["independent_blind"])
        self.assertFalse(self.report["competition_ready"])

    def test_missing_or_forged_metadata_completion_and_threshold_are_rejected(self):
        for field in ("seed", "score", "coverage", "missing", "completion", "threshold", "strict"):
            report = deepcopy(self.report)
            repeat = report["profiles"][0]["rounds"][0]
            row = next(row for row in repeat["rows"] if row["returned"])
            if field == "seed":
                row["evidence"][0]["seed_id"] = "another-record"
            elif field == "score":
                row["evidence"][0]["direct_score"] = .1
            elif field == "coverage":
                row["evidence"][0]["coverage"] = -1
            elif field == "missing":
                del row["evidence"]
            elif field == "completion":
                repeat["completion"]["multi_document_correct"] = 1000
            elif field == "threshold":
                report["method"]["completion_thresholds"]["multi_document_accuracy"] = .85
            else:
                report["strict_quality_targets_met"] = False
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_report(report, self.suite)


if __name__ == "__main__":
    unittest.main()

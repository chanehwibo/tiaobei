import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.request_evaluation import (
    evaluate_preferences, evaluate_retrieval, evaluate_sensitive, validate_suite,
)


class RequestEvaluationTest(unittest.TestCase):
    def suite(self):
        return json.loads((ROOT / "data/eval/request_regression_v1.json").read_text(encoding="utf-8"))

    def test_denominators_are_requests_and_reject_duplicate_inputs(self):
        suite = validate_suite(self.suite())
        for key in ("preferences", "conflicts", "sensitive"):
            self.assertGreaterEqual(len(suite[key]), 50)
        self.assertGreaterEqual(sum(bool(row["expected"]) for row in suite["queries"]), 50)
        for section in ("preferences", "queries", "conflicts", "sensitive"):
            duplicate = copy.deepcopy(suite)
            duplicate[section].append({**duplicate[section][0], "id": "different-id"})
            with self.assertRaisesRegex(ValueError, "duplicate request content"):
                validate_suite(duplicate)

    def test_extra_slots_fail_whole_request(self):
        row = self.suite()["preferences"][34]
        result = evaluate_preferences([{**row, "expected": {"output.language": "zh-CN"}}])
        self.assertEqual(result["requests"], 1)
        self.assertEqual(result["accuracy"], 0)
        self.assertLess(result["slot_scores"]["precision"], 1)

    def test_sensitive_scores_entities_not_just_positive_requests(self):
        result = evaluate_sensitive([{"id": "multi", "text": "demo@example.com 13912345678", "entities": [
            {"kind": "email", "value": "demo@example.com"},
        ]}])
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 1, 0))
        self.assertLess(result["f1"], 1)

    def test_weak_temporary_preference_is_not_durable(self):
        row = next(row for row in self.suite()["preferences"] if row["category"] == "temporary")
        result = evaluate_preferences([row])
        self.assertTrue(result["durable_checks_passed"])
        self.assertTrue(result["rows"][0]["passed"])

    def test_ingestion_failure_is_reported_without_changing_query_denominator(self):
        suite = self.suite()
        suite["documents"] = suite["documents"][:1]
        suite["queries"] = [suite["queries"][0], suite["queries"][60], suite["queries"][72]]
        with patch("os_agent_memory.lifecycle.KnowledgeExtractor.extract", return_value=[]):
            result = evaluate_retrieval(suite, size=8)
        self.assertFalse(result["ingestion"]["passed"])
        self.assertEqual(result["ingestion"]["missing_document_ids"], ["d-000"])
        self.assertEqual(result["positive_requests"], 1)
        self.assertEqual(result["positive_recall_at_3"], 0)
        self.assertEqual(result["records"], 8)
        self.assertEqual(result["no_answer_requests"], 1)
        self.assertEqual(result["scope_requests"], 1)

    def test_duplicate_effective_scope_is_rejected(self):
        suite = self.suite()
        suite["queries"].append({**suite["queries"][0], "id": "same-effective-input",
                                 "tenant_id": "request-eval", "user_id": "request-user"})
        with self.assertRaisesRegex(ValueError, "duplicate request content"):
            validate_suite(suite)

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.complex_retrieval import (
    FROZEN_SHA256, SUITE_PATH, make_corpus, run_profile, score_request, summarize_rows, validate_suite, visible,
)
from scripts.generate_complex_suite import build_suite


class ComplexRetrievalTest(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads((ROOT / SUITE_PATH).read_bytes())

    def test_frozen_counts_labels_and_generator(self):
        payload = (ROOT / SUITE_PATH).read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), FROZEN_SHA256)
        self.assertEqual(self.suite, build_suite())
        validate_suite(self.suite)
        self.assertEqual(len(self.suite["documents"]), 132)
        self.assertEqual(len(self.suite["queries"]), 120)
        self.assertEqual(sum(row["kind"] == "positive" for row in self.suite["queries"]), 72)
        self.assertEqual(sum(len(row["expected"]) == 2 for row in self.suite["queries"]), 12)
        self.assertEqual(len({row["scenario"] for row in self.suite["queries"]}), 12)

    def test_duplicate_input_missing_label_or_invisible_label_rejected(self):
        for mutate in (
            lambda suite: suite["queries"].append({**suite["queries"][0], "id": "duplicate"}),
            lambda suite: suite["queries"][0].update(expected=["absent"]),
            lambda suite: suite["queries"][0].update(expected=["archive-other-tenant"]),
            lambda suite: suite["queries"][0].update(expected=["archive-pending"]),
            lambda suite: suite["queries"][0].update(expected=["archive-future"]),
        ):
            with self.subTest(mutation=mutate):
                suite = deepcopy(self.suite)
                mutate(suite)
                with self.assertRaises(ValueError):
                    validate_suite(suite)
        with self.assertRaises(ValueError):
            validate_suite(self.suite, now=datetime(2100, 1, 1, tzinfo=timezone.utc))

    def test_filler_composition_is_deterministic_and_does_not_drop_fixed_records(self):
        documents, corpus = make_corpus(self.suite, 232, .75)
        self.assertEqual(documents[:132], self.suite["documents"])
        self.assertEqual(corpus["hard_fillers"], 75)
        self.assertEqual(corpus["generated_fillers"], 100)
        self.assertEqual(make_corpus(self.suite, 232, .75), (documents, corpus))
        self.assertEqual(len({row["id"] for row in documents}), 232)
        for size, fraction in ((131, .75), (232, -1), (232, float("nan")), (232, 1.1)):
            with self.assertRaises(ValueError):
                make_corpus(self.suite, size, fraction)

    def test_two_evidence_documents_partial_recall_is_not_full_success(self):
        query = self.suite["queries"][3]
        row = score_request(query, [{"memory_id": query["expected"][1], "score": .7}], elapsed_ms=2.0)
        self.assertEqual(row["recall_at_3"], .5)
        self.assertEqual(row["precision_at_3"], 1 / 3)
        self.assertEqual(row["mrr_at_3"], 1)
        self.assertLess(row["ndcg_at_3"], 1)
        self.assertFalse(row["passed"])

    def test_no_answer_errors_and_scope_do_not_inflate_accuracy(self):
        queries = self.suite["queries"]
        no_answer = [row for row in queries if row["kind"] == "no_answer"][0]
        scoped = [row for row in queries if row["kind"] == "scope"][0]
        rows = [
            score_request(no_answer, [], elapsed_ms=600, error_type="TimeoutError"),
            score_request(scoped, [], elapsed_ms=1),
        ]
        summary = summarize_rows(rows)
        self.assertEqual(summary["no_answer_requests"], 1)
        self.assertEqual(summary["no_answer_accuracy"], 0)
        self.assertEqual(summary["scope_empty_correct"], 1)
        self.assertFalse(summary["latency_valid"])
        self.assertEqual(summary["p95_ms"], 600)

    def test_extra_invisible_result_fails_even_when_expected_document_is_present(self):
        query = self.suite["queries"][0]
        row = score_request(query, [{"memory_id": query["expected"][0], "score": .8},
                                    {"memory_id": "archive-other-user", "score": .7}],
                            elapsed_ms=1, invalid_ids=["archive-other-user"])
        self.assertEqual(row["recall_at_3"], 1)
        self.assertFalse(row["passed"])
        self.assertEqual(summarize_rows([row])["leaked_records"], 1)

    def test_visibility_checks_every_boundary_and_shared_records(self):
        query = self.suite["queries"][0]
        now = datetime(2026, 9, 9, tzinfo=timezone.utc)
        docs = {row["id"]: row for row in self.suite["documents"]}
        self.assertTrue(visible(docs["archive-main"], query, now))
        self.assertTrue(visible({**docs["archive-main"], "user_id": "*"}, query, now))
        for suffix in ("old", "future", "pending", "quarantined", "other-tenant", "other-user", "other-scene"):
            self.assertFalse(visible(docs["archive-" + suffix], query, now), suffix)

    def test_profile_retains_every_failed_query_in_every_round(self):
        suite = deepcopy(self.suite)
        suite["queries"] = [suite["queries"][0], suite["queries"][6], suite["queries"][8]]
        with patch("os_agent_memory.complex_retrieval.MemoryService.search", side_effect=RuntimeError("fixture")):
            report = run_profile(suite, size=132, hard_fraction=0, mode="hybrid", rounds=2)
        self.assertFalse(report["quality_targets_met"])
        self.assertFalse(report["safety_passed"])
        self.assertFalse(report["latency_target_met"])
        for repeat in report["rounds"]:
            self.assertEqual(len(repeat["rows"]), 3)
            self.assertEqual(repeat["summary"]["errors"], 3)
            self.assertEqual(repeat["summary"]["no_answer_accuracy"], 0)
            self.assertTrue(all(row["error_type"] == "RuntimeError" for row in repeat["rows"]))


if __name__ == "__main__":
    unittest.main()

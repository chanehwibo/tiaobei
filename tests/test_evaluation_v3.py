import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from generate_eval_v3 import generate, audit_splits
from os_agent_memory.experiments import select_threshold, evaluate_frozen, run_ablations


class SplitIsolationTest(unittest.TestCase):
    def test_content_and_template_isolation_and_query_balance(self):
        suite = generate()
        self.assertEqual(suite, generate())
        self.assertTrue(all(not any(row.values()) for row in audit_splits(suite).values()))
        for split in ("train", "dev", "test"):
            queries = [q for q in suite["retrieval_queries"] if q["split"] == split]
            self.assertEqual(len(queries), 18)
            self.assertEqual(sum(q["expected_empty"] for q in queries), 6)
            self.assertTrue(all("min_score" not in q for q in queries))

    def test_leakage_is_detected(self):
        suite = generate()
        suite["records"][-1]["content"] = suite["records"][0]["content"]
        self.assertGreater(audit_splits(suite)["train/test"]["shared_content"], 0)

    def test_threshold_selection_does_not_use_test_labels(self):
        suite = generate()
        first = select_threshold(suite)
        for query in suite["retrieval_queries"]:
            if query["split"] == "test":
                query["expected_titles"] = ["changed-test-label"]
        self.assertEqual(first, select_threshold(suite))
        report = evaluate_frozen(suite)
        self.assertEqual(report["test"]["threshold"], first["threshold"])

    def test_ablation_preserves_cache_results_and_exposes_pending_conflicts(self):
        report = run_ablations(generate())
        cached = report["retrieval_comparisons"][-1]["result"]
        uncached = report["without_cache"]
        self.assertEqual([r["returned"] for r in cached["rows"]], [r["returned"] for r in uncached["rows"]])
        self.assertLess(cached["query_phase_encode_calls"], uncached["query_phase_encode_calls"])
        self.assertEqual(report["conflict_isolation_probe"][0]["pending_returned"], 0)
        self.assertGreater(report["conflict_isolation_probe"][1]["pending_returned"], 0)

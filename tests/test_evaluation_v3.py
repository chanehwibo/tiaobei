import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from generate_eval_v3 import generate, audit_splits
from os_agent_memory.experiments import select_threshold, evaluate_frozen, run_ablations, quality_targets
from os_agent_memory.memory_store import MemoryStore
from os_agent_memory.evaluation import build_store_from_raw_records
from os_agent_memory.experiments import split_rows


class SplitIsolationTest(unittest.TestCase):
    def test_fixed_suite_meets_both_targets_and_deployed_threshold_matches_dev(self):
        suite = generate()
        report = evaluate_frozen(suite)
        self.assertTrue(all(report["quality_targets"].values()), report["test"])
        self.assertEqual(report["test"]["positive_queries"], 12)
        self.assertEqual(report["test"]["no_answer_queries"], 6)
        self.assertEqual(report["configuration"]["threshold"], MemoryStore.DEFAULT_MIN_SCORE)
        store = build_store_from_raw_records(split_rows(suite, "records", "test"))
        for query, row in zip(split_rows(suite, "retrieval_queries", "test"), report["test"]["rows"]):
            hits = store.search_knowledge(query["query"], tenant_id=query["tenant_id"], user_id=query["user_id"], top_k=3)
            self.assertEqual([hit.title for hit in hits], row["returned"])

    def test_quality_gate_requires_both_metrics_and_nonempty_classes(self):
        trial = {"positive_queries": 12, "no_answer_queries": 6,
                 "positive_recall_at_3": .85, "no_answer_accuracy": .85}
        self.assertTrue(all(quality_targets(trial).values()))
        for field in ("positive_recall_at_3", "no_answer_accuracy"):
            self.assertFalse(all(quality_targets({**trial, field: .8499}).values()))
        self.assertFalse(all(quality_targets({**trial, "positive_queries": 0}).values()))
        self.assertFalse(all(quality_targets({**trial, "no_answer_queries": 0}).values()))

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

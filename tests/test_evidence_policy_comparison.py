from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from os_agent_memory.complex_retrieval import (
    completion_summary, grouped_summaries, run_complex_evaluation, score_request,
    strict_quality_passed, summarize_rows,
)
from os_agent_memory.focused_evidence import POLICY
from os_agent_memory.retrieval_evidence import POLICIES
from scripts.compare_evidence_policies import compare_policies, compare_rounds, main


def recount(report):
    for profile in report["profiles"]:
        for repeat in profile["rounds"]:
            rows = repeat["rows"]
            repeat.update(summary=summarize_rows(rows), completion=completion_summary(rows),
                          groups=grouped_summaries(rows), first_query_ms=rows[0]["elapsed_ms"])
            repeat["categories"] = {category: summarize_rows([row for row in rows if row["category"] == category])
                                    for category in {row["category"] for row in rows}}
        summaries = [repeat["summary"] for repeat in profile["rounds"]]
        profile["quality_targets_met"] = all(row["macro_recall_at_3"] >= .85 and row["no_answer_accuracy"] >= .85
                                             for row in summaries)
        profile["strict_quality_targets_met"] = all(strict_quality_passed(row["completion"])
                                                     for row in profile["rounds"])
        profile["safety_passed"] = all(row["errors"] == 0 and row["leaked_records"] == 0 for row in summaries)
        profile["latency_target_met"] = all(row["latency_valid"] and row["p95_ms"] <= 500 for row in summaries)
        profile["all_targets_met"] = all(profile[key] for key in (
            "quality_targets_met", "strict_quality_targets_met", "safety_passed", "latency_target_met"))
    for key in ("quality_targets_met", "strict_quality_targets_met", "safety_passed",
                "latency_target_met", "all_targets_met"):
        report[key] = all(profile[key] for profile in report["profiles"])


class EvidencePolicyComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"PYTHONHASHSEED": "0"}):
            cls.report = run_complex_evaluation(
                ROOT, suite_name="complex_constraints_v1", sizes=(78,), hard_fractions=(0,),
                rounds=1, constraint_modes=(True,), evidence_policies=POLICIES,
            )

    def compare(self, report):
        return compare_policies(report, sizes=(78,), hard_fractions=(0,), rounds=1)

    def test_control_failures_are_retained_without_failing_a_valid_candidate(self):
        result = self.compare(self.report)
        self.assertTrue(result["optimization_gates_passed"])
        self.assertFalse(result["all_controls_meet_targets"])
        self.assertEqual(result["paired_request_count_per_reference"], 48)
        self.assertEqual(result["distinct_requests"], 48)
        self.assertFalse(result["competition_ready"])
        self.assertFalse(result["independent_blind"])
        self.assertFalse(result["equivalent_output_speed_comparison"])
        self.assertEqual(result["candidate_policy"], POLICY)
        self.assertTrue(result["rows"][0]["reference"]["failed_ids"])
        self.assertEqual(result["rows"][0]["candidate"]["failed_ids"], [])

    def test_missing_profiles_policies_rounds_or_grouped_results_are_rejected(self):
        for kind in ("profile", "policy", "round", "group", "dimensions", "constraints", "provider"):
            report = deepcopy(self.report)
            if kind == "profile":
                report["profiles"].pop()
            elif kind == "policy":
                report["method"]["evidence_policies"].pop()
            elif kind == "round":
                report["method"]["rounds"] = 2
            elif kind == "group":
                del report["profiles"][0]["rounds"][0]["groups"]
            elif kind == "dimensions":
                report["profiles"][0]["configuration"]["dimensions"] = 128
            elif kind == "constraints":
                report["method"]["constraint_modes"] = [False]
            else:
                report["profiles"][-1]["provider"]["dimensions"] = 128
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.compare(report)
        with self.assertRaises(ValueError):
            compare_policies(self.report)

    def test_changed_source_environment_or_protocol_cannot_be_called_same_run(self):
        for kind in ("source", "evaluator", "seed", "host", "threshold", "query_order",
                     "dataset", "readiness", "snapshot"):
            report = deepcopy(self.report)
            if kind == "source":
                report["source_sha256"]["src/os_agent_memory/memory_store.py"] = "0" * 64
            elif kind == "evaluator":
                report["evaluator_sha256"]["scripts/evaluate_complex_retrieval.py"] = "0" * 64
            elif kind == "seed":
                report["environment"]["python_hash_seed"] = "random"
            elif kind == "host":
                del report["environment"]["host_fingerprint"]
            elif kind == "threshold":
                report["method"]["quality_thresholds"]["p95_ms"] = 1000
            elif kind == "query_order":
                report["method"]["query_order"] = "warmed"
            elif kind == "dataset":
                report["dataset"]["kinds"]["positive"] += 1
            elif kind == "readiness":
                report["competition_ready"] = True
            else:
                report["source_unchanged_during_run"] = False
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.compare(report)
        with self.assertRaises(ValueError):
            compare_policies(self.report, sizes=(78,), hard_fractions=(0,), rounds=1, measured_snapshot={})

    def test_one_lost_positive_fails_even_if_average_still_exceeds_original_threshold(self):
        report = deepcopy(self.report)
        profile = report["profiles"][-1]
        row = next(row for row in profile["rounds"][0]["rows"] if row["kind"] == "positive")
        row.update(score_request(row, [], elapsed_ms=row["elapsed_ms"]))
        recount(report)
        result = self.compare(report)
        self.assertTrue(profile["quality_targets_met"])
        self.assertFalse(result["optimization_gates_passed"])
        self.assertTrue(result["request_regressions"])
        self.assertEqual(len(result["candidate_failures"]), 1)

    def test_latency_violation_fails_without_changing_quality(self):
        report = deepcopy(self.report)
        for row in report["profiles"][-1]["rounds"][0]["rows"]:
            row["elapsed_ms"] = 501
        recount(report)
        result = self.compare(report)
        self.assertTrue(result["checks"]["full_evidence_and_abstention_100_percent"])
        self.assertFalse(result["checks"]["p95_at_most_500ms_every_profile_and_round"])
        self.assertFalse(result["optimization_gates_passed"])

    def test_ranking_and_distractor_regression_are_not_masked_by_full_recall(self):
        query = {"id": "fixture", "query": "fixture", "kind": "positive", "scenario": "fixture",
                 "category": "fixture", "expected": ["evidence"]}
        before_row = score_request(query, [{"memory_id": "evidence", "score": .5}], elapsed_ms=1)
        after_row = score_request(query, [{"memory_id": key, "score": .5}
                                         for key in ("distractor", "evidence")], elapsed_ms=1)
        before, after = ({"rows": [row], "summary": summarize_rows([row])} for row in (before_row, after_row))
        differences = compare_rounds(before, after)
        self.assertTrue(after_row["passed"])
        self.assertEqual(differences["request_regressions"], [])
        self.assertEqual({row["metric"] for row in differences["metric_regressions"]},
                         {"mrr_at_3", "ndcg_at_3", "irrelevant_returned", "distractor_return_rate"})

    def test_equally_good_aggregates_cannot_mask_swapped_request_failures(self):
        queries = [{"id": str(index), "query": "fixture", "kind": "positive", "scenario": "fixture",
                    "category": "fixture", "expected": ["evidence"]} for index in range(2)]
        rows = [[score_request(query, [{"memory_id": "evidence", "score": .5}] if index == success else [],
                               elapsed_ms=1) for index, query in enumerate(queries)] for success in range(2)]
        before, after = ({"rows": group, "summary": summarize_rows(group)} for group in rows)
        differences = compare_rounds(before, after)
        self.assertEqual(differences["metric_regressions"], [])
        self.assertEqual(differences["request_regressions"][0]["id"], "0")

    def test_cli_refuses_to_overwrite_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "comparison.json"
            output.touch()
            with self.assertRaisesRegex(ValueError, "overwrite"):
                main(["--input", "not-read.json", "--output", str(output)])


if __name__ == "__main__":
    unittest.main()

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from os_agent_memory.request_contract import (
    FROZEN_DATASET_SHA256, assess_frozen_requests, assess_request_targets,
)
from scripts.evaluate_requests import main


class RequestContractTest(unittest.TestCase):
    def report(self):
        report = json.loads((ROOT / "artifacts/verification/round5/requests_windows.json").read_bytes())
        # Historical report predates the explicit top_k field; this is a gate fixture only.
        report["retrieval"]["top_k"] = 3
        return report

    def test_frozen_bytes_and_known_report(self):
        self.assertEqual(hashlib.sha256((ROOT / "data/eval/request_regression_v1.json").read_bytes()).hexdigest(),
                         FROZEN_DATASET_SHA256)
        self.assertTrue(assess_frozen_requests(self.report())["passed"])

    def test_numeric_gate_does_not_trust_boolean_claim(self):
        for key, value in (
            ("preference_accuracy", .849), ("knowledge_recall", .849),
            ("conflict_accuracy", .879), ("retrieval_p95_ms", 500.001), ("sensitive_f1", .899),
            ("preference_accuracy", True), ("sensitive_f1", float("nan")),
            ("retrieval_p95_ms", -1), ("knowledge_recall", 1.01),
        ):
            with self.subTest(key=key, value=value):
                report = self.report()
                report["metrics"][key] = value
                self.assertTrue(report["all_targets_met"])
                self.assertFalse(assess_request_targets(report)["passed"])

    def test_frozen_scope_configuration_and_counts_are_enforced(self):
        source = self.report()
        changes = (
            ("dataset", "sha256", "0" * 64),
            ("observation_counts", "knowledge_recall", 49),
            ("observation_counts", "preference_accuracy", 69),
            ("retrieval", "records", 9999), ("retrieval", "threshold", .26),
            ("retrieval", "top_k", 5), ("retrieval", "provider", {}),
        )
        for section, key, value in changes:
            with self.subTest(section=section, key=key):
                report = copy.deepcopy(source)
                report[section][key] = value
                self.assertFalse(assess_frozen_requests(report)["passed"])

    def test_empty_missing_or_false_safety_does_not_pass(self):
        for safety in ({}, {"no_scope_leaks": True}, {**self.report()["safety_checks"], "future_check": False}):
            report = self.report()
            report["safety_checks"] = safety
            self.assertFalse(assess_frozen_requests(report)["passed"])

    def test_repeated_and_missing_rows_or_changed_numerators_fail(self):
        for section in ("preference", "retrieval", "conflict", "sensitive"):
            report = self.report()
            report[section]["rows"][-1] = copy.deepcopy(report[section]["rows"][0])
            self.assertFalse(assess_frozen_requests(report)["passed"])
        report = self.report()
        report["preference"]["correct"] -= 1
        self.assertFalse(assess_frozen_requests(report)["passed"])

    def test_row_measurements_cannot_disagree_with_green_summaries(self):
        changes = (
            ("preference", "passed", False), ("conflict", "passed", False),
            ("sensitive", "fp", 1), ("sensitive", "redaction_leak", True),
            ("retrieval", "elapsed_ms", float("inf")), ("retrieval", "returned", []),
        )
        for section, key, value in changes:
            with self.subTest(section=section, key=key):
                report = self.report()
                report[section]["rows"][0][key] = value
                self.assertFalse(assess_frozen_requests(report)["passed"])

    def test_cli_fails_nonzero_and_retains_failed_report(self):
        report = self.report()
        report["metrics"]["sensitive_f1"] = .5
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "failed.json"
            with patch("scripts.evaluate_requests.run_request_evaluation", return_value=report), contextlib.redirect_stdout(io.StringIO()):
                result = main(["--output", str(output), "--require-frozen"])
            self.assertEqual(result, 2)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(saved["release_gate"]["passed"])
            self.assertEqual(saved["metrics"]["sensitive_f1"], .5)

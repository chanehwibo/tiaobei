import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.experiments import assess_decay_diagnostics, decay_diagnostics
from scripts import benchmark_service, run_ablations


class BenchmarkEntrypointsTest(unittest.TestCase):
    def test_diagnostic_gate_recounts_predictions_and_rejects_empty_rows(self):
        report = {"decay_diagnostics": decay_diagnostics()}
        self.assertTrue(assess_decay_diagnostics(report)["passed"])
        for mutate in (
            lambda r: r["decay_diagnostics"]["cases"][0]["results"][0].update(prediction="wrong"),
            lambda r: r["decay_diagnostics"]["comparison"].update(regressed=1),
            lambda r: r["decay_diagnostics"].update(cases=[]),
            lambda r: r["decay_diagnostics"]["cases"][0].update(results=[]),
            lambda r: r["decay_diagnostics"].update(independent_blind=True),
        ):
            changed = copy.deepcopy(report)
            mutate(changed)
            self.assertFalse(assess_decay_diagnostics(changed)["passed"])

    def test_workload_refuses_existing_evidence_before_running(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "evidence.json"
            target.write_text("original", encoding="utf-8")
            with patch.object(benchmark_service, "run_service_workload") as runner:
                with self.assertRaises(SystemExit) as raised:
                    benchmark_service.main(["--output", str(target)])
            self.assertEqual(raised.exception.code, 2)
            runner.assert_not_called()
            self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_workload_integrity_failure_is_nonzero_and_preserved(self):
        report = {"integrity_passed": False, "results": []}
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "evidence.json"
            with patch.object(benchmark_service, "run_service_workload", return_value=report):
                self.assertEqual(benchmark_service.main(["--output", str(target), "--require-integrity"]), 2)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), report)

    def test_ablation_failure_is_nonzero_and_cannot_be_overwritten(self):
        report = {"decay_diagnostics": decay_diagnostics(), "retrieval_comparisons": []}
        report["decay_diagnostics"]["cases"][0]["results"][0]["prediction"] = "wrong"
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "evidence.json"
            with patch.object(run_ablations, "run_ablations", return_value=report):
                self.assertEqual(run_ablations.main(["--output", str(target), "--require-diagnostics"]), 2)
                with self.assertRaises(SystemExit) as raised:
                    run_ablations.main(["--output", str(target)])
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(json.loads(target.read_text(encoding="utf-8"))["diagnostic_gate"]["passed"])

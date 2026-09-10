from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_review_submission import make_manifest
from scripts.generate_review_materials import (
    DOCUMENTS, INITIAL_STATUS, OFFICE_NAMES, SDK_RISK_STATUS, frozen_block, main, metric_rows,
    render_markdown, slide_sections, validate_windows_evidence, verify_outputs,
)
from scripts.generate_takeover_materials import WINDOWS_CHECKS
from scripts.verify_kylin_guest import file_hashes

ROOT = Path(__file__).resolve().parents[1]


def fixture_summary():
    requests = json.loads((ROOT / "artifacts/verification/round5/windows/requests.json").read_bytes())
    service = json.loads((ROOT / "artifacts/verification/takeover/t01-service.json").read_bytes())
    quality = {
        "requests": 120, "macro_recall_at_3": .94, "precision_at_3": .37,
        "no_answer_accuracy": .04, "no_answer_correct": 1, "no_answer_requests": 24,
        "false_answers": 23, "distractor_return_rate": .58, "leaked_records": 0, "errors": 0, "p95_ms": 39,
    }
    comparison = {"identical_ranked_results_and_scores": True, "rows": [
        {"records": 10000, "hard_fraction": .75, "round": 1, "before_p95_ms": 68, "after_p95_ms": 39},
    ]}
    return {
        "generated_at_utc": "2026-09-09T00:00:00Z",
        "windows": {"tests_run": 7, "engineering_checks": len(WINDOWS_CHECKS), "metrics": requests["metrics"],
                    "observation_counts": requests["observation_counts"], "service": service["results"][-1]},
        "complex": {"quality_targets_met": False, "profiles": [
            {"records": 10000, "hard_fraction": .75, "rounds": [quality]}],
            "comparison": comparison, "ablations": [{"mode": "hybrid", **quality}]},
        "sdk": {"single_probe_ms": 13390.615, "native_latency_passed": False},
    }


class ReviewMaterialsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "src").mkdir()
        (self.root / "src/example.py").write_text("answer = 42\n", encoding="utf-8")
        self.snapshot = file_hashes(self.root)
        self.request = json.loads((ROOT / "artifacts/verification/round5/windows/requests.json").read_bytes())
        self.request["source_sha256"] = self.snapshot["raw_sha256"]
        self.service = json.loads((ROOT / "artifacts/verification/takeover/t01-service.json").read_bytes())
        self.windows = {
            "checks": dict.fromkeys(WINDOWS_CHECKS, True), "file_hashes": self.snapshot,
            "local_release_checks_passed": True, "competition_submission_ready": False,
            "unit_tests": {"tests_run": 7, "passed": True, "output_tail": "Ran 7 tests in 1s\n\nOK\n"},
            "request_metrics": self.request["metrics"], "request_counts": self.request["observation_counts"],
            "service_workload": self.service,
        }

    def validate(self):
        return validate_windows_evidence(self.snapshot, self.windows, self.request, self.service)

    def test_review_windows_validation_does_not_invent_v11_success(self):
        self.assertTrue(self.validate()["passed"])
        summary = fixture_summary()
        text = render_markdown(summary)
        self.assertEqual(len(slide_sections(summary)), 15)
        for value in (INITIAL_STATUS, SDK_RISK_STATUS, "MemGPT", "FAISS", "nearest-rank", "V11待当前版复验",
                      "仅为反馈组织依据", "不能概括", "13,390.615"):
            self.assertIn(value, text)
        for value in ("INCOMPLETE", "第五轮", "未完成"):
            self.assertNotIn(value, text)
        self.assertEqual(len(OFFICE_NAMES), 2)
        self.assertEqual(len(DOCUMENTS), 4)

    def test_five_metric_block_is_derived_from_evidence(self):
        summary = fixture_summary()
        text = frozen_block(summary["windows"])
        for row in metric_rows(summary):
            for value in row:
                self.assertIn(value, text)
        self.assertIn("Windows 7项通过", text)
        self.assertIn("V11部署待独立复验", text)

    def test_stale_source_or_failed_check_rejected(self):
        self.windows["file_hashes"] = deepcopy(self.snapshot)
        self.windows["file_hashes"]["lf_sha256"]["src/example.py"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "measured source"):
            self.validate()
        self.windows["file_hashes"] = self.snapshot
        self.windows["checks"]["privacy_scan"] = False
        with self.assertRaisesRegex(ValueError, "engineering"):
            self.validate()

    def test_request_details_and_test_count_are_recomputed(self):
        self.windows["unit_tests"]["tests_run"] = 8
        with self.assertRaisesRegex(ValueError, "test count"):
            self.validate()
        self.windows["unit_tests"]["tests_run"] = 7
        self.request["metrics"]["preference_accuracy"] = .84
        with self.assertRaisesRegex(ValueError, "request details"):
            self.validate()

    def test_reported_windows_and_service_counts_must_be_genuine(self):
        self.request["environment"]["system"] = "Linux"
        with self.assertRaisesRegex(ValueError, "request details"):
            self.validate()
        self.request["environment"]["system"] = "Windows"
        self.service["results"][1]["correct_queries"]["http"] -= 1
        with self.assertRaisesRegex(ValueError, "target counts"):
            self.validate()

    def test_official_flag_is_not_inferred_from_local_passes(self):
        self.windows["competition_submission_ready"] = True
        with self.assertRaisesRegex(ValueError, "overstated"):
            self.validate()

    def test_current_summary_is_bound_and_outputs_refuse_overwrite(self):
        summary = fixture_summary()
        output = self.root / "review"
        with patch("scripts.generate_review_materials.build_summary", return_value=summary):
            self.assertEqual(main(["--output-dir", str(output)]), 0)
            report = verify_outputs(self.root, output, require_office=False)
            self.assertTrue(report["passed"])
            for key in ("competition_ready", "native_latency_passed", "complex_quality_targets_met",
                        "v11_current_source_verified"):
                self.assertIs(report[key], False)
            with self.assertRaisesRegex(ValueError, "overwrite"):
                main(["--output-dir", str(output)])
            (output / "current_report.md").write_text("forged\n", encoding="utf-8")
            self.assertFalse(verify_outputs(self.root, output, require_office=False)["passed"])

    def test_allowlist_separates_current_public_material_from_historical_dependencies(self):
        legacy = json.loads((ROOT / "submission/submission_manifest.json").read_bytes())
        manifest = make_manifest(legacy)
        public = {name for section in manifest["public_sections"] for name in section["files"]}
        source = set(manifest["source_section"]["files"]) | public
        historical = {name for section in legacy["public_sections"] for name in section["files"]}
        self.assertTrue(historical.issubset(source))
        self.assertFalse(any(name.startswith(("deliverables/doc/", "deliverables/ppt/")) for name in public))
        self.assertTrue(set(DOCUMENTS).issubset(public))
        self.assertEqual(manifest["source_section"]["target"], "03_源代码与说明/project")
        self.assertEqual(manifest["external_inputs"], legacy["external_inputs"])

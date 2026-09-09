import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.generate_takeover_materials import (
    CORE_CHECKS, EVIDENCE, OFFICE_NAMES, WINDOWS_CHECKS, build_summary,
    controller_source_identity, file_hashes, main, render_markdown, sections, verify_outputs,
)
from os_agent_memory.experiments import decay_diagnostics
from scripts.material_status import INITIAL_STATUS

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_fixture(root):
    (root / "src").mkdir()
    (root / "src/example.py").write_text("answer = 42\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = 'test-fixture'\n", encoding="utf-8")
    dataset = root / "data/eval/request_regression_v1.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_bytes((ROOT / "data/eval/request_regression_v1.json").read_bytes())
    snapshot = file_hashes(root)
    request = json.loads((ROOT / "artifacts/verification/round5/windows/requests.json").read_bytes())
    request["source_sha256"] = {name: value for name, value in snapshot["raw_sha256"].items()
                                if name.startswith("src/") and name.endswith(".py")}
    service = json.loads((ROOT / "artifacts/verification/takeover/t01-service.json").read_bytes())
    ready = json.loads((ROOT / "artifacts/verification/takeover/t03-windows-readiness.json").read_bytes())
    ready["controller_source_sha256"] = controller_source_identity(root)["sha256"]
    action = {"execution_completed": True, "official_accuracy_verified": False,
              "posthoc_mode": "fixture_exact", "sessions": 5, "turns": 50,
              "protocol": {"cross_session_verified": True, "probe_files": 12, "slot_checks": 50},
              "posthoc": {"passed": True}}
    log = "Ran 7 tests in 1.0s\n\nOK\n"
    windows = {
        "generated_at_utc": "2026-09-09T00:00:00+00:00",
        "checks": {name: True for name in WINDOWS_CHECKS},
        "local_release_checks_passed": True, "competition_submission_ready": False,
        "file_hashes": snapshot, "unit_tests": {"tests_run": 7, "passed": True, "output_tail": log},
    }
    kylin = {
        "generated_at_utc": windows["generated_at_utc"], "file_hashes": snapshot,
        "installed": True, "required_v11_verified": True, "core_checks_passed": True,
        "source_unchanged_during_checks": True, "tests_passed": True,
        "official_validation_ready": False, "root_filesystem": "/dev/sda3 ext4",
        "system": "Linux", "python": "3.12.3", "machine": "x86_64", "virtualization": "vmware",
        "checks": {name: {"returncode": 0} for name in CORE_CHECKS}, "tests_run": 7,
        "compatibility": {"operating_system": {"os_release": {"ID": "kylin", "VERSION_ID": "v11"}},
                          "resources": {"logical_cpu_count": 4, "physical_memory_gb": 5.787}},
    }
    for name in ("windows", "kylin"):
        folder = root / EVIDENCE / name
        for filename, value in (("requests.json", request), ("service_workload.json", service),
                                ("action-readiness.json", ready), ("actions.json", action),
                                ("ablations.json", {"decay_diagnostics": decay_diagnostics()})):
            write_json(folder / filename, value)
    write_json(root / EVIDENCE / "windows/final_verification.json", windows)
    write_json(root / EVIDENCE / "kylin/kylin_vm.json", kylin)
    (root / EVIDENCE / "kylin/unit_tests.log").write_text(log, encoding="utf-8")
    acceptance = Path("artifacts/verification/x01-x02/organizer_acceptance_reported_20260909.json")
    write_json(root / acceptance, {"reported_organizer_acceptance": True, "organizer_acceptance_verified": False})


class TakeoverMaterialsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        prepare_fixture(self.root)

    def mutate(self, relative, callback):
        path = self.root / EVIDENCE / relative
        value = json.loads(path.read_bytes())
        callback(value)
        write_json(path, value)

    def test_matching_evidence_generates_fifteen_sections_with_honest_limits(self):
        summary = build_summary(self.root)
        self.assertFalse(summary["competition_ready"])
        self.assertEqual(summary["requests"]["windows"]["observation_counts"]["knowledge_recall"], 60)
        self.assertEqual(len(sections(summary)), 15)
        self.assertEqual(len(OFFICE_NAMES), 2)
        text = render_markdown(summary)
        for value in (INITIAL_STATUS, "HashEmbedding", "V11", "68", "60", "80", "50", "500ms",
                      "独立", "7分钟", "--output", "半衰期", "生命周期峰值"):
            self.assertIn(value, text)

    def test_summary_flags_cannot_override_failed_request_details(self):
        self.mutate("windows/requests.json", lambda row: row["metrics"].update(preference_accuracy=.84))
        with self.assertRaisesRegex(ValueError, "request details"):
            build_summary(self.root)

    def test_workload_needs_target_counts_and_available_process_rss(self):
        path = self.root / EVIDENCE / "kylin/service_workload.json"
        original = json.loads(path.read_bytes())
        for mutate in (
            lambda row: row["results"][1]["correct_queries"].update(http=9),
            lambda row: row["results"][0]["process_resources"].update(available=False),
        ):
            changed = copy.deepcopy(original)
            mutate(changed)
            write_json(path, changed)
            with self.assertRaises(ValueError):
                build_summary(self.root)

    def test_stale_source_snapshot_is_rejected(self):
        (self.root / "src/example.py").write_text("answer = 43\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "measured source"):
            build_summary(self.root)

    def test_v11_name_or_aggregate_flag_is_not_installation_evidence(self):
        self.mutate("kylin/kylin_vm.json", lambda row: row.update(root_filesystem="overlay overlay"))
        with self.assertRaisesRegex(ValueError, "V11"):
            build_summary(self.root)

    def test_test_count_must_match_actual_completion_log(self):
        self.mutate("windows/final_verification.json", lambda row: row["unit_tests"].update(tests_run=99))
        with self.assertRaisesRegex(ValueError, "test count"):
            build_summary(self.root)

    def test_readiness_and_fixture_cannot_claim_official_execution(self):
        self.mutate("kylin/action-readiness.json", lambda row: row.update(agent_executed=True))
        with self.assertRaisesRegex(ValueError, "readiness"):
            build_summary(self.root)

    def test_current_materials_refuse_overwrite_and_detect_evidence_byte_changes(self):
        output = self.root / "deliverables/current"
        with patch("scripts.generate_takeover_materials.ROOT", self.root):
            self.assertEqual(main(["--output-dir", str(output)]), 0)
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                main(["--output-dir", str(output)])
        path = self.root / EVIDENCE / "windows/requests.json"
        path.write_bytes(path.read_bytes() + b"\n")
        report = verify_outputs(self.root, output, require_office=False)
        self.assertFalse(report["passed"])
        self.assertIn("summary_does_not_match_current_evidence", report["issues"])

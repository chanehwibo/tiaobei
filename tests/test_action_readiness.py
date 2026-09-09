from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory import action_readiness as readiness
from os_agent_memory.action_evaluation import make_cross_session_sample
from os_agent_memory.action_judging import controller_source_identity, digest_json
from os_agent_memory.bounded_command import CommandFailure
from scripts import check_action_readiness as cli


class ActionReadinessTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
        self.sample = make_cross_session_sample()
        self.manifest = {
            "schema": "action_run_manifest_v1", "run_id": "readiness-test", "purpose": "integration",
            "frozen_at_utc": "2026-01-01T00:00:00Z", "sample_sha256": digest_json(self.sample),
            "controller_source_sha256": controller_source_identity(self.root)["sha256"],
            "roles": {"agent_operator": "operator", "judge_operator": "reviewer", "label_custodian": "custodian"},
            "agent": {"image": "sha256:" + "a" * 64,
                      "model": {"id": "agent", "revision": "v1", "artifact_sha256": "b" * 64}},
            "judge": {"image": "sha256:" + "c" * 64,
                      "model": {"id": "judge", "revision": "v1", "artifact_sha256": "d" * 64}},
        }
        self.server = {"version": "28.0.4", "os": "linux", "architecture": "x86_64",
                       "cpus": 4, "memory_bytes": 6 * 1024**3}
        self.calls = []
        for target, value in (
            ("platform.system", "Linux"), ("platform.machine", "x86_64"),
            ("_os_release", {"ID": "kylin", "VERSION_ID": "V11"}),
            ("shutil.which", "/usr/bin/docker"),
        ):
            mocked = patch("os_agent_memory.action_readiness." + target, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def runner(self, argv, **kwargs):
        self.calls.append(argv)
        self.assertEqual(kwargs, {"timeout": 15, "max_stdout": 16384, "max_stderr": 4096})
        if argv[1] == "info":
            row = self.server
        else:
            self.assertEqual(argv[1:3], ["image", "inspect"])
            self.assertIn(argv[-1], [self.manifest[role]["image"] for role in ("agent", "judge")])
            row = {"id": argv[-1], "os": "linux", "architecture": "amd64", "size_bytes": 9 * 1024**3}
        return subprocess.CompletedProcess(argv, 0, json.dumps(row), "")

    def inspect(self, **kwargs):
        return readiness.inspect_readiness(self.root, sample=self.sample, manifest=self.manifest,
                                          runner=self.runner, **kwargs)

    def test_static_success_never_certifies_runtime_or_image_size_as_ram(self):
        result = self.inspect()
        self.assertTrue(result["static_prerequisites_passed"])
        self.assertFalse(result["competition_submission_ready"])
        self.assertFalse(result["agent_executed"])
        self.assertFalse(result["independent_judge_executed"])
        self.assertFalse(result["runtime_requirements_not_verified"]["model_peak_rss_and_context_fit"])
        self.assertEqual(len(self.calls), 3)
        self.assertTrue(all(row[1] in {"info", "image"} for row in self.calls))

    def test_podman_uses_its_own_structured_template(self):
        self.assertTrue(self.inspect(engine="podman")["static_prerequisites_passed"])
        self.assertIn(".Host.CPUs", self.calls[0][-1])

    def test_absent_inputs_and_engine_remain_missing(self):
        with patch("os_agent_memory.action_readiness.shutil.which", return_value=None):
            result = readiness.inspect_readiness(self.root, runner=self.runner)
        self.assertEqual(result["manifest_error"], "frozen_run_inputs_missing")
        self.assertFalse(result["static_prerequisites_passed"])
        self.assertEqual(self.calls, [])

    def test_invalid_future_or_mismatched_manifest_never_inspects_images(self):
        original = deepcopy(self.manifest)
        for mutate in (
            lambda m: m.update(sample_sha256="0" * 64),
            lambda m: m["agent"].update(image="latest"),
            lambda m: m.update(frozen_at_utc=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()),
        ):
            self.manifest = deepcopy(original)
            mutate(self.manifest)
            self.calls.clear()
            result = self.inspect()
            self.assertEqual(result["manifest_error"], "frozen_manifest_invalid")
            self.assertEqual(len(self.calls), 1)
            self.assertFalse(result["static_prerequisites_passed"])

    def test_controller_changes_and_wrong_environment_fail(self):
        self.manifest["controller_source_sha256"] = "0" * 64
        with patch("os_agent_memory.action_readiness.platform.system", return_value="Windows"):
            result = self.inspect()
        self.assertFalse(result["checks"]["controller_source_matches_freeze"])
        self.assertFalse(result["checks"]["required_v11_identity"])

    def test_engine_capacity_and_architecture_are_not_assumed(self):
        for key, value in (("cpus", 1), ("memory_bytes", 1024**3), ("architecture", "arm64"), ("os", "windows")):
            original = self.server[key]
            self.server[key] = value
            self.assertFalse(self.inspect()["static_prerequisites_passed"])
            self.server[key] = original

    def test_bad_engine_results_are_bounded_and_not_echoed(self):
        for value in ("", "private-local-path", '{"version":1,"version":2}', "[]"):
            result = readiness.inspect_readiness(
                self.root, runner=lambda *_a, **_k: subprocess.CompletedProcess([], 0, value, "private-stderr"))
            self.assertFalse(result["engine"]["valid"])
            self.assertNotIn("private-", json.dumps(result))
        for failure in (CommandFailure("command_timeout"), OSError("private-local-path")):
            with patch.object(readiness, "run_bounded", side_effect=failure) as runner:
                result = readiness.inspect_readiness(self.root, runner=runner)
            self.assertFalse(result["engine"]["valid"])
            self.assertNotIn("private-local-path", json.dumps(result))

    def test_booleans_and_extra_inventory_fields_are_rejected(self):
        for update in ({"cpus": True}, {"memory_bytes": "6000"}, {"unexpected": "private-value"}):
            original = dict(self.server)
            self.server.update(update)
            self.assertFalse(self.inspect()["engine"]["valid"])
            self.server = original

    def test_image_must_match_exact_id_os_and_architecture(self):
        for changed in ({"id": "sha256:" + "f" * 64}, {"os": "windows"}, {"architecture": "arm64"}):
            def runner(argv, **kwargs):
                completed = self.runner(argv, **kwargs)
                if argv[1] == "image":
                    completed.stdout = json.dumps({**json.loads(completed.stdout), **changed})
                return completed
            result = readiness.inspect_readiness(self.root, sample=self.sample, manifest=self.manifest, runner=runner)
            self.assertFalse(result["checks"]["agent_image_matches_pin"])
            self.assertFalse(result["checks"]["judge_image_matches_pin"])

    def test_source_change_during_inspection_is_detected(self):
        def runner(argv, **kwargs):
            result = self.runner(argv, **kwargs)
            (self.root / "pyproject.toml").write_text("changed\n", encoding="utf-8")
            return result
        result = readiness.inspect_readiness(self.root, sample=self.sample, manifest=self.manifest, runner=runner)
        self.assertFalse(result["checks"]["source_unchanged_during_inspection"])

    def test_invalid_engine_and_partial_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            readiness.inspect_readiness(self.root, engine="docker; echo")
        with self.assertRaises(ValueError):
            readiness.inspect_readiness(self.root, sample=self.sample)

    def test_cli_preserves_prior_evidence_and_never_returns_acceptance(self):
        output = self.root / "readiness.json"
        with patch.object(cli, "inspect_readiness", return_value={
            "static_prerequisites_passed": True, "missing_static_prerequisites": [],
            "competition_submission_ready": False,
        }), patch("builtins.print"):
            self.assertEqual(cli.main(["--output", str(output)]), 3)
            original = output.read_bytes()
            self.assertEqual(cli.main(["--output", str(output)]), 2)
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

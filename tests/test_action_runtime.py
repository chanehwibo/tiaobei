import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_action_runtime", ROOT / "scripts/check_action_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class ActionRuntimeTest(unittest.TestCase):
    def setUp(self):
        system = patch.object(runtime.platform, "system", return_value="Linux")
        system.start()
        self.addCleanup(system.stop)

    def test_missing_engines_never_trigger_installation_or_model_calls(self):
        with patch.object(runtime.shutil, "which", return_value=None), \
                patch.object(runtime.subprocess, "run") as run:
            report = runtime.inventory()
        run.assert_not_called()
        self.assertFalse(any(report["commands_on_path"].values()))
        self.assertFalse(report["agent_executed"])
        self.assertFalse(report["independent_judge_executed"])
        self.assertFalse(report["organizer_acceptance_verified"])

    def test_secrets_are_only_presence_booleans_and_engines_are_read_only(self):
        def which(name):
            return name if name == "docker" else None
        with patch.object(runtime.shutil, "which", side_effect=which), \
                patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess(
                    ["docker"], 0, stdout="28.0.4\n")) as run, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "do-not-publish-this-value"}):
            report = runtime.inventory()
        self.assertEqual(run.call_args.args[0], ["docker", "info", "--format", "{{.ServerVersion}}"])
        self.assertTrue(report["model_environment_present"]["OPENAI_API_KEY"])
        self.assertNotIn("do-not-publish-this-value", json.dumps(report))
        self.assertTrue(report["engines"]["docker"]["reachable"])
        self.assertFalse(report["model_endpoints_contacted"])
        self.assertFalse(report["images_started_or_pulled"])

    def test_unreachable_engine_is_not_accepted_and_errors_are_not_echoed(self):
        with patch.object(runtime.shutil, "which", return_value="engine"), \
                patch.object(runtime.subprocess, "run", side_effect=OSError("private error detail")):
            report = runtime.inventory()
        self.assertFalse(report["engines"]["docker"]["reachable"])
        self.assertEqual(report["engines"]["docker"]["error_type"], "OSError")
        self.assertNotIn("private error detail", json.dumps(report))


if __name__ == "__main__":
    unittest.main()

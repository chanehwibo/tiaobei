import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.action_evaluation import FactLedger, FixtureAdapter, DockerSample, make_sample, run_sample, judge_actions


class ActionEvaluationTest(unittest.TestCase):
    def test_atomic_slots_and_full_session_protocol(self):
        ledger = FactLedger()
        ledger.record("alpha.format", "csv")
        ledger.record("beta.format", "json")
        with self.assertRaises(ValueError):
            ledger.record("alpha.format", "json")
        ledger.record("alpha.format", "json", update=True)
        with tempfile.TemporaryDirectory() as temp:
            sample = make_sample()
            resets = []
            class Inspect(FixtureAdapter):
                def send(self, payload):
                    self.assertions(payload)
                    resets.append(payload["reset_context"])
                    return super().send(payload)
                def assertions(self, payload):
                    assert set(payload) == {"session", "turn_id", "reset_context", "history", "message"}
                    if payload["reset_context"]:
                        assert not payload["history"]
            workspace = Path(temp) / "sample"
            result = run_sample(sample, workspace, adapter_factory=Inspect)
            self.assertTrue(result["posthoc"]["passed"])
            self.assertEqual(result["posthoc"]["total_files"], 15)
            self.assertEqual(sum(resets), 5)
            self.assertFalse(result["official_accuracy_verified"])
            last = workspace / "outputs/s05-t07.json"
            values = json.loads(last.read_text())
            values["alpha.format"] = "csv"
            last.write_text(json.dumps(values))
            self.assertFalse(judge_actions(workspace, sample["oracle"])["passed"])
            last.unlink()
            self.assertFalse(judge_actions(workspace, sample["oracle"])["passed"])

    def test_oracle_traversal_missing_actions_and_fixture_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            sample = make_sample()
            class Empty(FixtureAdapter):
                def send(self, payload):
                    return {"text": "all tasks completed"}
            result = run_sample(sample, Path(temp) / "empty", adapter_factory=Empty)
            self.assertEqual(result["posthoc"]["correct_files"], 0)
            self.assertFalse(result["posthoc"]["passed"])
            sample["oracle"]["files"] = {"../outside.json": {}}
            self.assertFalse(judge_actions(Path(temp) / "empty", sample["oracle"])["passed"])

    def test_container_is_pinned_offline_scoped_and_no_oracle_mount(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(DockerSample, "command") as command:
                with DockerSample(Path(temp), "sha256:" + "a" * 64, ["/opt/agent-adapter"]):
                    pass
            create = command.call_args_list[1].args[0]
            self.assertIn("--read-only", create)
            self.assertIn("none", create)
            self.assertEqual(create.count("--mount"), 1)
            self.assertEqual(command.call_args_list[-1].args[0][:2], ["rm", "-f"])

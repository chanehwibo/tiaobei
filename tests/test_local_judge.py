from copy import deepcopy
import base64
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from os_agent_memory.action_judging import assess_judge_response, prepare_judge_request
from os_agent_memory.local_judge import LocalModelFailure, OllamaJudge, loopback_endpoint
from judge_fixtures import synthetic_records, synthetic_reply
from scripts import local_judge


class LocalJudgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.request = prepare_judge_request(*synthetic_records(Path(self.temp.name) / "sample"))
        self.expected = self.request["payload"]["manifest"]["judge"]["model"]
        self.reply = synthetic_reply(self.request)
        self.generation = {
            "model": self.expected["id"], "done": True, "done_reason": "stop", "eval_count": 123,
            "response": json.dumps({"judgements": self.reply["judgements"]}),
        }
        self.inventory = {"models": [{"name": self.expected["id"], "digest": self.expected["artifact_sha256"]}]}

    def test_only_literal_loopback_http_and_explicit_ports_are_permitted(self):
        self.assertEqual(loopback_endpoint("http://127.0.0.1:11434"), ("127.0.0.1", 11434))
        self.assertEqual(loopback_endpoint("http://[::1]:11434/"), ("::1", 11434))
        for endpoint in ("https://127.0.0.1:11434", "http://localhost:11434", "http://192.0.2.1:11434",
                         "http://127.0.0.1", "http://127.0.0.1:11434/api", "http://user@127.0.0.1:11434",
                         "http://127.0.0.1:11434?key=value", "http://127.0.0.1:99999", None):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                loopback_endpoint(endpoint)

    def test_pinned_local_model_is_checked_before_and_after_generation(self):
        calls = []
        def request_json(method, path, payload=None):
            calls.append((method, path, payload))
            return self.inventory if path == "/api/tags" else self.generation
        judge = OllamaJudge()
        with patch.object(judge, "request_json", side_effect=request_json):
            reply = judge.judge(self.request)
        self.assertEqual([(m, p) for m, p, _ in calls],
                         [("GET", "/api/tags"), ("POST", "/api/generate"), ("GET", "/api/tags")])
        prompt = calls[1][2]
        self.assertFalse(prompt["stream"])
        self.assertEqual(prompt["options"]["temperature"], 0)
        self.assertEqual(prompt["format"]["properties"]["judgements"]["minItems"], 76)
        self.assertIn("untrusted DATA", prompt["system"])
        receipt = reply["runtime_receipt"]
        self.assertEqual(receipt["completion_sha256"],
                         hashlib.sha256(self.generation["response"].encode()).hexdigest())
        result = assess_judge_response(self.request, reply)
        self.assertTrue(result["all_checks_passed"])
        self.assertTrue(result["independent_llm_judge"]["model_execution_reported"])
        self.assertFalse(result["independent_llm_judge"]["model_identity_verified"])
        self.assertFalse(result["independent_llm_judge"]["executed"])
        self.assertFalse(result["competition_submission_ready"])

    def test_unloaded_unpinned_duplicate_models_do_not_trigger_generation_or_pull(self):
        for inventory in ({}, {"models": []}, {"models": [self.inventory["models"][0]] * 2},
                          {"models": [{"name": self.expected["id"], "digest": "f" * 64}]}):
            judge = OllamaJudge()
            with patch.object(judge, "request_json", return_value=inventory) as call, \
                    self.assertRaises(LocalModelFailure):
                judge.judge(self.request)
            self.assertEqual(call.call_args_list[0].args, ("GET", "/api/tags"))
            self.assertEqual(call.call_count, 1)

    def test_mid_generation_model_replacement_is_rejected(self):
        judge = OllamaJudge()
        after = deepcopy(self.inventory)
        after["models"][0]["digest"] = "f" * 64
        with patch.object(judge, "request_json", side_effect=[self.inventory, self.generation, after]), \
                self.assertRaisesRegex(LocalModelFailure, "digest_mismatch"):
            judge.judge(self.request)

    def test_truncated_wrong_model_or_incomplete_generation_never_scores(self):
        for key, value in (("done", False), ("done_reason", "length"), ("model", "other-model"),
                           ("eval_count", True), ("eval_count", 0), ("response", None)):
            generated = {**self.generation, key: value}
            judge = OllamaJudge()
            with self.subTest(key=key, value=value), \
                    patch.object(judge, "request_json", side_effect=[self.inventory, generated]), \
                    self.assertRaises(LocalModelFailure):
                judge.judge(self.request)

    def test_duplicate_json_and_missing_judgements_are_not_retried(self):
        for raw in ('{"judgements":[],"judgements":[]}', '{"judgements":[]}', '{"score":1}'):
            judge = OllamaJudge()
            generated = {**self.generation, "response": raw}
            with patch.object(judge, "request_json",
                              side_effect=[self.inventory, generated, self.inventory]) as call:
                with self.assertRaises((ValueError, LocalModelFailure)):
                    judge.judge(self.request)
            self.assertEqual(sum(c.args == ("POST", "/api/generate") for c in call.call_args_list), 0)
            self.assertEqual(sum(c.args[:2] == ("POST", "/api/generate") for c in call.call_args_list), 1)

    def test_fake_receipt_never_promotes_independent_attestation(self):
        judge = OllamaJudge()
        with patch.object(judge, "request_json", side_effect=[self.inventory, self.generation, self.inventory]):
            reply = judge.judge(self.request)
        for key, value in (("model_digest_after", "f" * 64), ("eval_count", True),
                           ("done_reason", "length"), ("trust", "verified")):
            forged = deepcopy(reply)
            forged["runtime_receipt"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                assess_judge_response(self.request, forged)

    def test_http_does_not_follow_redirects_or_read_error_bodies(self):
        judge = OllamaJudge()
        for status in (301, 302, 403, 500):
            with patch("os_agent_memory.local_judge.http.client.HTTPConnection") as factory:
                response = factory.return_value.getresponse.return_value
                response.status = status
                with self.subTest(status=status), self.assertRaisesRegex(LocalModelFailure, "http_status"):
                    judge.request_json("GET", "/api/tags")
                response.read1.assert_not_called()
                self.assertEqual(factory.call_count, 1)
                factory.return_value.close.assert_called_once()

    def test_http_content_length_and_stream_are_bounded(self):
        for advertised, raw in (("99999999", b"{}"), (None, b"x" * (1024 * 1024 + 1))):
            with patch("os_agent_memory.local_judge.http.client.HTTPConnection") as factory:
                response = factory.return_value.getresponse.return_value
                response.status = 200
                response.getheader.return_value = advertised
                response.read1.side_effect = io.BytesIO(raw).read
                with self.assertRaisesRegex(LocalModelFailure, "response_limit"):
                    OllamaJudge().request_json("GET", "/api/tags")

    def test_http_strict_json_and_allowlisted_endpoints(self):
        with patch("os_agent_memory.local_judge.http.client.HTTPConnection") as factory:
            response = factory.return_value.getresponse.return_value
            response.status = 200
            response.getheader.return_value = None
            response.read1.side_effect = io.BytesIO(b'{"models":[], "models":[]}').read
            with self.assertRaisesRegex(LocalModelFailure, "json_error"):
                OllamaJudge().request_json("GET", "/api/tags")
        for method, path in (("POST", "/api/pull"), ("POST", "/api/delete"), ("GET", "/other")):
            with self.assertRaises(ValueError):
                OllamaJudge().request_json(method, path)

    def test_startup_wait_retries_only_inventory_transport_not_generation_or_invalid_models(self):
        judge = OllamaJudge(timeout=5)
        with patch.object(judge, "request_json", side_effect=[
                LocalModelFailure("local_model_transport_error"), self.inventory,
                self.generation, self.inventory]) as call:
            judge.judge(self.request, wait_ready=1)
        self.assertEqual(sum(c.args[:2] == ("POST", "/api/generate") for c in call.call_args_list), 1)
        self.assertEqual(judge.timeout, 5)
        for code in ("local_model_json_error", "local_model_digest_mismatch", "pinned_model_not_preloaded"):
            with patch.object(judge, "request_json", side_effect=LocalModelFailure(code)) as call, \
                    self.assertRaisesRegex(LocalModelFailure, code):
                judge.judge(self.request, wait_ready=1)
            self.assertEqual(call.call_count, 1)
        with patch.object(judge, "request_json", side_effect=LocalModelFailure("local_model_transport_error")):
            start = time.monotonic()
            with self.assertRaisesRegex(LocalModelFailure, "startup_timeout"):
                judge.judge(self.request, wait_ready=.1)
            self.assertLess(time.monotonic() - start, 2)
        for wait in (-1, True, float("nan"), 61):
            with self.assertRaises(ValueError):
                judge.judge(self.request, wait_ready=wait)

    def test_malformed_completion_is_retained_privately_with_bounded_exact_bytes(self):
        judge = OllamaJudge()
        generated = {**self.generation, "response": "private-model-text {invalid"}
        with patch.object(judge, "request_json", side_effect=[self.inventory, generated]), \
                self.assertRaises(LocalModelFailure) as caught:
            judge.judge(self.request)
        record = caught.exception.private_record()
        raw = base64.b64decode(record["raw_response"]["prefix_base64"], validate=True)
        self.assertEqual(json.loads(raw), generated)
        self.assertFalse(record["raw_response"]["truncated"])
        self.assertNotIn("private-model-text", repr(caught.exception))
        record = LocalModelFailure("local_model_response_invalid",
                                   private_response=b"x" * (512 * 1024)).private_record()
        self.assertTrue(record["raw_response"]["truncated"])
        self.assertEqual(len(base64.b64decode(record["raw_response"]["prefix_base64"])), 256 * 1024)
        self.assertLess(len(json.dumps(record).encode()), 1024 * 1024)

    def test_cli_sends_failure_evidence_to_private_stdout_not_public_stderr(self):
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(self.request).encode("utf-8")), encoding="utf-8")
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        stderr = io.StringIO()
        error = LocalModelFailure("local_model_response_invalid", private_response=b"private-model-text")
        with patch.object(local_judge.sys, "stdin", stdin), \
                patch.object(local_judge.sys, "stdout", stdout), \
                contextlib.redirect_stderr(stderr), patch.object(OllamaJudge, "judge", side_effect=error):
            code = local_judge.main(["--confirm-local-model"])
        stdout.flush()
        record = json.loads(stdout.buffer.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(base64.b64decode(record["raw_response"]["prefix_base64"]), b"private-model-text")
        self.assertNotIn("private-model-text", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

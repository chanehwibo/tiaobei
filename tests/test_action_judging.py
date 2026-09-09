import contextlib
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
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
from os_agent_memory import action_judging as judging
from os_agent_memory.action_evaluation import load_json
from scripts import evaluate_actions, judge_actions
from judge_fixtures import synthetic_records, synthetic_reply


class ActionJudgingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sample, self.evidence, self.manifest = synthetic_records(self.root / "sample")
        self.request = judging.prepare_judge_request(self.sample, self.evidence, self.manifest)

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def test_all_slots_are_scored_without_claiming_independence_or_five_metrics(self):
        result = judging.assess_judge_response(self.request, synthetic_reply(self.request))
        self.assertTrue(result["all_checks_passed"])
        self.assertEqual(result["metrics"]["action_slot"], {"correct": 50, "total": 50, "rate": 1})
        self.assertEqual(result["metrics"]["memory_slot"]["total"], 10)
        self.assertEqual(result["metrics"]["reply_consistency"]["total"], 12)
        self.assertEqual(len(result["judgements"]), 76)
        self.assertEqual(len(result["human_review"]["required_ids"]), 8)
        self.assertFalse(result["human_review"]["completed"])
        self.assertFalse(result["independent_llm_judge"]["executed"])
        self.assertFalse(result["independent_llm_judge"]["adapter_executed"])
        self.assertFalse(result["official_five_metrics_verified"])
        self.assertFalse(result["third_party_blind_verified"])
        self.assertFalse(result["competition_submission_ready"])
        self.assertFalse(result["external_side_effects_verified"])

    def test_manifest_binds_sample_source_image_and_pre_execution_time(self):
        for key, bad in (("sample_sha256", "0" * 64), ("controller_source_sha256", "bad"),
                         ("purpose", []), ("frozen_at_utc", "2026-09-01")):
            manifest = deepcopy(self.manifest)
            manifest[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                judging.prepare_judge_request(self.sample, self.evidence, manifest)
        for key, bad in (("run_manifest_sha256", "0" * 64), ("controller_source_sha256", "0" * 64),
                         ("controller_source_unchanged", False), ("agent_model_declared", {}),
                         ("generated_at_utc", "2999-01-01T00:00:00Z")):
            evidence = deepcopy(self.evidence)
            evidence[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                judging.prepare_judge_request(self.sample, evidence, self.manifest)

    def test_blind_declaration_cannot_relabel_public_fixture_or_reuse_roles_or_models(self):
        manifest = deepcopy(self.manifest)
        manifest["purpose"] = "third_party_blind_declared"
        with self.assertRaises(ValueError):
            judging.validate_manifest(manifest, self.sample)
        sample = deepcopy(self.sample)
        sample["turns"][-1]["message"] += " Please use the remembered settings."
        manifest["sample_sha256"] = judging.digest_json(sample)
        self.assertFalse(judging.validate_manifest(manifest, sample)["declarations_verified"])
        for kind in ("roles", "model"):
            bad = deepcopy(manifest)
            if kind == "roles":
                bad["roles"]["judge_operator"] = bad["roles"]["agent_operator"]
            else:
                bad["judge"]["model"] = deepcopy(bad["agent"]["model"])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                judging.validate_manifest(bad, sample)

    def test_incomplete_unfrozen_and_fixture_executions_are_not_judge_candidates(self):
        for key, bad in (("execution_completed", False), ("workspace_frozen_before_capture", False),
                         ("oracle_supplied_to_adapter", True), ("scope", ["synthetic_fixture_only"]),
                         ("posthoc_mode", "fixture_exact"), ("turns", True), ("sessions", False)):
            evidence = deepcopy(self.evidence)
            evidence[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                judging.prepare_judge_request(self.sample, evidence, self.manifest)

    def test_transcript_cannot_be_shortened_reordered_or_forge_reset(self):
        for kind in ("short", "order", "reset", "message", "nonfinite", "extra"):
            evidence = deepcopy(self.evidence)
            if kind == "short":
                evidence["trace"].pop()
            elif kind == "order":
                evidence["trace"].reverse()
            elif kind == "reset":
                evidence["trace"][10]["reset_context"] = 1
            elif kind == "message":
                evidence["trace"][0]["message"] = "different prompt"
            elif kind == "nonfinite":
                evidence["trace"][0]["response"]["score"] = float("nan")
            else:
                evidence["trace"][0]["oracle"] = self.sample["oracle"]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                judging.prepare_judge_request(self.sample, evidence, self.manifest)

    def test_container_provenance_is_required_not_an_agent_claim(self):
        for key, bad in (("removed", False), ("image", "sha256:" + "f" * 64),
                         ("guest_identity", {"is_required_v11": False}), ("engine", "shell")):
            evidence = deepcopy(self.evidence)
            evidence["container"][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                judging.prepare_judge_request(self.sample, evidence, self.manifest)

    def test_artifact_tampering_aliases_incomplete_inventory_and_size_are_rejected(self):
        for kind in ("content", "bytes", "hash", "duplicate", "traversal", "missing_row", "large", "inventory"):
            evidence = deepcopy(self.evidence)
            rows = evidence["posthoc"]["artifacts"]
            row = rows[0]
            if kind == "content":
                row["untrusted_content"] += "forged"
            elif kind == "bytes":
                row["bytes"] = True
            elif kind == "hash":
                row["sha256"] = "0" * 64
            elif kind == "duplicate":
                duplicate = deepcopy(row)
                duplicate["path"] = duplicate["path"].upper()
                rows.append(duplicate)
            elif kind == "traversal":
                row["path"] = "outputs/../private"
            elif kind == "missing_row":
                rows[:] = [r for r in rows if r["path"] != "outputs/s02-t01.json"]
            elif kind == "large":
                raw = b"x" * (65536 + 1)
                row.update(untrusted_content=raw.decode(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            else:
                evidence["posthoc"]["inventory_error"] = "workspace_inventory_invalid"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                judging.prepare_judge_request(self.sample, evidence, self.manifest)

    def test_missing_artifacts_score_zero_even_when_model_claims_pass(self):
        evidence = deepcopy(self.evidence)
        row = next(r for r in evidence["posthoc"]["artifacts"] if r["path"] == "outputs/s02-t01.json")
        row.clear()
        row.update(path="outputs/s02-t01.json", state="missing_or_invalid")
        evidence["posthoc"]["all_expected_files_captured"] = False
        request = judging.prepare_judge_request(self.sample, evidence, self.manifest)
        result = judging.assess_judge_response(request, synthetic_reply(request))
        self.assertFalse(result["all_checks_passed"])
        self.assertEqual(result["metrics"]["action_slot"], {"correct": 47, "total": 50, "rate": .94})
        failed = [r for r in result["judgements"] if not r["score"]]
        self.assertEqual(len(failed), 4)
        self.assertTrue(all(r["id"] in result["human_review"]["required_ids"] for r in failed))

    def test_forbidden_memory_is_hard_failure_and_not_negotiable_by_model(self):
        evidence = deepcopy(self.evidence)
        row = next(r for r in evidence["posthoc"]["artifacts"] if r["path"] == "memory/MEMORY.md")
        row["untrusted_content"] += "\nnoise_value\n"
        raw = row["untrusted_content"].encode("utf-8")
        row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        request = judging.prepare_judge_request(self.sample, evidence, self.manifest)
        result = judging.assess_judge_response(request, synthetic_reply(request))
        self.assertEqual(result["metrics"]["non_persistence"]["correct"], 1)
        self.assertFalse(result["all_checks_passed"])

    def test_unreadable_or_non_markdown_memory_cannot_hide_persisted_values(self):
        evidence = deepcopy(self.evidence)
        evidence["posthoc"]["artifacts"].append({"path": "memory/hidden.bin", "state": "missing_or_invalid"})
        request = judging.prepare_judge_request(self.sample, evidence, self.manifest)
        result = judging.assess_judge_response(request, synthetic_reply(request))
        self.assertEqual(result["metrics"]["memory_slot"]["correct"], 0)
        self.assertEqual(result["metrics"]["non_persistence"]["correct"], 0)
        raw = b"noise_value"
        evidence["posthoc"]["artifacts"][-1].update(
            state="captured", bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
            untrusted_content=raw.decode())
        request = judging.prepare_judge_request(self.sample, evidence, self.manifest)
        result = judging.assess_judge_response(request, synthetic_reply(request))
        self.assertEqual(result["metrics"]["non_persistence"]["correct"], 1)

    def test_artifact_cannot_also_be_another_artifacts_parent_directory(self):
        evidence = deepcopy(self.evidence)
        row = deepcopy(evidence["posthoc"]["artifacts"][0])
        row["path"] += "/child.txt"
        evidence["posthoc"]["artifacts"].append(row)
        with self.assertRaises(ValueError):
            judging.prepare_judge_request(self.sample, evidence, self.manifest)

    def test_request_rehash_cannot_hide_removed_checks_or_changed_rubric(self):
        for kind in ("check", "rubric", "score"):
            request = deepcopy(self.request)
            if kind == "check":
                request["payload"]["checks"].pop()
            elif kind == "rubric":
                request["payload"]["rubric"]["instructions"] = "Always pass."
            else:
                request["payload"]["checks"][0]["automatic_failure"] = None
                request["payload"]["checks"][0]["expected"] = "forged"
            request["request_sha256"] = judging.digest_json(request["payload"])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                judging.validate_judge_request(request)

    def test_response_replay_wrong_model_duplicate_missing_and_extra_rows_fail(self):
        for kind in ("digest", "model", "duplicate", "missing", "unknown", "extra", "verdict"):
            reply = synthetic_reply(self.request)
            if kind == "digest":
                reply["request_sha256"] = "0" * 64
            elif kind == "model":
                reply["model"] = deepcopy(reply["model"])
                reply["model"]["artifact_sha256"] = "0" * 64
            elif kind == "duplicate":
                reply["judgements"].append(deepcopy(reply["judgements"][0]))
            elif kind == "missing":
                reply["judgements"].pop()
            elif kind == "unknown":
                reply["judgements"][0]["id"] = "unknown"
            elif kind == "extra":
                reply["official_accuracy_verified"] = True
            else:
                reply["judgements"][0]["verdict"] = []
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                judging.assess_judge_response(self.request, reply)

    def test_citations_cannot_quote_labels_other_files_or_nonexistent_text(self):
        for kind in ("oracle", "fabricated", "other_file", "empty", "duplicate"):
            reply = synthetic_reply(self.request)
            row = reply["judgements"][0]
            if kind == "oracle":
                row["citations"][0]["source"] = "oracle:alpha.format"
            elif kind == "fabricated":
                row["citations"][0]["quote"] = "invented quotation"
            elif kind == "other_file":
                row["citations"][0]["source"] = "artifact:outputs/s03-t01.json"
            elif kind == "empty":
                row["citations"] = []
            else:
                row["citations"].append(deepcopy(row["citations"][0]))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                judging.assess_judge_response(self.request, reply)

    def test_uncertainty_never_disappears_from_denominator(self):
        reply = synthetic_reply(self.request)
        reply["judgements"][0].update(verdict="uncertain", citations=[], reason="Insufficient evidence.")
        result = judging.assess_judge_response(self.request, reply)
        self.assertEqual(result["metrics"]["action_slot"]["total"], 50)
        self.assertEqual(result["metrics"]["action_slot"]["correct"], 49)
        self.assertIn(reply["judgements"][0]["id"], result["human_review"]["required_ids"])

    def review_record(self, reply):
        review = judging.prepare_human_review(self.request, reply)
        expected = {row["id"]: row for row in reply["judgements"]}
        review.update(reviewer="test-human-reviewer",
                      reviewed_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      judgements=[deepcopy(expected[row["id"]]) for row in review["judgements"]])
        return review

    def test_human_review_coverage_does_not_promote_external_identity_or_change_scores(self):
        reply = synthetic_reply(self.request)
        review = self.review_record(reply)
        result = judging.assess_human_review(self.request, reply, review)
        self.assertTrue(result["human_review"]["completed"])
        self.assertFalse(result["human_review"]["reviewer_identity_verified"])
        self.assertEqual(result["metrics"], judging.assess_judge_response(self.request, reply)["metrics"])
        self.assertFalse(result["competition_submission_ready"])
        self.assertFalse(result["independent_llm_judge"]["executed"])
        self.assertFalse(result["third_party_blind_verified"])

    def test_blank_missing_replayed_or_duplicate_human_review_is_rejected(self):
        reply = synthetic_reply(self.request)
        with self.assertRaises(ValueError):
            judging.assess_human_review(self.request, reply, judging.prepare_human_review(self.request, reply))
        for kind in ("missing", "duplicate", "digest", "reviewer", "time", "citation"):
            review = self.review_record(reply)
            if kind == "missing":
                review["judgements"].pop()
            elif kind == "duplicate":
                review["judgements"].append(deepcopy(review["judgements"][0]))
            elif kind == "digest":
                review["response_sha256"] = "0" * 64
            elif kind == "reviewer":
                review["reviewer"] = self.manifest["roles"]["agent_operator"]
            elif kind == "time":
                review["reviewed_at_utc"] = "2999-01-01T00:00:00Z"
            else:
                review["judgements"][0]["citations"] = [{"source": "oracle", "quote": "label"}]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                judging.assess_human_review(self.request, reply, review)

    def test_human_disagreement_is_unresolved_and_does_not_silently_replace_model_score(self):
        reply = synthetic_reply(self.request)
        for verdict in ("fail", "uncertain"):
            review = self.review_record(reply)
            review["judgements"][0].update(verdict=verdict, reason="Needs adjudication.", citations=[])
            result = judging.assess_human_review(self.request, reply, review)
            self.assertTrue(result["human_review"]["coverage_complete"])
            self.assertFalse(result["human_review"]["completed"])
            self.assertIn(review["judgements"][0]["id"], result["human_review"]["unresolved_ids"])
            self.assertTrue(result["all_checks_passed"])
            self.assertEqual(result["metrics"], judging.assess_judge_response(self.request, reply)["metrics"])

    def test_cli_review_template_and_import_never_invoke_a_model(self):
        request = self.write("request.json", self.request)
        reply = synthetic_reply(self.request)
        response = self.write("response.json", reply)
        template, output = self.root / "review-template.json", self.root / "reviewed.json"
        with contextlib.redirect_stdout(io.StringIO()), patch.object(judge_actions, "DockerJudge") as docker:
            self.assertEqual(judge_actions.main(["review-template", "--request", str(request),
                "--response", str(response), "--output", str(template)]), 0)
            review = self.write("review.json", self.review_record(reply))
            self.assertEqual(judge_actions.main(["review", "--request", str(request), "--response", str(response),
                "--review", str(review), "--output", str(output)]), 3)
        docker.assert_not_called()
        self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["human_review"]["completed"])
        self.assertTrue(all(row["verdict"] is None for row in json.loads(
            template.read_text(encoding="utf-8"))["judgements"]))

    def test_strict_json_prevents_duplicate_keys_and_nonfinite_scores(self):
        for raw in ('{"judgements":[],"judgements":[]}', '{"score":NaN}', '{"score":Infinity}'):
            with self.assertRaises(ValueError):
                load_json(raw)

    def test_source_identity_tracks_code_not_old_generated_reports(self):
        root = self.root / "code"
        (root / "src").mkdir(parents=True)
        (root / "pyproject.toml").write_bytes(b"# project\r\n")
        code = root / "src/module.py"
        code.write_bytes(b"VALUE = 1\r\n")
        first = judging.controller_source_identity(root)
        code.write_bytes(b"VALUE = 1\n")
        self.assertEqual(first, judging.controller_source_identity(root))
        (root / "old-report.json").write_text("{}")
        self.assertEqual(first, judging.controller_source_identity(root))
        code.write_bytes(b"VALUE = 2\n")
        self.assertNotEqual(first, judging.controller_source_identity(root))

    def test_cli_prepare_score_validate_and_refuse_overwrite(self):
        sample = self.write("sample.json", self.sample)
        evidence = self.write("evidence.json", self.evidence)
        manifest = self.write("manifest.json", self.manifest)
        request, output = self.root / "request.json", self.root / "assessment.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(judge_actions.main(["prepare", "--sample", str(sample), "--evidence", str(evidence),
                                                "--manifest", str(manifest), "--output", str(request)]), 0)
            self.assertEqual(judge_actions.main(["validate", "--request", str(request)]), 0)
            response = self.write("response.json", synthetic_reply(self.request))
            args = ["score", "--request", str(request), "--response", str(response), "--output", str(output)]
            self.assertEqual(judge_actions.main(args), 3)
            original = output.read_bytes()
            self.assertEqual(judge_actions.main(args), 2)
        self.assertEqual(original, output.read_bytes())

    def test_cli_freeze_binds_current_source_and_does_not_start_a_container(self):
        sample = self.write("sample.json", self.sample)
        identities = self.write("identities.json", {k: self.manifest[k] for k in (
            "run_id", "purpose", "roles", "agent", "judge")})
        output = self.root / "manifest.json"
        with patch.object(judge_actions, "DockerJudge") as docker, contextlib.redirect_stdout(io.StringIO()):
            code = judge_actions.main(["freeze", "--sample", str(sample), "--identities", str(identities),
                                       "--output", str(output)])
        self.assertEqual(code, 0)
        docker.assert_not_called()
        manifest = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(manifest["controller_source_sha256"], judging.controller_source_identity(ROOT)["sha256"])
        self.assertEqual(manifest["sample_sha256"], judging.digest_json(self.sample))

    def test_cli_rejects_host_judge_execution_and_symlinked_input_before_start(self):
        request = self.write("request.json", self.request)
        with patch.object(judge_actions.platform, "system", return_value="Windows"), \
                patch.object(judge_actions, "DockerJudge") as docker, contextlib.redirect_stdout(io.StringIO()):
            code = judge_actions.main(["run", "--request", str(request), "--output", str(self.root / "out.json"),
                "--raw-output", str(self.root / "raw.json"), "--judge-argv", '["/opt/judge"]',
                "--confirm-isolated-guest"])
        self.assertEqual(code, 2)
        docker.assert_not_called()
        self.assertFalse((self.root / "raw.json").exists())
        with patch.object(judge_actions.FileMemory, "_check_path", side_effect=ValueError()):
            with self.assertRaises(ValueError):
                judge_actions.read_private(request)

    def test_judge_container_is_separate_readonly_no_network_and_has_no_mounts(self):
        with patch.object(judging.DockerJudge, "command") as command:
            with judging.DockerJudge("sha256:" + "b" * 64, ["/opt/judge"]):
                pass
        create = command.call_args_list[1].args[0]
        self.assertIn("--read-only", create)
        self.assertIn("none", create)
        self.assertNotIn("--mount", create)
        self.assertNotIn(str(self.root), " ".join(create))
        self.assertTrue(create[2].startswith("tiaobei-judge-"))
        self.assertEqual(command.call_args_list[-1].args[0][:2], ["rm", "-f"])

    def test_judge_start_failure_cleans_only_owned_container(self):
        for stage in ("create", "start"):
            calls = []
            def command(argv, **_):
                calls.append(argv)
                if argv[0] == stage:
                    raise OSError()
            with self.subTest(stage=stage), patch.object(judging.DockerJudge, "command", side_effect=command):
                with self.assertRaises(OSError):
                    with judging.DockerJudge("sha256:" + "b" * 64, ["/opt/judge"]):
                        pass
            self.assertEqual(calls[-1][:2], ["rm", "-f"])
            self.assertTrue(calls[-1][2].startswith("tiaobei-judge-"))

    def test_optional_model_service_starts_only_in_owned_networkless_container(self):
        with patch.object(judging.DockerJudge, "command") as command:
            with judging.DockerJudge("sha256:" + "b" * 64, ["/opt/judge"],
                                     service_command=["/usr/bin/ollama", "serve"]) as judge:
                self.assertFalse(judge.removed)
        calls = [call.args[0] for call in command.call_args_list]
        self.assertEqual(calls[3], ["exec", "-d", judge.name, "/usr/bin/ollama", "serve"])
        self.assertIn("OLLAMA_MODELS=/opt/judge/models", calls[1])
        self.assertIn("OLLAMA_HOST=127.0.0.1:11434", calls[1])
        self.assertTrue(judge.removed)
        for argv in ("ollama serve", [], ["ollama", "serve"], ["/usr/bin/ollama", "bad\x00arg"]):
            with patch.object(judging.DockerJudge, "command") as command, self.assertRaises(ValueError):
                with judging.DockerJudge("sha256:" + "b" * 64, ["/opt/judge"], service_command=argv):
                    pass
            command.assert_not_called()

    def test_cli_mocked_judge_run_retains_raw_reply_but_does_not_claim_llm_execution(self):
        request = self.write("request.json", self.request)
        raw, report = self.root / "raw.json", self.root / "report.json"
        reply = json.dumps(synthetic_reply(self.request))
        def command(argv, **kwargs):
            if argv[0] == "exec":
                self.assertEqual(load_json(kwargs["input"]), self.request)
                return subprocess.CompletedProcess(argv, 0, stdout=reply)
            return subprocess.CompletedProcess(argv, 0, stdout="{}")
        with patch.object(judge_actions.platform, "system", return_value="Linux"), \
                patch.object(judge_actions, "_os_release", return_value={"ID": "kylin", "VERSION_ID": "v11"}), \
                patch.object(judging.DockerJudge, "command", side_effect=command), \
                contextlib.redirect_stdout(io.StringIO()):
            code = judge_actions.main(["run", "--request", str(request), "--output", str(report),
                "--raw-output", str(raw), "--judge-argv", '["/opt/judge"]', "--confirm-isolated-guest"])
        self.assertEqual(code, 3)
        self.assertEqual(raw.read_text(encoding="utf-8"), reply)
        result = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(result["independent_llm_judge"]["adapter_executed"])
        self.assertFalse(result["independent_llm_judge"]["executed"])
        self.assertFalse(result["competition_submission_ready"])

    def test_cli_invalid_model_json_is_saved_and_not_retried(self):
        request = self.write("request.json", self.request)
        raw, report = self.root / "invalid-raw.json", self.root / "failed.json"
        calls = []
        def command(argv, **_):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="not valid JSON")
        with patch.object(judge_actions.platform, "system", return_value="Linux"), \
                patch.object(judge_actions, "_os_release", return_value={"ID": "kylin", "VERSION_ID": "v11"}), \
                patch.object(judging.DockerJudge, "command", side_effect=command), \
                contextlib.redirect_stdout(io.StringIO()):
            code = judge_actions.main(["run", "--request", str(request), "--output", str(report),
                "--raw-output", str(raw), "--judge-argv", '["/opt/judge"]', "--confirm-isolated-guest"])
        self.assertEqual(code, 2)
        self.assertEqual(sum(row[0] == "exec" for row in calls), 1)
        self.assertEqual(raw.read_text(encoding="utf-8"), "not valid JSON")
        self.assertFalse(json.loads(report.read_text(encoding="utf-8"))["judge_response_validated"])

    def test_cli_nonzero_adapter_output_is_retained_and_cleanup_failure_cannot_pass(self):
        request = self.write("request.json", self.request)
        for failure in ("adapter", "cleanup"):
            raw, report = self.root / (failure + "-raw.json"), self.root / (failure + "-report.json")
            reply = json.dumps(synthetic_reply(self.request))
            def command(argv, **kwargs):
                if argv[0] == "exec":
                    self.assertIs(kwargs["check"], False)
                    return subprocess.CompletedProcess(argv, 2 if failure == "adapter" else 0, stdout=reply)
                if argv[0] == "rm" and failure == "cleanup":
                    raise OSError("private cleanup diagnostic")
                return subprocess.CompletedProcess(argv, 0, stdout="{}")
            with self.subTest(failure=failure), \
                    patch.object(judge_actions.platform, "system", return_value="Linux"), \
                    patch.object(judge_actions, "_os_release", return_value={"ID": "kylin", "VERSION_ID": "v11"}), \
                    patch.object(judging.DockerJudge, "command", side_effect=command), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = judge_actions.main(["run", "--request", str(request), "--output", str(report),
                    "--raw-output", str(raw), "--judge-argv", '["/opt/judge"]', "--confirm-isolated-guest"])
            self.assertEqual(code, 2)
            self.assertEqual(raw.read_text(encoding="utf-8"), reply)
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(result["all_checks_passed"])
            self.assertFalse(result["judge_response_validated"])
            self.assertNotIn("private cleanup diagnostic", report.read_text(encoding="utf-8"))

    def test_agent_cli_rejects_changed_manifest_before_container_creation(self):
        sample = self.write("sample.json", self.sample)
        manifest = self.write("manifest.json", self.manifest)
        with patch.object(evaluate_actions, "DockerSample") as docker, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            evaluate_actions.main(["--mode", "container", "--sample", str(sample), "--manifest", str(manifest),
                "--workspace", str(self.root / "new-sample"), "--output", str(self.root / "evidence-new.json"),
                "--image", self.manifest["agent"]["image"], "--adapter-argv", '["/opt/agent"]',
                "--confirm-isolated-guest"])
        docker.assert_not_called()
        self.assertFalse((self.root / "new-sample").exists())


if __name__ == "__main__":
    unittest.main()

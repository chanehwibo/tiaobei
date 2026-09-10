from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from os_agent_memory.complex_retrieval import (
    CONSTRAINT_SHA256, CONSTRAINT_SUITE_PATH, grouped_summaries,
    run_complex_evaluation, validate_suite,
)
from scripts.compare_retrieval_runs import validate_report
from scripts.generate_constraint_suite import build_suite
from scripts.generate_review_materials import validate_current_complex
from scripts.verify_kylin_guest import file_hashes


class ConstraintSuiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = json.loads((ROOT / CONSTRAINT_SUITE_PATH).read_bytes())
        cls.report = run_complex_evaluation(
            ROOT, suite_name="complex_constraints_v1", sizes=(78,), hard_fractions=(0,),
            rounds=1, constraint_modes=(False, True),
        )

    def test_frozen_data_and_independent_denominators(self):
        self.assertEqual(hashlib.sha256((ROOT / CONSTRAINT_SUITE_PATH).read_bytes()).hexdigest(), CONSTRAINT_SHA256)
        self.assertEqual(build_suite(), self.suite)
        validate_suite(self.suite)
        self.assertEqual(len(self.suite["documents"]), 78)
        self.assertEqual(len(self.suite["queries"]), 48)
        self.assertEqual(self.report["dataset"]["kinds"], {"positive": 24, "no_answer": 12, "scope": 12})

    def test_constraints_are_explicit_input_not_label_terms(self):
        suite = deepcopy(self.suite)
        suite["queries"][0]["required_terms"].append("answer-not-mentioned-in-the-request")
        with self.assertRaisesRegex(ValueError, "not derived from labels"):
            validate_suite(suite)

    def test_same_queries_evaluated_with_and_without_constraints(self):
        validate_report(self.report, self.suite)
        first, second = self.report["profiles"]
        self.assertIs(first["required_terms_enabled"], False)
        self.assertIs(second["required_terms_enabled"], True)
        self.assertEqual(first["corpus"], second["corpus"])
        self.assertEqual(first["configuration"], second["configuration"])
        self.assertEqual(first["provider"], second["provider"])
        self.assertEqual([row["id"] for row in first["rounds"][0]["rows"]],
                         [row["id"] for row in second["rounds"][0]["rows"]])
        self.assertIs(self.report["competition_ready"], False)

    def test_missing_version_refuses_but_unsupported_relations_are_not_hidden(self):
        guarded = self.report["profiles"][1]["rounds"][0]
        self.assertEqual(guarded["categories"]["absent_version"]["no_answer_correct"], 6)
        self.assertEqual(guarded["categories"]["unsupported_relation"]["no_answer_requests"], 6)
        self.assertEqual(guarded["summary"]["positive_requests"], 24)
        self.assertEqual(guarded["summary"]["no_answer_requests"], 12)
        self.assertEqual(guarded["summary"]["scope_requests"], 12)
        self.assertEqual(guarded["groups"], grouped_summaries(guarded["rows"]))

    def test_forged_group_measurements_and_constraint_policy_are_rejected(self):
        for field in ("group", "constraint", "dataset"):
            report = deepcopy(self.report)
            if field == "group":
                report["profiles"][1]["rounds"][0]["groups"]["kind"]["no_answer"]["requests"] = 1
            elif field == "constraint":
                report["profiles"][1]["required_terms_enabled"] = "yes"
            else:
                report["dataset"]["sha256"] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_report(report, self.suite)

    def test_current_review_requires_source_grouping_provider_and_input_attribution(self):
        report = deepcopy(self.report)
        # This is a validation fixture, not evidence for the host environment.
        report["environment"].update(system="Windows", python_hash_seed="0")
        snapshot = file_hashes(ROOT)
        arguments = {"expected_profiles": {(78, 0, "hybrid", value) for value in (False, True)}, "rounds": 1}
        validate_current_complex(ROOT, snapshot, report, self.suite, **arguments)
        for field in ("source", "groups", "provider", "method", "constraints"):
            changed = deepcopy(report)
            if field == "source":
                changed["source_sha256"]["src/os_agent_memory/memory_store.py"] = "0" * 64
            elif field == "groups":
                del changed["profiles"][0]["rounds"][0]["groups"]
            elif field == "provider":
                changed["profiles"][0]["provider"]["dimensions"] = 768
            elif field == "method":
                changed["method"]["boundary"] = "native SDK"
            else:
                changed["method"]["constraint_source"] = "answer labels"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_current_complex(ROOT, snapshot, changed, self.suite, **arguments)

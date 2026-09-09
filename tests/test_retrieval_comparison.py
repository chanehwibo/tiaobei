from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.compare_retrieval_runs import compare_reports, validate_report
from os_agent_memory.complex_retrieval import run_complex_evaluation, summarize_rows
import json


class RetrievalComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = json.loads((ROOT / "data/eval/complex_retrieval_v1.json").read_bytes())
        with patch.dict(os.environ, {"PYTHONHASHSEED": "0"}):
            cls.before = run_complex_evaluation(ROOT, sizes=(132,), hard_fractions=(0,), rounds=1)
        # Synthetic paired timings test the verifier, not a performance claim.
        cls.after = deepcopy(cls.before)
        cls.after["source_sha256"]["src/os_agent_memory/memory_store.py"] = "0" * 64
        for profile in cls.after["profiles"]:
            for repeat in profile["rounds"]:
                for row in repeat["rows"]:
                    row["elapsed_ms"] /= 2
                repeat["summary"] = summarize_rows(repeat["rows"])
                repeat["categories"] = {
                    category: summarize_rows([row for row in repeat["rows"] if row["category"] == category])
                    for category in repeat["categories"]
                }
                repeat["first_query_ms"] = repeat["rows"][0]["elapsed_ms"]

    def test_identical_outputs_and_faster_timings_do_not_erase_quality_failure(self):
        result = compare_reports(self.before, self.after, self.suite)
        self.assertTrue(result["identical_ranked_results_and_scores"])
        self.assertTrue(result["performance_improvement_supported"])
        self.assertFalse(result["complex_quality_targets_met"])
        self.assertFalse(result["competition_ready"])

    def test_edited_summary_missing_request_or_forged_label_rejected(self):
        for kind in ("summary", "missing", "label", "scope", "nan", "gate"):
            report = deepcopy(self.after)
            repeat = report["profiles"][0]["rounds"][0]
            if kind == "summary":
                repeat["summary"]["macro_recall_at_3"] = 1
            elif kind == "missing":
                repeat["rows"].pop()
            elif kind == "label":
                repeat["rows"][0]["expected"] = []
            elif kind == "scope":
                repeat["rows"][0]["returned"][0] = "not-in-corpus"
            elif kind == "nan":
                repeat["rows"][0]["elapsed_ms"] = float("nan")
            elif kind == "gate":
                report["quality_targets_met"] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate_report(report, self.suite)

    def test_changed_protocol_sources_environment_or_profile_rejected(self):
        for kind in ("protocol", "source", "environment", "profile"):
            report = deepcopy(self.after)
            if kind == "protocol":
                report["method"]["query_order"] = "warmed"
            elif kind == "source":
                report["source_sha256"]["src/os_agent_memory/service.py"] = "1" * 64
            elif kind == "environment":
                report["environment"]["python_hash_seed"] = "random"
            elif kind == "profile":
                report["profiles"].append(deepcopy(report["profiles"][0]))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                compare_reports(self.before, report, self.suite)

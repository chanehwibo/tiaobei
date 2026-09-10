import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.check_kylin_native import diagnose, main
from scripts.material_status import INITIAL_STATUS, SDK_RISK_STATUS
from scripts.summarize_sdk_risk import PROBE, ROOT, summarize_sdk_risk


class SDKRiskTest(unittest.TestCase):
    def assert_risk_only(self, report):
        self.assertEqual(report["display_status"], INITIAL_STATUS)
        self.assertEqual(report["latency_status"], SDK_RISK_STATUS)
        self.assertIsNone(report["native_p95_ms"])
        for key in ("native_latency_passed", "competition_ready", "official_validation_ready",
                    "model_identity_verified", "model_version_verified", "vector_database_connected"):
            self.assertIs(report[key], False)

    def test_discovery_without_probe_retains_risk_and_has_no_timing(self):
        report = diagnose()
        self.assert_risk_only(report)
        self.assertEqual(report["observations"], 0)
        self.assertIsNone(report["single_probe_ms"])
        self.assertEqual(report["probe_mode"], "discovery")

    def test_configuration_probe_times_success_and_failure_without_claiming_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "native.json"
            config.write_text(json.dumps({"provider": "kylin-native"}), encoding="utf-8")
            for error in (None, TimeoutError("private runtime details")):
                with self.subTest(error=error):
                    provider = SimpleNamespace(identity="native-test",
                                               encode=Mock(return_value=[.6, .8], side_effect=error))
                    with patch("scripts.check_kylin_native.create_provider", return_value=provider), \
                            patch("scripts.check_kylin_native.time.perf_counter", side_effect=[10., 23.5]):
                        report = diagnose(config)
                    self.assert_risk_only(report)
                    self.assertEqual(report["observations"], 1)
                    self.assertEqual(report["single_probe_ms"], 13500.)
                    self.assertEqual(report["real_embedding_executed"], error is None)
                    self.assertNotIn("private runtime details", json.dumps(report))
                    if error:
                        self.assertEqual(report["error_type"], "TimeoutError")
            config.write_text(json.dumps({"provider": "hash"}), encoding="utf-8")
            with patch("scripts.check_kylin_native.create_provider") as factory:
                report = diagnose(config)
                factory.assert_not_called()
            self.assert_risk_only(report)
            self.assertEqual(report["observations"], 0)

    def test_failed_legacy_probe_retains_elapsed_time_and_risk(self):
        with patch("scripts.check_kylin_native.probe_native_default", side_effect=TimeoutError), \
                patch("scripts.check_kylin_native.time.perf_counter", side_effect=[1., 11.]):
            report = diagnose(library_path="absent.so", probe_legacy_default=True)
        self.assert_risk_only(report)
        self.assertFalse(report["real_embedding_executed"])
        self.assertEqual(report["single_probe_ms"], 10000.)
        self.assertEqual(report["error_type"], "TimeoutError")

    def test_cli_refuses_overwrite_before_starting_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "diagnostic.json"
            output.write_text("original", encoding="utf-8")
            with patch("scripts.check_kylin_native.diagnose") as probe:
                with self.assertRaises(FileExistsError):
                    main(["--output", str(output)])
                probe.assert_not_called()
            self.assertEqual(output.read_text(encoding="utf-8"), "original")

    def test_native_single_probe_never_becomes_p95_or_acceptance(self):
        report = summarize_sdk_risk()
        self.assertEqual(report["latency_status"], SDK_RISK_STATUS)
        self.assertAlmostEqual(report["single_probe_ms"], 13390.615, places=3)
        self.assertEqual(report["observations"], 1)
        self.assertIsNone(report["native_p95_ms"])
        for key in ("native_latency_passed", "competition_ready", "model_identity_verified",
                    "model_version_verified", "hash_results_are_native_evidence"):
            self.assertIs(report[key], False)
        self.assertEqual(len(report["source_sha256"]), 64)

    def test_hash_or_invalid_timing_cannot_be_presented_as_native_evidence(self):
        original = json.loads((ROOT / PROBE).read_bytes())
        for change in ({"real_embedding_executed": False}, {"probe_mode": "HashEmbedding"},
                       {"single_probe_ms": float("nan")}, {"single_probe_ms": True},
                       {"single_probe_ms": -1}, {"dimensions": 0}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / PROBE
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({**original, **change}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    summarize_sdk_risk(root)

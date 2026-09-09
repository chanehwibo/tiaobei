import json
from pathlib import Path
import tempfile
import unittest

from scripts.material_status import SDK_RISK_STATUS
from scripts.summarize_sdk_risk import PROBE, ROOT, summarize_sdk_risk


class SDKRiskTest(unittest.TestCase):
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

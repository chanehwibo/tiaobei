import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.official_diagnostics import sensitive_diagnostic, diverse_latency


class OfficialDiagnosticsTest(unittest.TestCase):
    def test_sensitive_actual_predictions_and_denominators(self):
        suite = json.loads((Path(__file__).resolve().parents[1] / "data/eval/sensitive_official_diagnostic.json").read_text(encoding="utf-8"))
        result = sensitive_diagnostic(suite)
        self.assertEqual(result["requests"], 50)
        self.assertEqual(result["positive"], 25)
        self.assertEqual(result["negative"], 25)
        self.assertGreaterEqual(result["f1"], .9)
        suite["cases"].append(suite["cases"][0])
        with self.assertRaises(ValueError):
            sensitive_diagnostic(suite)

    def test_latency_50_distinct_queries_and_percentile(self):
        result = diverse_latency(size=50)
        self.assertEqual(result["unique_queries"], 50)
        ordered = sorted(row["elapsed_ms"] for row in result["rows"])
        self.assertEqual(result["p95_ms"], ordered[47])
        with self.assertRaises(ValueError):
            diverse_latency(requests=49)

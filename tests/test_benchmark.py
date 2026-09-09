from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from os_agent_memory.benchmark import run_scale_benchmark, write_benchmark_report
from os_agent_memory.resources import resource_snapshot, resource_usage
from unittest.mock import patch


class ScaleBenchmarkTest(unittest.TestCase):
    def test_small_benchmark_reports_all_required_evidence(self) -> None:
        result = run_scale_benchmark((10, 25), rounds=3, top_k=3)
        self.assertEqual([row["records"] for row in result["results"]], [10, 25])
        self.assertTrue(result["all_meet_500ms"])
        required = {
            "cold_query_ms",
            "hot_query_p50_ms",
            "hot_query_p95_ms",
            "hot_query_p99_ms",
            "throughput_qps",
            "peak_python_memory_mb",
            "sqlite_disk_mb",
            "meets_500ms",
            "process_resources",
        }
        self.assertTrue(all(required <= set(row) for row in result["results"]))

        with tempfile.TemporaryDirectory() as temporary_directory:
            json_path = Path(temporary_directory) / "report.json"
            markdown_path = Path(temporary_directory) / "report.md"
            write_benchmark_report(result, json_path=json_path, markdown_path=markdown_path)
            restored = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
        self.assertEqual(restored["benchmark"], result["benchmark"])
        self.assertIn("HashEmbedding", markdown)
        self.assertIn("不能替代真实 SDK", markdown)
        self.assertIn("生命周期峰值", markdown)

    def test_process_resources_are_measured_and_scope_is_explicit(self):
        before = resource_snapshot()
        after = resource_snapshot()
        result = resource_usage(before, after)
        self.assertGreaterEqual(result["cpu_ms"], 0)
        self.assertGreaterEqual(result["wall_ms"], 0)
        if sys.platform in {"win32", "linux"}:
            self.assertTrue(result["available"], result)
            self.assertGreater(result["rss_after_bytes"], 0)
        self.assertIn("not a per-workload peak", result["peak_definition"])
        self.assertIn("excludes", result["scope"])

    def test_unavailable_process_memory_is_not_reported_as_zero(self):
        with patch("os_agent_memory.resources._resident_memory", side_effect=OSError):
            snapshot = resource_snapshot()
        result = resource_usage(snapshot, snapshot)
        self.assertFalse(result["available"])
        self.assertIsNone(result["rss_after_bytes"])
        self.assertIsNone(result["lifetime_peak_rss_bytes"])
        self.assertIsNone(result["cpu_percent_one_core"])

    def test_benchmark_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            run_scale_benchmark((0,), rounds=1)
        with self.assertRaises(ValueError):
            run_scale_benchmark((10,), rounds=0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from os_agent_memory.benchmark import run_scale_benchmark, write_benchmark_report


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

    def test_benchmark_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            run_scale_benchmark((0,), rounds=1)
        with self.assertRaises(ValueError):
            run_scale_benchmark((10,), rounds=0)


if __name__ == "__main__":
    unittest.main()

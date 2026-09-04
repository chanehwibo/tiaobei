from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from os_agent_memory.compatibility import collect_compatibility_report, write_compatibility_report


class CompatibilityTest(unittest.TestCase):
    def test_report_separates_local_and_competition_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = collect_compatibility_report(temporary_directory)
        self.assertIn("operating_system", report)
        self.assertIn("resources", report)
        self.assertIn("sqlite", report)
        self.assertTrue(report["sqlite"]["json1"])
        self.assertTrue(report["resources"]["filesystem"]["writable"])
        self.assertEqual(report["embedding_sdk"]["status"], "not_checked")
        verdict = report["verdict"]
        self.assertIn("local_runtime_ready", verdict)
        self.assertIn("competition_environment_ready", verdict)
        self.assertFalse(verdict["real_embedding_sdk_verified"])

    def test_report_writer_outputs_json_and_honest_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = collect_compatibility_report(temporary_directory)
            json_path = Path(temporary_directory) / "compat.json"
            markdown_path = Path(temporary_directory) / "compat.md"
            write_compatibility_report(report, json_path=json_path, markdown_path=markdown_path)
            restored = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
        self.assertEqual(restored["verdict"], report["verdict"])
        self.assertIn("真实银河麒麟环境", markdown)
        self.assertIn("真实 embedding SDK", markdown)


if __name__ == "__main__":
    unittest.main()

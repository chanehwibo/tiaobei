from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from os_agent_memory.diagnostics import run_preflight


class DiagnosticsTest(unittest.TestCase):
    def test_preflight_passes_local_requirements_and_keeps_external_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            input_path = directory / "events.jsonl"
            suite_path = directory / "suite.json"
            input_path.write_text("{}\n", encoding="utf-8")
            suite_path.write_text('{"records": []}\n', encoding="utf-8")
            result = run_preflight(
                workspace=directory,
                input_path=input_path,
                suite_path=suite_path,
                port=0,
            )
        self.assertTrue(result["ready_for_local_demo"])
        self.assertEqual(result["blocking_failures"], [])
        self.assertIn("real_kylin_sdk_ready", result["warnings"])

    def test_preflight_reports_missing_file_and_occupied_port(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            suite_path = directory / "suite.json"
            suite_path.write_text('{"records": []}\n', encoding="utf-8")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
                occupied.bind(("127.0.0.1", 0))
                port = occupied.getsockname()[1]
                result = run_preflight(
                    workspace=directory,
                    input_path=directory / "missing.jsonl",
                    suite_path=suite_path,
                    port=port,
                )
        self.assertFalse(result["ready_for_local_demo"])
        self.assertIn("sample_input_exists", result["blocking_failures"])
        self.assertIn("dashboard_port_available", result["blocking_failures"])


if __name__ == "__main__":
    unittest.main()

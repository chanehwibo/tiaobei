import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.workload import run_service_workload

class ServiceWorkloadTest(unittest.TestCase):
    def test_real_ingest_restart_http_and_concurrent_writes(self):
        report = run_service_workload((8,), rounds=3)
        row = report["results"][0]
        self.assertEqual(row["persisted_knowledge"], 12)
        self.assertTrue(row["all_queries_nonempty"])
        self.assertGreater(row["service_ingest_ms"], 0)
        self.assertGreater(row["http_query_p99_ms"], 0)
        self.assertEqual(row["concurrent_operations"], 6)

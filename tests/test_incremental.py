import sys
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.service import MemoryService
from os_agent_memory.workload import workload_event


class IncrementalPersistenceTest(unittest.TestCase):
    def test_restart_preserves_evidence_dedup_and_delete_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.sqlite"
            service = MemoryService(database_path=path)
            record = workload_event(1)
            record["authority"] = 0.8
            service.ingest([record])
            service = MemoryService(database_path=path)
            self.assertEqual(service.ingest([record])["duplicate_records"], 1)
            newer = {**record, "id": "second", "timestamp": "2026-01-02T00:00:00+00:00"}
            self.assertTrue(service.ingest([newer])["knowledge"])
            plan = service.forget_preview("删除task00001相关记忆", tenant_id="load", user_id="operator")
            receipt = service.forget_confirm(plan["id"])
            self.assertGreater(receipt["knowledge_count"], 0)
            reloaded = MemoryService(database_path=path)
            self.assertEqual(reloaded.forget_confirm(plan["id"]), receipt)
            self.assertFalse(reloaded.lifecycle.medium_term.clusters(tenant_id="load", user_id="operator"))
            self.assertEqual(reloaded.ingest([record])["duplicate_records"], 1)
            self.assertFalse(reloaded.search("task00001", tenant_id="load", user_id="operator"))

    def test_unchanged_save_does_not_rewrite_knowledge_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.sqlite"
            service = MemoryService(database_path=path)
            service.ingest([workload_event(1)])
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE mutations (operation TEXT)")
                db.execute("CREATE TRIGGER count_update AFTER UPDATE ON knowledge BEGIN INSERT INTO mutations VALUES ('update'); END")
                db.execute("CREATE TRIGGER count_delete AFTER DELETE ON knowledge BEGIN INSERT INTO mutations VALUES ('delete'); END")
                db.commit()
            service.save()
            service.ingest([workload_event(2)])
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM mutations").fetchone()[0], 0)

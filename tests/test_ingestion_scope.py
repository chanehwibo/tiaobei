import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.ingestion import DataIngestionPipeline
from os_agent_memory.lifecycle import ShortTermMemoryBuffer
from os_agent_memory.service import MemoryService


def event(tenant="one", user="reader", **updates):
    return {"id": "local-event", "tenant_id": tenant, "user_id": user,
            "source_type": "manual_config", "timestamp": "2026-01-01T00:00:00Z",
            "content": "操作流程：审核记录后归档，保留核验记录。",
            "metadata": {"title": "Archive procedure"}, **updates}


class IngestionScopeTest(unittest.TestCase):
    def test_local_event_ids_are_scoped_by_tenant_and_user(self):
        service = MemoryService()
        report = service.ingest([event(), event("two"), event(user="another")])
        self.assertEqual(report["accepted_records"], 3)
        self.assertEqual(report["duplicate_records"], 0)
        self.assertEqual(len(service.store.knowledge), 3)
        self.assertEqual(service.ingest([event(), event("two")])["duplicate_records"], 2)

    def test_ingest_response_does_not_return_another_owners_memories(self):
        service = MemoryService()
        service.ingest([event(), event(content="请始终用中文回答，输出格式使用Markdown。")])
        for incoming in (event("two"), event(user="another")):
            report = service.ingest([incoming])
            self.assertTrue(report["knowledge"])
            for item in report["knowledge"] + report["preferences"]:
                self.assertEqual((item["tenant_id"], item["user_id"]),
                                 (incoming["tenant_id"], incoming["user_id"]))

    def test_preference_response_is_scoped_even_when_evidence_id_is_reused(self):
        service = MemoryService()
        preference = event(content="请始终使用中文回答，输出格式使用Markdown。")
        original = service.ingest([preference])
        self.assertTrue(original["preferences"])
        report = service.ingest([{**preference, "tenant_id": "two"}])
        self.assertTrue(report["preferences"])
        self.assertEqual({item["tenant_id"] for item in report["preferences"]}, {"two"})

    def test_short_term_same_ids_survive_reload_and_scoped_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite"
            service = MemoryService(database_path=path)
            # A future timestamp keeps the short-term fixture independent of today's clock.
            rows = [event(tenant, timestamp="2090-01-01T00:00:00Z") for tenant in ("one", "two")]
            service.ingest(rows)
            for store in (service, MemoryService(database_path=path)):
                for tenant in ("one", "two"):
                    active = store.lifecycle.short_term.active(tenant_id=tenant, user_id="reader")
                    self.assertEqual([item.id for item in active], ["local-event"])
            self.assertTrue(service.lifecycle.short_term.remove(
                "local-event", tenant_id="one", user_id="reader"))
            self.assertEqual(len(service.lifecycle.short_term), 1)
            self.assertTrue(service.lifecycle.short_term.active(tenant_id="two", user_id="reader"))

    def test_expiring_one_owner_does_not_remove_another_owners_event(self):
        buffer = ShortTermMemoryBuffer()
        for row in (event(ttl_seconds=10), event("two", ttl_seconds=120)):
            buffer.add(DataIngestionPipeline().normalize_record(row))
        self.assertEqual(buffer.expire(now="2026-01-01T00:00:30Z"), ["local-event"])
        self.assertEqual(len(buffer.active(tenant_id="two", user_id="reader",
                                           now="2026-01-01T00:00:30Z")), 1)

    def test_conflicting_event_payload_is_reported_instead_of_discarded(self):
        report = DataIngestionPipeline().ingest_with_report(
            [event(), event(content="操作流程：备份数据库后校验，保留完整结果。"), event()])
        self.assertEqual(len(report.records), 1)
        self.assertEqual(report.duplicate_count, 1)
        self.assertEqual([item.reason for item in report.issues], ["event_id_conflict"])

    def test_invalid_authority_is_isolated_without_poisoning_valid_rows(self):
        for value in (float("nan"), float("inf"), float("-inf"), True):
            with self.subTest(value=value):
                report = DataIngestionPipeline().ingest_with_report(
                    [event(authority=value), event(id="valid")])
                self.assertEqual([item.id for item in report.records], ["valid"])
                self.assertEqual(len(report.issues), 1)

    def test_invalid_ttl_is_rejected_without_aborting_batch(self):
        for value in (float("inf"), float("nan"), True, 1.5, 10**30):
            with self.subTest(value=value):
                report = DataIngestionPipeline().ingest_with_report(
                    [event(ttl_seconds=value), event(id="valid")])
                self.assertEqual([item.id for item in report.records], ["valid"])
                self.assertEqual(len(report.issues), 1)


if __name__ == "__main__":
    unittest.main()

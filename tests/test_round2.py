from __future__ import annotations

import sys
import unittest
import tempfile
from unittest.mock import Mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from os_agent_memory.service import MemoryService
from os_agent_memory.evaluation import build_store_from_raw_records
from os_agent_memory.persistence import SQLiteMemoryPersistence


def event(identifier="probe", authority=0.4):
    return {
        "id": identifier, "tenant_id": "test", "user_id": "alice",
        "source_type": "user_behavior", "scene": "office",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "content": "报销流程模板：先收集票据，再校验金额，最后提交审批并归档。",
        "metadata": {"title": "报销流程模板"}, "authority": authority,
    }


class LifecycleIntegrationTest(unittest.TestCase):
    def test_service_and_evaluation_reject_single_weak_event(self):
        service = MemoryService()
        result = service.ingest([event()], persist=False)
        self.assertFalse(result["promotion_decisions"][0]["accepted"])
        self.assertFalse(service.store.knowledge)
        self.assertFalse(build_store_from_raw_records([event()]).knowledge)

    def test_distinct_repeated_evidence_promotes_across_requests(self):
        service = MemoryService()
        service.ingest([event("one", 0.8)], persist=False)
        result = service.ingest([event("two", 0.8)], persist=False)
        self.assertTrue(result["promotion_decisions"][0]["accepted"])
        self.assertTrue(service.search("报销", tenant_id="test", user_id="alice"))


class ValidityTest(unittest.TestCase):
    def test_validity_is_start_inclusive_end_exclusive_and_cleans_index(self):
        service = MemoryService()
        service.ingest([event(authority=0.95)], persist=False)
        item = next(iter(service.store.knowledge.values()))
        item.valid_from = "2026-01-02T00:00:00+00:00"
        item.valid_to = "2026-01-03T00:00:00+00:00"
        def query(now):
            return service.store.search_knowledge("报销", tenant_id="test", user_id="alice", now=now)
        self.assertFalse(query("2026-01-01T00:00:00+00:00"))
        self.assertTrue(query(item.valid_from))
        self.assertFalse(query(item.valid_to))
        self.assertEqual(item.status.value, "expired")
        self.assertFalse(item.embedding)
        self.assertNotIn(item.id, service.store._document_tokens)

    def test_explicit_high_authority_configuration_promotes(self):
        service = MemoryService()
        result = service.ingest([event(authority=0.95)], persist=False)
        self.assertTrue(result["promotion_decisions"][0]["accepted"])


class DeletedIndexTest(unittest.TestCase):
    def test_deleted_vectors_stay_absent_after_rebuild_and_reload(self):
        service = MemoryService()
        service.ingest([event(authority=0.95)], persist=False)
        plan = service.forget_preview("删除报销相关记忆", tenant_id="test", user_id="alice")
        service.forget_confirm(plan["id"], persist=False)
        service.store.rebuild_index()
        with tempfile.TemporaryDirectory() as folder:
            persistence = SQLiteMemoryPersistence(Path(folder) / "memory.sqlite")
            persistence.save(service.store)
            loaded = persistence.load()
        for store in (service.store, loaded):
            item = next(iter(store.knowledge.values()))
            self.assertEqual(item.status.value, "forgotten")
            self.assertFalse(item.embedding)
            self.assertNotIn(item.id, store._document_tokens)
            self.assertFalse(store.search_knowledge("报销", tenant_id="test", user_id="alice"))


class TransactionTest(unittest.TestCase):
    def test_failed_ingestion_rolls_back_memory_and_lifecycle(self):
        service = MemoryService()
        service.persistence = Mock()
        service.persistence.save.side_effect = OSError("simulated disk failure")
        with self.assertRaises(OSError):
            service.ingest([event(authority=0.95)])
        self.assertFalse(service.store.knowledge)
        self.assertFalse(service.lifecycle.medium_term.clusters(tenant_id="test", user_id="alice"))

    def test_failed_delete_is_retryable_and_does_not_consume_plan(self):
        service = MemoryService()
        service.ingest([event(authority=0.95)], persist=False)
        plan = service.forget_preview("删除报销相关记忆", tenant_id="test", user_id="alice")
        service.persistence = Mock()
        service.persistence.save.side_effect = OSError("simulated disk failure")
        with self.assertRaises(OSError):
            service.forget_confirm(plan["id"])
        self.assertFalse(service.store.pending_forget_plans[plan["id"]].confirmed)
        self.assertFalse(service.store.audit_events)
        self.assertTrue(service.search("报销", tenant_id="test", user_id="alice"))
        service.persistence.save.side_effect = None
        self.assertTrue(service.forget_confirm(plan["id"])["confirmed"])

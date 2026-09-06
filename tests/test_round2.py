from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from os_agent_memory.service import MemoryService
from os_agent_memory.evaluation import build_store_from_raw_records


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

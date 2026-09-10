from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from os_agent_memory.service import MemoryService
from os_agent_memory.schemas import KnowledgeMemory
from os_agent_memory.retrieval_evidence import DEFAULT_POLICY
from os_agent_memory.web_server import create_server, dashboard_html
from tests.test_evidence_constraints import document


class WebServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MemoryService()
        sample_path = ROOT / "data" / "samples" / "events.jsonl"
        raw_records = self.service.ingestion.load_jsonl(sample_path)
        self.service.ingest(raw_records, persist=False)
        self.server = create_server(self.service, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = build_opener(ProxyHandler({}))

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def get_json(self, path: str) -> object:
        with self.opener.open(self.base_url + path, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path: str, payload: object) -> object:
        request = Request(
            self.base_url + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener.open(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_dashboard_and_read_apis_are_available(self) -> None:
        with self.opener.open(self.base_url + "/", timeout=3) as response:
            html = response.read().decode("utf-8")
            self.assertEqual(response.headers.get_content_type(), "text/html")
        self.assertIn("端侧智能记忆优化演示台", html)
        self.assertIn("安全遗忘", dashboard_html())

        stats = self.get_json("/api/stats")
        self.assertGreater(stats["knowledge"], 0)
        preferences = self.get_json(
            "/api/preferences?tenant_id=default&user_id=u-demo&scene=office_report"
        )
        self.assertIn("output.language", {item["key"] for item in preferences})

    def test_search_and_two_phase_forget_work_through_http(self) -> None:
        search = self.post_json(
            "/api/search",
            {
                "query": "报销模板",
                "tenant_id": "default",
                "user_id": "u-demo",
                "scene": "office_report",
            },
        )
        self.assertTrue(search)
        preview = self.post_json(
            "/api/forget/preview",
            {
                "instruction": "删除报销模板相关记忆",
                "tenant_id": "default",
                "user_id": "u-demo",
            },
        )
        self.assertTrue(preview["knowledge_ids"])
        confirmed = self.post_json("/api/forget/confirm", {"plan_id": preview["id"], "tenant_id": "default", "user_id": "u-demo"})
        self.assertTrue(confirmed["confirmed"])

    def test_api_rejects_missing_scope(self) -> None:
        request = Request(
            self.base_url + "/api/search",
            data=b'{"query":"test"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as caught:
            self.opener.open(request, timeout=3)
        self.assertEqual(caught.exception.code, 400)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        caught.exception.close()
        self.assertIn("tenant_id is required", payload["error"])

    def test_search_evidence_constraints_and_modes_reach_the_service(self):
        for identifier in ("AE-17", "AE-170"):
            self.service.store.upsert_knowledge(KnowledgeMemory(
                id=identifier, title="procedure", content=identifier + " v2.4 installation",
                tags=["procedure"], source_ids=[identifier], version=1,
                created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
                tenant_id="constraints", user_id="operator"))
        body = {"query": "procedure", "tenant_id": "constraints", "user_id": "operator",
                "required_terms": ["AE-17", "v2.4"], "retrieval_mode": "lexical", "min_score": 0}
        self.assertEqual([row["memory_id"] for row in self.post_json("/api/search", body)], ["AE-17"])
        self.assertEqual(self.post_json("/api/search", {**body, "required_terms": ["v2.40"]}), [])
        guarded = {**body, "query": "procedure insurance settlement currency",
                   "evidence_policy": "content_coverage_v1"}
        self.assertEqual(self.post_json("/api/search", guarded), [])
        for change in ({"required_terms": "AE-17"}, {"required_terms": [""]}, {"retrieval_mode": "unknown"},
                       {"evidence_policy": "unknown"}, {"evidence_policy": None}):
            with self.assertRaises(HTTPError) as caught:
                self.post_json("/api/search", {**body, **change})
            self.assertEqual(caught.exception.code, 400)
            caught.exception.close()

    def test_http_default_completes_evidence_and_rejects_unsupported_property(self):
        self.service.store.upsert_knowledge(document(
            "seed", "calibration readout procedure", title="Sensor H7 procedure"))
        self.service.store.upsert_knowledge(document(
            "support", "two reviewers approve calibration", title="Sensor H7 requirements"))
        body = {"query": "what calibration readout and reviewers are required for sensor h7",
                "tenant_id": "tenant", "user_id": "operator", "top_k": 3, "min_score": 0}
        results = self.post_json("/api/search", body)
        self.assertEqual({row["memory_id"] for row in results}, {"seed", "support"})
        self.assertTrue(all(row["evidence"]["policy"] == DEFAULT_POLICY for row in results))
        self.assertEqual(results, self.post_json("/api/search", {**body, "evidence_policy": DEFAULT_POLICY}))
        body["query"] = "what insurance settlement currency covers sensor h7"
        self.assertEqual(self.post_json("/api/search", body), [])
        self.assertTrue(self.post_json("/api/search", {**body, "evidence_policy": "similarity"}))

    def test_confirm_rejects_another_user_and_null_scope(self):
        preview = self.post_json("/api/forget/preview", {
            "instruction": "删除报销模板相关记忆", "tenant_id": "default", "user_id": "u-demo"})
        for user, status in (("attacker", 403), (None, 400)):
            with self.assertRaises(HTTPError) as caught:
                self.post_json("/api/forget/confirm", {
                    "plan_id": preview["id"], "tenant_id": "default", "user_id": user})
            self.assertEqual(caught.exception.code, status)
            caught.exception.close()
        self.assertFalse(self.service.store.pending_forget_plans[preview["id"]].confirmed)

    def test_conflict_resolution_rejects_wrong_scope(self):
        item = next(iter(self.service.store.knowledge.values()))
        with self.assertRaises(PermissionError):
            self.service.resolve_conflict(item.id, tenant_id="other", user_id=item.user_id)

    def test_scenarios_and_reset_preserve_other_tenants(self):
        original_ids = set(self.service.store.knowledge)
        self.post_json("/api/demo", {"name": "baseline", "reset": True})
        self.post_json("/api/demo", {"name": "preference"})
        self.post_json("/api/demo", {"name": "conflict"})
        result = self.get_json("/api/overview?tenant_id=local-demo&user_id=presenter")
        self.assertTrue(any(p["value"] == "detailed" for p in result["preferences"]))
        self.assertTrue(any(k["status"] == "conflict_pending" for k in result["knowledge"]))
        self.assertGreater(len(result["history"]), len(result["preferences"]))
        self.post_json("/api/demo", {"name": "baseline", "reset": True})
        reset = self.get_json("/api/overview?tenant_id=local-demo&user_id=presenter")
        self.assertFalse(any(k["status"] == "conflict_pending" for k in reset["knowledge"]))
        self.assertTrue(original_ids <= self.service.store.knowledge.keys())


if __name__ == "__main__":
    unittest.main()

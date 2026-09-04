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
from os_agent_memory.web_server import create_server, dashboard_html


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
        confirmed = self.post_json("/api/forget/confirm", {"plan_id": preview["id"]})
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


if __name__ == "__main__":
    unittest.main()

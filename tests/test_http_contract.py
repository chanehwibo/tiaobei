import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.service import MemoryService
from os_agent_memory.memory_store import MemoryStore
from os_agent_memory.web_server import create_server


class HttpContractTest(unittest.TestCase):
    def setUp(self):
        self.service = MemoryService()
        self.server = create_server(self.service, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, body=None, *, headers=None, method="POST", path="/api/search"):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=body,
                               headers={"Content-Type": "application/json", **(headers or {})})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_cross_origin_request_is_rejected_before_body_parsing(self):
        status, _ = self.request(b"invalid", headers={"Origin": "https://example.invalid"})
        self.assertEqual(status, 403)

    def test_matching_untrusted_host_and_origin_cannot_access_local_server(self):
        for method in ("GET", "POST"):
            status, _ = self.request(b"{}", method=method, path="/api/stats",
                                     headers={"Host": "example.invalid", "Origin": "http://example.invalid"})
            self.assertEqual(status, 403)
        self.assertEqual(self.request(method="GET", path="/api/stats")[0], 200)

    def test_nonfinite_and_duplicate_json_fields_are_rejected(self):
        for body in (b'{"records":[],"records":[]}',
                     b'{"records":[],"value":NaN}', b'{"records":[],"value":1e999}'):
            with self.subTest(body=body):
                status, payload = self.request(body, path="/api/ingest")
                self.assertEqual(status, 400)
                self.assertIn("error", json.loads(payload))
        self.assertEqual(self.service.stats()["knowledge"], 0)

    def test_search_numbers_are_not_coerced_from_booleans_or_fractional_values(self):
        base = {"query": "calibration", "tenant_id": "one", "user_id": "reader"}
        for change in ({"top_k": True}, {"top_k": 1.5}, {"top_k": "3"},
                       {"min_score": True}, {"scene": ["office"]}):
            with self.subTest(change=change):
                self.assertEqual(self.request(json.dumps({**base, **change}).encode())[0], 400)
        self.assertEqual(self.request(json.dumps(base).encode())[0], 200)

    def test_unsupported_transfer_encoding_is_rejected(self):
        self.assertEqual(self.request(b"{}", headers={"Transfer-Encoding": "chunked"})[0], 400)

    def test_partial_request_body_has_a_read_timeout(self):
        with patch("os_agent_memory.web_server.REQUEST_TIMEOUT_SECONDS", 0.1):
            connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
            try:
                connection.request("POST", "/api/search", body=b"{", headers={"Content-Length": "10"})
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                self.assertIn(b"timed out", response.read())
            finally:
                connection.close()

    def test_library_validates_limits_even_for_an_empty_query(self):
        store = MemoryStore()
        for options in ({"top_k": True}, {"top_k": 1.5}, {"candidate_limit": float("inf")},
                        {"min_score": float("nan")}, {"min_score": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                store.search_knowledge("", **options)


if __name__ == "__main__":
    unittest.main()

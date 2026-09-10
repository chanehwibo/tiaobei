from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .service import MemoryService
from .memory_store import MemoryStore
from .retrieval_evidence import DEFAULT_POLICY


MAX_REQUEST_BYTES = 1_000_000


def dashboard_html() -> str:
    from pathlib import Path
    return Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")


def create_server(
    service: MemoryService,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    class MemoryRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._send_text(dashboard_html(), content_type="text/html; charset=utf-8")
                    return
                query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
                if parsed.path == "/api/stats":
                    self._send_json(service.stats())
                elif parsed.path == "/api/preferences":
                    self._send_json(
                        service.preferences(
                            tenant_id=self._required(query, "tenant_id"),
                            user_id=self._required(query, "user_id"),
                            scene=query.get("scene") or None,
                        )
                    )
                elif parsed.path == "/api/overview":
                    self._send_json(service.overview(tenant_id=self._required(query, "tenant_id"),
                                                     user_id=self._required(query, "user_id")))
                elif parsed.path == "/api/conflicts":
                    self._send_json(
                        service.conflicts(
                            tenant_id=self._required(query, "tenant_id"),
                            user_id=self._required(query, "user_id"),
                        )
                    )
                else:
                    self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            except (KeyError, TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                body = self._read_json()
                origin = self.headers.get("Origin")
                if origin and origin != "http://" + self.headers.get("Host", ""):
                    raise PermissionError("cross-origin mutation is forbidden")
                if parsed.path == "/api/demo":
                    if not isinstance(body.get("reset", False), bool):
                        raise ValueError("reset must be boolean")
                    result = service.demo_scenario(self._required(body, "name"), reset=body.get("reset", False))
                elif parsed.path == "/api/ingest":
                    records = body.get("records")
                    if not isinstance(records, list):
                        raise ValueError("records must be an array")
                    result = service.ingest(records)
                elif parsed.path == "/api/search":
                    result = service.search(
                        self._required(body, "query"),
                        tenant_id=self._required(body, "tenant_id"),
                        user_id=self._required(body, "user_id"),
                        scene=str(body.get("scene") or "") or None,
                        top_k=int(body.get("top_k", 5)),
                        min_score=float(body.get("min_score", MemoryStore.DEFAULT_MIN_SCORE)),
                        retrieval_mode=body.get("retrieval_mode", "hybrid"),
                        required_terms=body.get("required_terms"),
                        evidence_policy=body.get("evidence_policy", DEFAULT_POLICY),
                    )
                elif parsed.path == "/api/conflicts/resolve":
                    result = service.resolve_conflict(
                        self._required(body, "memory_id"),
                        tenant_id=self._required(body, "tenant_id"),
                        user_id=self._required(body, "user_id"),
                        strategy=str(body.get("strategy", "auto")),
                    )
                elif parsed.path == "/api/forget/preview":
                    if not isinstance(body.get("hard_delete", False), bool):
                        raise ValueError("hard_delete must be boolean")
                    result = service.forget_preview(
                        self._required(body, "instruction"),
                        tenant_id=self._required(body, "tenant_id"),
                        user_id=self._required(body, "user_id"),
                        hard_delete=bool(body.get("hard_delete", False)),
                    )
                elif parsed.path == "/api/forget/confirm":
                    result = service.forget_confirm(self._required(body, "plan_id"),
                                                    tenant_id=self._required(body, "tenant_id"),
                                                    user_id=self._required(body, "user_id"))
                else:
                    self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(result)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except OSError:
                self._send_json({"error": "storage operation failed"}, HTTPStatus.SERVICE_UNAVAILABLE)
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)

        def log_message(self, _format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError(f"request body must be 1..{MAX_REQUEST_BYTES} bytes")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_text(self, payload: str, *, content_type: str) -> None:
            data = payload.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(data)

        @staticmethod
        def _required(payload: dict[str, Any], key: str) -> str:
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} is required")
            return value.strip()

    return ThreadingHTTPServer((host, port), MemoryRequestHandler)


def serve(service: MemoryService, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = create_server(service, host=host, port=port)
    print(f"Memory dashboard: http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

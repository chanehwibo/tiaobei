from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .service import MemoryService


MAX_REQUEST_BYTES = 1_000_000


def dashboard_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>端侧智能记忆优化演示台</title>
  <style>
    :root{color-scheme:dark;--bg:#09111f;--panel:#111d31;--line:#263957;--accent:#6ee7d2;--warn:#ffca76}
    *{box-sizing:border-box}body{margin:0;font:15px/1.55 system-ui,"Microsoft YaHei",sans-serif;background:radial-gradient(circle at top,#18304b,var(--bg) 55%);color:#eef6ff}
    main{max-width:1180px;margin:auto;padding:28px}h1{margin:0;font-size:30px}p{color:#aac0da}.bar,.grid{display:grid;gap:14px}.bar{grid-template-columns:repeat(4,1fr);margin:24px 0}.grid{grid-template-columns:1fr 1fr}.card{background:rgba(17,29,49,.94);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 14px 34px #0005}.metric{font-size:28px;color:var(--accent)}label{display:block;margin-top:10px;color:#bcd0e7}input,textarea,select,button{width:100%;border:1px solid #365072;border-radius:8px;background:#0b1628;color:#eef6ff;padding:9px}textarea{min-height:105px;resize:vertical}button{margin-top:10px;background:#147c74;border:0;font-weight:700;cursor:pointer}button.secondary{background:#374a67}.output{white-space:pre-wrap;max-height:280px;overflow:auto;background:#07101e;border-radius:8px;padding:12px;margin-top:12px;color:#cae0f8}.danger{background:#a13d4e}@media(max-width:780px){.bar,.grid{grid-template-columns:1fr 1fr}}@media(max-width:520px){.bar,.grid{grid-template-columns:1fr}}
  </style>
</head>
<body><main>
  <h1>端侧智能记忆优化演示台</h1>
  <p>多源数据接入 · 偏好画像 · 混合检索 · 冲突治理 · 可审计遗忘</p>
  <section class="bar" id="metrics"></section>
  <section class="grid">
    <article class="card"><h2>作用域</h2>
      <label>租户 <input id="tenant" value="default"></label>
      <label>用户 <input id="user" value="u-demo"></label>
      <label>场景 <input id="scene" value="office_report"></label>
      <button onclick="refreshAll()">刷新仪表盘</button>
    </article>
    <article class="card"><h2>偏好记忆</h2><div id="preferences" class="output">等待加载</div></article>
    <article class="card"><h2>多源接入</h2>
      <label>事件数组（JSON）<textarea id="records">[{"id":"web-demo","source_type":"manual_config","user_id":"u-demo","scene":"office_report","content":"用户偏好：输出请使用中文并保持简洁。","metadata":{"title":"网页演示偏好"}}]</textarea></label>
      <button onclick="ingest()">校验、脱敏并接入</button><div id="ingest-output" class="output">尚未接入</div>
    </article>
    <article class="card"><h2>知识检索</h2>
      <label>问题 <input id="query" value="报销流程模板"></label><button onclick="search()">检索</button>
      <div id="search-output" class="output">尚未检索</div>
    </article>
    <article class="card"><h2>冲突治理</h2><button onclick="loadConflicts()">查看待决冲突</button>
      <label>记忆 ID <input id="conflict-id"></label><label>策略 <select id="strategy"><option value="auto">权威度与时效自动决策</option><option value="keep_existing">保留现有</option><option value="accept_incoming">接受新版本</option><option value="manual_review">人工复核</option></select></label>
      <button onclick="resolveConflict()">执行冲突决策</button><div id="conflict-output" class="output">尚未加载</div>
    </article>
    <article class="card"><h2>安全遗忘</h2>
      <label>自然语言指令 <input id="forget-text" value="删除报销模板相关记忆"></label>
      <button class="secondary" onclick="previewForget()">仅预览影响范围</button>
      <label>确认计划 ID <input id="plan-id" readonly></label>
      <button class="danger" onclick="confirmForget()">确认执行软删除</button><div id="forget-output" class="output">必须先预览再确认</div>
    </article>
  </section>
</main>
<script>
const el=id=>document.getElementById(id);const scope=()=>({tenant_id:el('tenant').value,user_id:el('user').value,scene:el('scene').value});
const show=(id,value)=>{el(id).textContent=JSON.stringify(value,null,2)};
async function api(path,options={}){const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});const data=await response.json();if(!response.ok)throw new Error(data.error||response.statusText);return data}
async function refreshAll(){try{const s=await api('/api/stats');el('metrics').innerHTML=Object.entries(s).slice(0,4).map(([k,v])=>`<article class="card"><div>${k.replaceAll('_',' ')}</div><div class="metric">${Number(v)}</div></article>`).join('');const q=new URLSearchParams(scope());show('preferences',await api('/api/preferences?'+q))}catch(e){show('preferences',{error:e.message})}}
async function ingest(){try{show('ingest-output',await api('/api/ingest',{method:'POST',body:JSON.stringify({records:JSON.parse(el('records').value)})}));refreshAll()}catch(e){show('ingest-output',{error:e.message})}}
async function search(){try{show('search-output',await api('/api/search',{method:'POST',body:JSON.stringify({...scope(),query:el('query').value,top_k:5})}))}catch(e){show('search-output',{error:e.message})}}
async function loadConflicts(){try{const q=new URLSearchParams(scope());const data=await api('/api/conflicts?'+q);show('conflict-output',data);if(data[0])el('conflict-id').value=data[0].id}catch(e){show('conflict-output',{error:e.message})}}
async function resolveConflict(){try{show('conflict-output',await api('/api/conflicts/resolve',{method:'POST',body:JSON.stringify({...scope(),memory_id:el('conflict-id').value,strategy:el('strategy').value})}));refreshAll()}catch(e){show('conflict-output',{error:e.message})}}
async function previewForget(){try{const data=await api('/api/forget/preview',{method:'POST',body:JSON.stringify({...scope(),instruction:el('forget-text').value})});el('plan-id').value=data.id;show('forget-output',data)}catch(e){show('forget-output',{error:e.message})}}
async function confirmForget(){try{show('forget-output',await api('/api/forget/confirm',{method:'POST',body:JSON.stringify({...scope(),plan_id:el('plan-id').value})}));refreshAll()}catch(e){show('forget-output',{error:e.message})}}
refreshAll();
</script></body></html>"""


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
                if parsed.path == "/api/ingest":
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
                        min_score=float(body.get("min_score", 0.08)),
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

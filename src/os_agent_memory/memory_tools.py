"""Bound KylinBot-style tools; model arguments cannot forge runtime consent."""
from __future__ import annotations
import json
from queue import Queue, Empty
from threading import Lock, Thread
import time
import uuid

from .file_memory import FileMemory
from .memory_store import MemoryStore


class LocalIndexSelector:
    """Explicit diagnostic fallback, NOT the official LLM Selector."""
    def __call__(self, query, headers):
        tokens = MemoryStore._lexical_tokens(query)
        ranked = []
        for row in headers:
            terms = MemoryStore._lexical_tokens(row["name"] + " " + row["description"])
            score = MemoryStore._lexical_similarity(tokens, terms)
            if score > .1:
                ranked.append((score, row["key"]))
        return [key for _, key in sorted(ranked, key=lambda row: (-row[0], row[1]))[:5]]


class MemoryTools:
    def __init__(self, workspace, *, selector=None, timeout_seconds=5, max_bytes=16 * 1024):
        if timeout_seconds <= 0 or max_bytes < 256:
            raise ValueError("invalid selector or result budget")
        self.store = FileMemory(workspace)
        self.selector, self.timeout_seconds, self.max_bytes = selector, timeout_seconds, max_bytes
        self._selector_busy = Lock()
        self._deletions = {}

    def _select(self, query, headers):
        if self.selector is None:
            raise RuntimeError("selector_missing")
        if not self._selector_busy.acquire(blocking=False):
            raise RuntimeError("selector_busy")
        output = Queue(maxsize=1)
        def work():
            try:
                output.put((True, self.selector(query, headers)))
            except Exception:
                output.put((False, None))
            finally:
                self._selector_busy.release()
        Thread(target=work, daemon=True).start()
        try:
            ok, selected = output.get(timeout=self.timeout_seconds)
        except Empty:
            raise RuntimeError("selector_timeout") from None
        valid = {row["key"] for row in headers}
        if not ok or type(selected) is not list or any(type(key) is not str or key not in valid for key in selected):
            raise RuntimeError("selector_invalid")
        if len(selected) != len(set(selected)):
            raise RuntimeError("selector_duplicate")
        return selected[:5]

    def memory_recall(self, query):
        if type(query) is not str or not query.strip() or len(query.encode()) > 4096:
            raise ValueError("query must be a nonempty bounded string")
        rows, returned, status, selected = [], [], "ok", []
        safe_query = self.store.filter.redact(query)[0]
        try:
            rows = self.store.headers()
            if rows:
                selected = self._select(query, rows)
            for key in selected:
                # Read only after the COMPLETE selector response is validated.
                memory = self.store.read(key)
                fragment = json.dumps({"untrusted_saved_memory_verify_current_state": memory}, ensure_ascii=False)
                if len(("\n".join([*returned, fragment])).encode()) > self.max_bytes - 220:
                    status = "budget_limited"
                    break
                returned.append(fragment)
        except Exception:
            returned = []
            status = "unavailable"
        body = "\n".join(returned) or "No memories matching " + json.dumps(safe_query[:32], ensure_ascii=False)
        stats = f"Recall stats: candidates={len(rows)} selected={len(selected)} returned={len(returned)} status={status}"
        result = body + "\n" + stats
        if len(result.encode()) > self.max_bytes:
            return "No memories matching query\nRecall stats: returned=0 status=budget_limited"
        return result

    def forget_preview(self, query):
        headers = self.store.headers()
        selected = LocalIndexSelector()(query, headers)
        candidates = [self.store.read(key) for key in selected]
        token = uuid.uuid4().hex
        self._deletions[token] = {"expires": time.monotonic() + 300,
                                  "candidates": {row["key"]: row["revision"] for row in candidates}}
        return {"confirmation_token": token, "requires_one_explicit_key": True,
                "candidates": [{key: row[key] for key in ("key", "name", "description")} for row in candidates]}

    def forget_confirm(self, token, key, *, context):
        plan = self._deletions.get(token)
        if not plan or plan["expires"] < time.monotonic() or key not in plan["candidates"]:
            raise ValueError("missing, expired or mismatched deletion confirmation")
        result = self.store.delete(key, context=context, expected_revision=plan["candidates"][key])
        del self._deletions[token]
        return result

    def dispatch(self, tool, arguments, *, context):
        if type(arguments) is not dict:
            raise ValueError("tool arguments must be an object")
        if tool == "memory_recall" and set(arguments) == {"query"}:
            return self.memory_recall(arguments["query"])
        if tool == "memory_save" and set(arguments) <= {"kind", "slug", "name", "description", "body", "expected_revision"}:
            return self.store.write(**arguments, context=context)
        if tool == "memory_forget_preview" and set(arguments) == {"query"}:
            return self.forget_preview(arguments["query"])
        if tool == "memory_forget_confirm" and set(arguments) == {"token", "key"}:
            return self.forget_confirm(**arguments, context=context)
        raise ValueError("unknown tool or invalid argument contract")

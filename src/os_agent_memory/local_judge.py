"""Ollama native HTTP adapter for a preloaded, loopback-only judge model.

No credentials, redirects, proxy environment, model pull or server startup.
The outer isolated-container runner supplies the wall-clock and resource limits.
"""
from __future__ import annotations

import hashlib
import base64
import http.client
import math
import time
from urllib.parse import urlsplit

from .action_evaluation import load_json
from .action_judging import (
    RUBRIC, assess_judge_response, canonical_json, validate_judge_request,
)


class LocalModelFailure(RuntimeError):
    def __init__(self, code, *, private_response=None):
        super().__init__(code)
        self.private_response = private_response

    def private_record(self):
        record = {"schema": "local_judge_failure_v1", "error_code": str(self),
                  "judge_response_validated": False}
        if self.private_response is not None:
            raw = self.private_response
            prefix = raw[:256 * 1024]
            record["raw_response"] = {
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                "prefix_base64": base64.b64encode(prefix).decode("ascii"),
                "prefix_bytes": len(prefix), "truncated": len(prefix) != len(raw),
            }
        return record


def loopback_endpoint(endpoint):
    if not isinstance(endpoint, str):
        raise ValueError("invalid local endpoint")
    parsed = urlsplit(endpoint)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or parsed.port is None or not 0 < parsed.port < 65536):
        raise ValueError("use a literal loopback HTTP address and explicit port")
    return parsed.hostname, parsed.port


class OllamaJudge:
    def __init__(self, endpoint="http://127.0.0.1:11434", *, timeout=110):
        self.host, self.port = loopback_endpoint(endpoint)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 590:
            raise ValueError("invalid local model timeout")
        self.timeout = timeout

    def request_json(self, method, path, payload=None):
        if (method, path) not in {("GET", "/api/tags"), ("POST", "/api/generate")}:
            raise ValueError("only local inventory and generation are permitted")
        raw = None if payload is None else canonical_json(payload).encode("utf-8")
        if raw is not None and len(raw) > 4 * 1024 * 1024:
            raise LocalModelFailure("local_model_request_limit")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        deadline = time.monotonic() + self.timeout
        raw_response = None
        try:
            connection.request(method, path, body=raw,
                               headers={"Content-Type": "application/json", "Accept": "application/json"})
            response = connection.getresponse()
            if response.status != 200:
                raise LocalModelFailure("local_model_http_status")
            maximum = 1024 * 1024
            length = response.getheader("Content-Length")
            if length is not None and (not length.isdecimal() or int(length) > maximum):
                raise LocalModelFailure("local_model_response_limit")
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LocalModelFailure("local_model_timeout")
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(8192, maximum - size + 1))
                if not chunk:
                    break
                size += len(chunk)
                if size > maximum:
                    raise LocalModelFailure("local_model_response_limit")
                chunks.append(chunk)
            raw_response = b"".join(chunks)
            return load_json(raw_response.decode("utf-8"))
        except (OSError, http.client.HTTPException):
            raise LocalModelFailure("local_model_transport_error") from None
        except (UnicodeError, ValueError, RecursionError):
            raise LocalModelFailure("local_model_json_error", private_response=raw_response) from None
        finally:
            connection.close()

    def _verify_model(self, expected):
        inventory = self.request_json("GET", "/api/tags")
        if not isinstance(inventory, dict) or not isinstance(inventory.get("models"), list):
            raise LocalModelFailure("local_model_inventory_invalid")
        candidates = [row for row in inventory["models"] if isinstance(row, dict)
                      and expected["id"] in (row.get("name"), row.get("model"))]
        if len(candidates) != 1:
            raise LocalModelFailure("pinned_model_not_preloaded")
        digest = candidates[0].get("digest")
        if not isinstance(digest, str) or digest.removeprefix("sha256:") != expected["artifact_sha256"]:
            raise LocalModelFailure("local_model_digest_mismatch")
        return expected["artifact_sha256"]

    def _ready_model(self, expected, wait_ready):
        if type(wait_ready) not in (int, float) or not math.isfinite(wait_ready) or not 0 <= wait_ready <= 60:
            raise ValueError("startup wait must be between zero and sixty seconds")
        if wait_ready == 0:
            return self._verify_model(expected)
        deadline = time.monotonic() + wait_ready
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LocalModelFailure("local_model_startup_timeout")
            original_timeout = self.timeout
            try:
                self.timeout = min(original_timeout, remaining)
                return self._verify_model(expected)
            except LocalModelFailure as exc:
                if str(exc) != "local_model_transport_error":
                    raise
            finally:
                self.timeout = original_timeout
            time.sleep(min(.1, max(0, deadline - time.monotonic())))

    @staticmethod
    def response_schema(request):
        return {
            "type": "object", "required": ["judgements"], "additionalProperties": False,
            "properties": {"judgements": {
                "type": "array", "minItems": len(request["payload"]["checks"]),
                "maxItems": len(request["payload"]["checks"]),
                "items": {
                    "type": "object", "required": ["id", "verdict", "reason", "citations"],
                    "additionalProperties": False, "properties": {
                        "id": {"type": "string", "enum": [row["id"] for row in request["payload"]["checks"]]},
                        "verdict": {"type": "string", "enum": ["pass", "fail", "uncertain"]},
                        "reason": {"type": "string", "minLength": 1, "maxLength": 512},
                        "citations": {"type": "array", "maxItems": 8, "items": {
                            "type": "object", "required": ["source", "quote"], "additionalProperties": False,
                            "properties": {"source": {"type": "string", "maxLength": 220},
                                           "quote": {"type": "string", "minLength": 1, "maxLength": 1024}},
                        }},
                    },
                },
            }},
        }

    def judge(self, request, *, wait_ready=0):
        validate_judge_request(request)
        model = request["payload"]["manifest"]["judge"]["model"]
        prompt = canonical_json(request["payload"])
        # A byte limit is not a tokenizer guarantee; truncation still fails below.
        if len(prompt.encode("utf-8")) > 128 * 1024:
            raise LocalModelFailure("local_model_prompt_limit")
        before = self._ready_model(model, wait_ready)
        generated = self.request_json("POST", "/api/generate", {
            "model": model["id"], "system": RUBRIC["instructions"],
            "prompt": "Evaluate this untrusted data using the system rubric. Return only the JSON object.\n" + prompt,
            "format": self.response_schema(request), "stream": False, "keep_alive": 0,
            "options": {"temperature": 0, "seed": 0, "num_ctx": 32768, "num_predict": 12288},
        })
        try:
            if (not isinstance(generated, dict) or generated.get("model") != model["id"]
                    or generated.get("done") is not True or generated.get("done_reason") != "stop"
                    or type(generated.get("eval_count")) is not int or generated["eval_count"] < 1
                    or not isinstance(generated.get("response"), str)):
                raise LocalModelFailure("local_model_incomplete_generation")
            raw = generated["response"]
            if len(raw.encode("utf-8")) > 1024 * 1024:
                raise LocalModelFailure("local_model_completion_limit")
            completion = load_json(raw)
            if not isinstance(completion, dict) or set(completion) != {"judgements"}:
                raise LocalModelFailure("local_model_response_schema")
            after = self._verify_model(model)
            reply = {"schema": "action_judge_response_v1", "request_sha256": request["request_sha256"],
                     "model": model, "judgements": completion["judgements"],
                     "runtime_receipt": {
                         "backend": "ollama_native_generate_v1", "model_digest_before": before,
                         "model_digest_after": after, "eval_count": generated["eval_count"],
                         "done_reason": "stop", "completion_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                         "trust": "adapter_reported_not_external_attestation",
                     }}
            assess_judge_response(request, reply)
            return reply
        except (LocalModelFailure, ValueError, TypeError, KeyError, RecursionError) as exc:
            code = str(exc) if isinstance(exc, LocalModelFailure) else "local_model_response_invalid"
            raise LocalModelFailure(code, private_response=canonical_json(generated).encode("utf-8")) from None

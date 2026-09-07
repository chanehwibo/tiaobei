import ctypes as C
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.kylin_native import NativeEmbeddingClient, NativeSDKError, _encode_library
from os_agent_memory.provider_config import create_provider


class FakeLibrary:
    def __init__(self, *, init_code=0, result_code=0, length=2, values=(3., 4.), success=True):
        self.init_code, self.result_code, self.length = init_code, result_code, length
        self.values = (C.c_float * len(values))(*values)
        self.success = success
        self.released = []
    def text_embedding_create_session(self): return 1
    def text_embedding_init_session(self, session): return self.init_code
    def text_embedding_init_model(self, session, model): return 0
    def text_embedding(self, session, text, result):
        C.cast(result, C.POINTER(C.c_void_p))[0] = 2
        return self.success
    def embedding_result_get_error_code(self, result): return self.result_code
    def embedding_result_get_vector_length(self, result): return self.length
    def embedding_result_get_vector_data(self, result): return self.values
    def embedding_result_destroy(self, result): self.released.append("result")
    def text_embedding_destroy_session(self, session): self.released.append("session")


class NativeBindingTests(unittest.TestCase):
    def client(self):
        return NativeEmbeddingClient(library_path=str(Path("missing-sdk.so").resolve()),
                                     model_name="explicit-test-model", dimensions=2, timeout_seconds=3)

    def test_native_lifetime_and_utf8(self):
        lib = FakeLibrary()
        self.assertEqual(_encode_library(lib, "项目记忆", "指定模型", 2), [3., 4.])
        self.assertEqual(lib.released, ["result", "session"])

    def test_native_errors_release_owned_resources(self):
        for kwargs, released in (({"init_code": 8}, ["session"]),
                ({"result_code": 9}, ["result", "session"]),
                ({"success": False}, ["result", "session"]),
                ({"length": 999999999}, ["result", "session"]),
                ({"values": (float("nan"), 1.)}, ["result", "session"]),
                ({"values": (0., 0.)}, ["result", "session"])):
            with self.subTest(kwargs=kwargs):
                lib = FakeLibrary(**kwargs)
                with self.assertRaises(NativeSDKError):
                    _encode_library(lib, "test", "model", 2)
                self.assertEqual(lib.released, released)

    def test_subprocess_boundary_and_normalization(self):
        child = subprocess.CompletedProcess([], 0, json.dumps({"status": "ok", "vector": [3, 4]}).encode())
        with patch("os_agent_memory.kylin_native.subprocess.run", return_value=child) as run:
            self.assertEqual(self.client().encode("private input"), [.6, .8])
            self.assertNotIn("private input", str(run.call_args.args[0]))
            self.assertEqual(json.loads(run.call_args.kwargs["input"])["text"], "private input")
            self.assertEqual(run.call_args.kwargs["timeout"], 3)

    def test_worker_failure_timeout_and_invalid_vectors_fail_closed(self):
        outputs = [b'{}', b'not json', b'{"status":"ok","vector":[0,0]}',
                   b'{"status":"ok","vector":[1]}', b'{"status":"ok","vector":[true,1]}',
                   b'{"status":"ok","vector":[NaN,1]}']
        for value in outputs:
            with patch("os_agent_memory.kylin_native.subprocess.run", return_value=subprocess.CompletedProcess([], 0, value)):
                with self.assertRaises(NativeSDKError): self.client().encode("test")
        with patch("os_agent_memory.kylin_native.subprocess.run", side_effect=subprocess.TimeoutExpired([], 3)):
            with self.assertRaises(TimeoutError): self.client().encode("test")
        with patch("os_agent_memory.kylin_native.subprocess.run", return_value=subprocess.CompletedProcess([], -11, b"")):
            with self.assertRaises(NativeSDKError): self.client().encode("test")

    def test_real_worker_missing_library_never_falls_back(self):
        with self.assertRaises(NativeSDKError): self.client().encode("sdk unavailable test")
        for value in ("", "a\0b", "汉"*6000):
            with self.assertRaises(ValueError): self.client().encode(value)

    def test_provider_config_uses_explicit_native_identity(self):
        provider = create_provider({"provider": "kylin-native", "model_version": "test-only",
            "dimensions": 2, "native": {"library_path": str(Path("absent.so").resolve()), "model_name": "test"}})
        self.assertEqual(provider.identity["provider"], "kylin-native")
        self.assertIsNone(provider.timeout_seconds)
        with self.assertRaises(NativeSDKError): provider.encode("test")

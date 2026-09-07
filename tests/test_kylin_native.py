import ctypes as C
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.kylin_native import (
    NativeEmbeddingClient, NativeSDKError, _encode_library, _models_library, discover_native_models,
    probe_native_default,
)
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


class ModelLibrary(FakeLibrary):
    def __init__(self, *, count=1, dimensions=768, model_name=b"installed-test-model", **kwargs):
        super().__init__(**kwargs)
        self.count, self.dimensions, self.model_name = count, dimensions, model_name
    def text_embedding_get_model_list(self, session, error): return 2
    def embedding_model_list_get_count(self, models, error): return self.count
    def embedding_model_list_get_model(self, models, index, error): return index + 3
    def embedding_model_info_get_model_name(self, item, error): return self.model_name
    def embedding_model_info_get_model_dim(self, item, error): return self.dimensions


class NativeModelDiscoveryTests(unittest.TestCase):
    def test_models_are_session_owned_and_zero_models_is_valid(self):
        for count in (0, 1):
            lib = ModelLibrary(count=count)
            rows = _models_library(lib)
            self.assertEqual(len(rows), count)
            self.assertEqual(lib.released, ["session"])

    def test_invalid_metadata_and_session_errors_fail_closed(self):
        for kwargs in ({"count": 129}, {"count": -1}, {"count": 2}, {"dimensions": 0},
                       {"model_name": b""}, {"model_name": b"bad\nname"}, {"init_code": 19}):
            lib = ModelLibrary(**kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(NativeSDKError):
                _models_library(lib)
            self.assertEqual(lib.released, ["session"])

    def test_discovery_subprocess_timeout_and_untrusted_error_details(self):
        path = str(Path("absent.so").resolve())
        payload = {"status": "ok", "models": [{"name": "installed", "dimensions": 768}]}
        with patch("os_agent_memory.kylin_native.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, json.dumps(payload).encode())) as run:
            self.assertEqual(discover_native_models(path), payload["models"])
            self.assertEqual(json.loads(run.call_args.kwargs["input"])["operation"], "models")
        with patch("os_agent_memory.kylin_native.subprocess.run", side_effect=subprocess.TimeoutExpired([], 1)):
            with self.assertRaises(TimeoutError):
                discover_native_models(path, timeout_seconds=1)
        payload = {"status": "unavailable", "stage": "session_init", "error_code": 19, "message": "private"}
        with patch("os_agent_memory.kylin_native.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, json.dumps(payload).encode())):
            with self.assertRaises(NativeSDKError) as error:
                discover_native_models(path)
            self.assertEqual(error.exception.stage, "session_init")
            self.assertEqual(error.exception.code, 19)
            self.assertNotIn("private", str(error.exception))

    def test_model_discovery_does_not_claim_embedding_or_agent_execution(self):
        from scripts.check_kylin_native import diagnose
        with patch("scripts.check_kylin_native.discover_native_models", return_value=[]):
            result = diagnose(library_path=Path("absent.so").resolve())
            self.assertTrue(result["model_list_executed"])
            self.assertFalse(result["real_embedding_executed"])
            self.assertFalse(result["agent_executed"])
            self.assertFalse(result["official_validation_ready"])
            result = diagnose(library_path=Path("absent.so").resolve(), probe_model="not-installed")
            self.assertFalse(result["real_embedding_executed"])
            self.assertEqual(result["error_type"], "ValueError")

    def test_legacy_probe_is_explicit_and_does_not_claim_model_identity(self):
        from scripts.check_kylin_native import diagnose
        path = str(Path("absent.so").resolve())
        lib = FakeLibrary()
        with patch.object(lib, "text_embedding_init_model", side_effect=AssertionError("not in legacy ABI")):
            self.assertEqual(_encode_library(lib, "diagnostic", None, None), [3., 4.])
        self.assertEqual(lib.released, ["result", "session"])
        with patch("os_agent_memory.kylin_native._run_worker", return_value={"dimensions": 768}) as worker:
            self.assertEqual(probe_native_default(path), {"dimensions": 768, "model_identity_verified": False})
            self.assertEqual(worker.call_args.args[0]["operation"], "legacy_probe")
        with patch("scripts.check_kylin_native.probe_native_default",
                   return_value={"dimensions": 768, "model_identity_verified": False}):
            result = diagnose(library_path=path, probe_legacy_default=True)
        self.assertTrue(result["real_embedding_executed"])
        self.assertFalse(result["model_list_executed"])
        self.assertFalse(result["model_identity_verified"])
        self.assertFalse(result["vector_database_connected"])
        self.assertFalse(result["official_validation_ready"])
        with self.assertRaises(ValueError):
            diagnose(library_path=path, probe_legacy_default=True, probe_model="unverified")

    def test_legacy_probe_rejects_unbounded_or_invalid_dimensions(self):
        for dimensions in (0, 16385, True, None, "768"):
            with patch("os_agent_memory.kylin_native._run_worker", return_value={"dimensions": dimensions}):
                with self.assertRaises(NativeSDKError):
                    probe_native_default(str(Path("absent.so").resolve()))

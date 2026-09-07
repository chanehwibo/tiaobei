"""Isolated binding to the published kysdk-coreai-embedding C ABI.

Each request owns a child process and a native session. This favors bounded
failure and reliable cleanup over speed; measure native latency separately.
No SDK or model is installed, downloaded, or silently replaced here.
"""
from __future__ import annotations

import ctypes as C
import json
import math
from pathlib import Path
import platform
import subprocess
import sys


class NativeSDKError(RuntimeError):
    pass


def _load_library(path):
    if platform.system() != "Linux":
        raise NativeSDKError("native Kylin SDK requires Linux")
    path = Path(path)
    if not path.is_absolute() or not path.is_file():
        raise NativeSDKError("an existing absolute SDK library path is required")
    lib = C.CDLL(str(path))
    ptr = C.c_void_p
    signatures = {
        "text_embedding_create_session": ([], ptr),
        "text_embedding_destroy_session": ([C.POINTER(ptr)], None),
        "text_embedding_init_session": ([ptr], C.c_int),
        "text_embedding_init_model": ([ptr, C.c_char_p], C.c_int),
        "text_embedding": ([ptr, C.c_char_p, C.POINTER(ptr)], C.c_bool),
        "embedding_result_get_vector_data": ([ptr], C.POINTER(C.c_float)),
        "embedding_result_get_vector_length": ([ptr], C.c_int),
        "embedding_result_get_error_code": ([ptr], C.c_int),
        "embedding_result_destroy": ([C.POINTER(ptr)], None),
    }
    for name, (args, result) in signatures.items():
        function = getattr(lib, name)
        function.argtypes, function.restype = args, result
    return lib


def _encode_library(lib, text, model_name, dimensions):
    session = C.c_void_p(lib.text_embedding_create_session())
    if not session:
        raise NativeSDKError("SDK did not create a session")
    result = C.c_void_p()
    try:
        code = lib.text_embedding_init_session(session)
        if code != 0:
            raise NativeSDKError(f"SDK session initialization failed ({code})")
        code = lib.text_embedding_init_model(session, model_name.encode("utf-8"))
        if code != 0:
            raise NativeSDKError(f"SDK model initialization failed ({code})")
        if not lib.text_embedding(session, text.encode("utf-8"), C.byref(result)) or not result:
            raise NativeSDKError("SDK embedding call failed")
        code = lib.embedding_result_get_error_code(result)
        if code != 0:
            raise NativeSDKError(f"SDK embedding result failed ({code})")
        length = lib.embedding_result_get_vector_length(result)
        if length != dimensions:
            raise NativeSDKError("SDK output dimension mismatch")
        values = lib.embedding_result_get_vector_data(result)
        if not values:
            raise NativeSDKError("SDK returned a null vector")
        vector = [float(values[index]) for index in range(length)]
        if not all(math.isfinite(value) for value in vector) or not any(vector):
            raise NativeSDKError("SDK returned a non-finite or zero vector")
        return vector
    finally:
        if result:
            lib.embedding_result_destroy(C.byref(result))
        lib.text_embedding_destroy_session(C.byref(session))


class NativeEmbeddingClient:
    def __init__(self, *, library_path, model_name, dimensions, timeout_seconds=10):
        if not isinstance(library_path, str) or not Path(library_path).is_absolute():
            raise ValueError("native library_path must be absolute")
        if not isinstance(model_name, str) or not model_name.strip() or "\0" in model_name:
            raise ValueError("an explicit native model_name is required")
        if type(dimensions) is not int or not 1 <= dimensions <= 16384:
            raise ValueError("native dimensions must be 1..16384")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120:
            raise ValueError("native timeout must be finite and within 0..120 seconds")
        self.library_path, self.model_name = library_path, model_name
        self.dimensions, self.timeout_seconds = dimensions, timeout_seconds

    def encode(self, text):
        if not isinstance(text, str) or not text or "\0" in text or len(text.encode("utf-8")) > 16384:
            raise ValueError("native input must be nonempty UTF-8 text within 16384 bytes, without NUL")
        payload = {"library_path": self.library_path, "model_name": self.model_name,
                   "dimensions": self.dimensions, "text": text}
        try:
            result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--worker"],
                input=json.dumps(payload).encode("utf-8"), stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=self.timeout_seconds, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise TimeoutError("native SDK worker timed out and was terminated") from None
        if result.returncode != 0:
            raise NativeSDKError("native SDK worker exited unsuccessfully")
        try:
            response = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            raise NativeSDKError("invalid native SDK worker response") from None
        if not isinstance(response, dict) or response.get("status") != "ok":
            raise NativeSDKError("native SDK unavailable or incompatible; run the SDK diagnostic")
        vector = response.get("vector")
        if (not isinstance(vector, list) or len(vector) != self.dimensions
                or not all(type(value) in (int, float) and math.isfinite(value) for value in vector)
                or not any(vector)):
            raise NativeSDKError("invalid native SDK vector")
        norm = math.hypot(*vector)
        return [value / norm for value in vector]

    def similarity(self, left, right):
        return sum(a*b for a,b in zip(self.encode(left), self.encode(right)))


def _worker():
    import os
    # Reserve stdout for the bounded JSON result; native service logs may include
    # user text, so discard them in this child process.
    output_fd = os.dup(sys.stdout.fileno())
    with open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        try:
            data = json.loads(sys.stdin.buffer.read(131073))
            client = NativeEmbeddingClient(library_path=data["library_path"], model_name=data["model_name"],
                                           dimensions=data["dimensions"])
            text = data["text"]
            if not isinstance(text, str) or not text or "\0" in text or len(text.encode("utf-8")) > 16384:
                raise ValueError("invalid input")
            vector = _encode_library(_load_library(client.library_path), text, client.model_name, client.dimensions)
            result = {"status": "ok", "vector": vector}
        except Exception as exc:
            result = {"status": "unavailable", "error_type": type(exc).__name__}
        with os.fdopen(output_fd, "w", encoding="utf-8") as output:
            output.write(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("internal worker only")
    _worker()

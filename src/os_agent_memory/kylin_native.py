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
    def __init__(self, message, *, stage=None, code=None):
        super().__init__(message)
        self.stage, self.code = stage, code


def _load_library(path, *, models=False, legacy_probe=False):
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
        "text_embedding": ([ptr, C.c_char_p, C.POINTER(ptr)], C.c_bool),
        "embedding_result_get_vector_data": ([ptr], C.POINTER(C.c_float)),
        "embedding_result_get_vector_length": ([ptr], C.c_int),
        "embedding_result_get_error_code": ([ptr], C.c_int),
        "embedding_result_destroy": ([C.POINTER(ptr)], None),
    }
    if not legacy_probe:
        signatures["text_embedding_init_model"] = ([ptr, C.c_char_p], C.c_int)
    if models:
        error = C.POINTER(C.c_int)
        signatures.update({
            "text_embedding_get_model_list": ([ptr, error], ptr),
            "embedding_model_list_get_count": ([ptr, error], C.c_int),
            "embedding_model_list_get_model": ([ptr, C.c_int, error], ptr),
            "embedding_model_info_get_model_name": ([ptr, error], C.c_char_p),
            "embedding_model_info_get_model_dim": ([ptr, error], C.c_int),
        })
    for name, (args, result) in signatures.items():
        try:
            function = getattr(lib, name)
        except AttributeError:
            raise NativeSDKError("SDK required symbol unavailable", stage="library_symbols") from None
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
            raise NativeSDKError("SDK session initialization failed", stage="session_init", code=code)
        if model_name is not None:
            code = lib.text_embedding_init_model(session, model_name.encode("utf-8"))
            if code != 0:
                raise NativeSDKError("SDK model initialization failed", stage="model_init", code=code)
        if not lib.text_embedding(session, text.encode("utf-8"), C.byref(result)) or not result:
            raise NativeSDKError("SDK embedding call failed")
        code = lib.embedding_result_get_error_code(result)
        if code != 0:
            raise NativeSDKError("SDK embedding result failed", stage="embedding_result", code=code)
        length = lib.embedding_result_get_vector_length(result)
        if not 1 <= length <= 16384 or (dimensions is not None and length != dimensions):
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


def _model_rows_valid(rows):
    return (
        isinstance(rows, list) and len(rows) <= 128
        and all(isinstance(row, dict) and set(row) == {"name", "dimensions"}
            and isinstance(row["name"], str) and 0 < len(row["name"].encode("utf-8")) <= 512
            and not any(char in row["name"] for char in "\0\r\n")
            and type(row["dimensions"]) is int and 1 <= row["dimensions"] <= 16384 for row in rows)
        and len({row["name"] for row in rows}) == len(rows)
    )


def _models_library(lib):
    session = C.c_void_p(lib.text_embedding_create_session())
    if not session:
        raise NativeSDKError("SDK did not create a session", stage="session_init")
    try:
        code = lib.text_embedding_init_session(session)
        if code != 0:
            raise NativeSDKError("SDK session initialization failed", stage="session_init", code=code)

        def read(function, *args):
            error = C.c_int()
            value = function(*args, C.byref(error))
            if error.value != 0:
                raise NativeSDKError("SDK model discovery failed", stage="model_list", code=error.value)
            return value

        models = read(lib.text_embedding_get_model_list, session)
        if not models:
            raise NativeSDKError("SDK returned a null model list", stage="model_list")
        count = read(lib.embedding_model_list_get_count, models)
        if not 0 <= count <= 128:
            raise NativeSDKError("SDK model count exceeds budget", stage="model_list")
        rows = []
        for index in range(count):
            item = read(lib.embedding_model_list_get_model, models, index)
            if not item:
                raise NativeSDKError("SDK returned a null model entry", stage="model_list")
            name = read(lib.embedding_model_info_get_model_name, item)
            dimensions = read(lib.embedding_model_info_get_model_dim, item)
            if not name:
                raise NativeSDKError("SDK returned an empty model name", stage="model_list")
            rows.append({"name": name.decode("utf-8"), "dimensions": dimensions})
        if not _model_rows_valid(rows):
            raise NativeSDKError("SDK model metadata is invalid", stage="model_list")
        return rows
    finally:
        # Model-list and model-info pointers are owned by the native session.
        lib.text_embedding_destroy_session(C.byref(session))


def _validate_location_timeout(library_path, timeout_seconds):
    if not isinstance(library_path, str) or not Path(library_path).is_absolute():
        raise ValueError("native library_path must be absolute")
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120:
        raise ValueError("native timeout must be finite and within 0..120 seconds")


def _run_worker(payload, timeout_seconds):
    try:
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--worker"],
            input=json.dumps(payload).encode("utf-8"), stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=timeout_seconds, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise TimeoutError("native SDK worker timed out and was terminated") from None
    if result.returncode != 0:
        raise NativeSDKError("native SDK worker exited unsuccessfully")
    if len(result.stdout) > 1024 * 1024:
        raise NativeSDKError("native SDK worker response exceeds budget")
    try:
        response = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise NativeSDKError("invalid native SDK worker response") from None
    if not isinstance(response, dict) or response.get("status") != "ok":
        details = response if isinstance(response, dict) else {}
        stage = details.get("stage")
        stage = stage if stage in {"library_symbols", "session_init", "model_init", "model_list", "embedding_result"} else None
        code = details.get("error_code")
        raise NativeSDKError("native SDK unavailable or incompatible; run the SDK diagnostic",
                             stage=stage, code=code if type(code) is int else None)
    return response


def discover_native_models(library_path, *, timeout_seconds=10):
    _validate_location_timeout(library_path, timeout_seconds)
    response = _run_worker({"operation": "models", "library_path": library_path}, timeout_seconds)
    rows = response.get("models")
    if not _model_rows_valid(rows):
        raise NativeSDKError("invalid native SDK model metadata")
    return rows


def probe_native_default(library_path, *, timeout_seconds=10):
    """Explicit legacy diagnostic only; never a service-provider fallback."""
    _validate_location_timeout(library_path, timeout_seconds)
    response = _run_worker({"operation": "legacy_probe", "library_path": library_path}, timeout_seconds)
    dimensions = response.get("dimensions")
    if type(dimensions) is not int or not 1 <= dimensions <= 16384:
        raise NativeSDKError("invalid native SDK probe dimensions")
    return {"dimensions": dimensions, "model_identity_verified": False}


class NativeEmbeddingClient:
    def __init__(self, *, library_path, model_name, dimensions, timeout_seconds=10):
        _validate_location_timeout(library_path, timeout_seconds)
        if not isinstance(model_name, str) or not model_name.strip() or "\0" in model_name:
            raise ValueError("an explicit native model_name is required")
        if type(dimensions) is not int or not 1 <= dimensions <= 16384:
            raise ValueError("native dimensions must be 1..16384")
        self.library_path, self.model_name = library_path, model_name
        self.dimensions, self.timeout_seconds = dimensions, timeout_seconds

    def encode(self, text):
        if not isinstance(text, str) or not text or "\0" in text or len(text.encode("utf-8")) > 16384:
            raise ValueError("native input must be nonempty UTF-8 text within 16384 bytes, without NUL")
        payload = {"library_path": self.library_path, "model_name": self.model_name,
                   "dimensions": self.dimensions, "text": text}
        response = _run_worker(payload, self.timeout_seconds)
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
            if data.get("operation") == "models":
                result = {"status": "ok", "models": _models_library(_load_library(data["library_path"], models=True))}
            elif data.get("operation") == "legacy_probe":
                vector = _encode_library(_load_library(data["library_path"], legacy_probe=True),
                                         "Native embedding diagnostic", None, None)
                result = {"status": "ok", "dimensions": len(vector)}
            else:
                client = NativeEmbeddingClient(library_path=data["library_path"], model_name=data["model_name"],
                                               dimensions=data["dimensions"])
                text = data["text"]
                if not isinstance(text, str) or not text or "\0" in text or len(text.encode("utf-8")) > 16384:
                    raise ValueError("invalid input")
                vector = _encode_library(_load_library(client.library_path), text, client.model_name, client.dimensions)
                result = {"status": "ok", "vector": vector}
        except Exception as exc:
            result = {"status": "unavailable", "error_type": type(exc).__name__}
            if isinstance(exc, NativeSDKError):
                result.update(stage=exc.stage, error_code=exc.code)
        with os.fdopen(output_fd, "w", encoding="utf-8") as output:
            output.write(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("internal worker only")
    _worker()

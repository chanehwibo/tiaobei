"""Inspect native SDK availability; only an actual vector call proves connection."""
import argparse
import ctypes.util
import json
from pathlib import Path
import platform
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from scripts.material_status import INITIAL_STATUS, SDK_RISK_STATUS
from os_agent_memory.official_contract import environment_identity
from os_agent_memory.provider_config import create_provider
from os_agent_memory.kylin_native import (
    NativeEmbeddingClient, NativeSDKError, discover_native_models, probe_native_default,
)


def diagnose(config=None, *, library_path=None, probe_model=None, probe_legacy_default=False, timeout_seconds=10):
    if config and (library_path or probe_model or probe_legacy_default):
        raise ValueError("choose a configuration or explicit model discovery, not both")
    if (probe_model or probe_legacy_default) and not library_path:
        raise ValueError("model probing requires an explicit library path")
    if probe_model and probe_legacy_default:
        raise ValueError("choose an explicit model or the legacy default diagnostic, not both")
    release = platform.freedesktop_os_release() if platform.system() == "Linux" else {}
    result = {"schema_version": 2,
        "display_status": INITIAL_STATUS, "latency_status": SDK_RISK_STATUS,
        "system": platform.system(), "machine": platform.machine(), "os_release": release,
        **environment_identity(platform.system(), release),
        "embedding_library": ctypes.util.find_library("kysdk-coreai-embedding"),
        "vector_client_library": ctypes.util.find_library("kysdk-vector-engine-client"),
        "real_embedding_executed": False, "vector_database_connected": False,
        "model_list_executed": False, "models": [],
        "probe_mode": ("configuration" if config else "legacy_runtime_default" if probe_legacy_default
                       else "explicit_model" if probe_model else "discovery"),
        "observations": 0, "single_probe_ms": None, "native_p95_ms": None,
        "native_latency_passed": False, "competition_ready": False,
        "model_identity_verified": False, "model_version_verified": False,
        "timing_boundary": "single_isolated_call_including_process_session_and_model_initialization",
        "commands": {name: shutil.which(name) for name in ("docker", "podman", "kylinbot", "kylin-bot")},
        "agent_executed": False, "container_sample_executed": False, "independent_judge_executed": False,
        "official_validation_ready": False,
        "scope": "native_environment_discovery_not_performance_or_official_validation"}
    if library_path:
        try:
            if probe_legacy_default:
                started = time.perf_counter()
                result["observations"] = 1
                try:
                    probe = probe_native_default(str(library_path), timeout_seconds=timeout_seconds)
                    result.update(probe, real_embedding_executed=True, model_version_verified=False)
                finally:
                    result["single_probe_ms"] = (time.perf_counter() - started) * 1000
            else:
                result["models"] = discover_native_models(str(library_path), timeout_seconds=timeout_seconds)
                result["model_list_executed"] = True
            if probe_model and not probe_legacy_default:
                model = next((row for row in result["models"] if row["name"] == probe_model), None)
                if model is None:
                    raise ValueError("requested model was not enumerated by the installed runtime")
                started = time.perf_counter()
                result["observations"] = 1
                try:
                    client = NativeEmbeddingClient(library_path=str(library_path), model_name=model["name"],
                                                   dimensions=model["dimensions"], timeout_seconds=timeout_seconds)
                    vector = client.encode("银河麒麟记忆接口适配自检")
                    result.update(real_embedding_executed=True, dimensions=len(vector),
                                  model_name=model["name"], model_version_verified=False)
                finally:
                    result["single_probe_ms"] = (time.perf_counter() - started) * 1000
        except Exception as exc:
            result["error_type"] = type(exc).__name__
            if isinstance(exc, NativeSDKError):
                result.update(error_stage=exc.stage, error_code=exc.code)
    if config:
        try:
            mapping = json.loads(Path(config).read_text(encoding="utf-8"))
            if mapping.get("provider") != "kylin-native":
                raise ValueError("only the native provider is accepted by this diagnostic")
            started = time.perf_counter()
            result["observations"] = 1
            try:
                provider = create_provider(mapping)
                vector = provider.encode("银河麒麟记忆接口适配自检")
                result.update(real_embedding_executed=True, dimensions=len(vector),
                              provider_identity=provider.identity)
            finally:
                result["single_probe_ms"] = (time.perf_counter() - started) * 1000
        except Exception as exc:
            result["error_type"] = type(exc).__name__
            if isinstance(exc, NativeSDKError):
                result.update(error_stage=exc.stage, error_code=exc.code)
    result["status"] = "embedding_connected" if result["real_embedding_executed"] else "not_connected"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-config", type=Path)
    parser.add_argument("--library-path", type=Path, help="enumerate models without loading or downloading one")
    parser.add_argument("--probe-model", help="probe exactly this previously enumerated installed model")
    parser.add_argument("--probe-legacy-default", action="store_true",
                        help="explicitly probe the old ABI runtime default; does not verify model identity")
    parser.add_argument("--timeout-seconds", type=float, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("choose a new native diagnostic output; existing evidence is immutable")
    result = diagnose(args.embedding_config, library_path=args.library_path,
                      probe_model=args.probe_model, probe_legacy_default=args.probe_legacy_default,
                      timeout_seconds=args.timeout_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["real_embedding_executed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Inspect native SDK availability; only an actual vector call proves connection."""
import argparse
import ctypes.util
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.official_contract import environment_identity
from os_agent_memory.provider_config import create_provider


def diagnose(config=None):
    release = platform.freedesktop_os_release() if platform.system() == "Linux" else {}
    result = {"system": platform.system(), "machine": platform.machine(), "os_release": release,
        **environment_identity(platform.system(), release),
        "embedding_library": ctypes.util.find_library("kysdk-coreai-embedding"),
        "vector_client_library": ctypes.util.find_library("kysdk-vector-engine-client"),
        "real_embedding_executed": False, "vector_database_connected": False,
        "official_validation_ready": False,
        "scope": "native_environment_discovery_not_performance_or_official_validation"}
    if config:
        try:
            mapping = json.loads(Path(config).read_text(encoding="utf-8"))
            if mapping.get("provider") != "kylin-native":
                raise ValueError("only the native provider is accepted by this diagnostic")
            provider = create_provider(mapping)
            vector = provider.encode("银河麒麟记忆接口适配自检")
            result.update(real_embedding_executed=True, dimensions=len(vector), provider_identity=provider.identity)
        except Exception as exc:
            result["error_type"] = type(exc).__name__
    result["status"] = "embedding_connected" if result["real_embedding_executed"] else "not_connected"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.embedding_config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["real_embedding_executed"] else 2)

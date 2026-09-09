"""Describe the native single-probe evidence without promoting it to a benchmark."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.material_status import INITIAL_STATUS, SDK_RISK_STATUS

PROBE = Path("artifacts/verification/round5/native/legacy_runtime_started.json")


def summarize_sdk_risk(root=ROOT):
    payload = (Path(root) / PROBE).read_bytes()
    probe = json.loads(payload)
    elapsed = probe.get("single_probe_ms")
    if (probe.get("real_embedding_executed") is not True
            or probe.get("probe_mode") != "legacy_runtime_default"
            or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed <= 0
            or type(probe.get("dimensions")) is not int or probe["dimensions"] <= 0):
        raise ValueError("expected genuine legacy native single-probe evidence")
    return {
        "schema_version": 1,
        "display_status": INITIAL_STATUS,
        "latency_status": SDK_RISK_STATUS,
        "scope": "historical_single_probe_not_native_latency_acceptance",
        "source": PROBE.as_posix(),
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "real_embedding_executed": True,
        "probe_mode": probe["probe_mode"],
        "dimensions": probe["dimensions"],
        "single_probe_ms": elapsed,
        "observations": 1,
        "timing_includes": ["child_process", "session", "model_initialization", "embedding"],
        "native_p95_ms": None,
        "native_latency_passed": False,
        "competition_ready": False,
        "model_identity_verified": probe.get("model_identity_verified") is True,
        "model_version_verified": probe.get("model_version_verified") is True,
        "vector_database_connected": probe.get("vector_database_connected") is True,
        "hash_results_are_native_evidence": False,
        "risks": [
            "Single probe exceeds 500ms; one observation cannot estimate P95.",
            "The current isolated-call provider initializes a process/session per call.",
            "Installed legacy ABI cannot verify the model; required new ABI symbols are absent.",
            "Native end-to-end search quality/latency and vector database roundtrip are unverified.",
        ],
        "retest_requirements": [
            "Record installed V11, CPU/RAM, SDK/runtime/model versions and binary/configuration hashes.",
            "Verify the actually selected native model, dimensions and no HashEmbedding fallback.",
            "Freeze at least 50 distinct requests, corpus, top_k and threshold before measuring.",
            "Report startup/initialization, first search and full service search separately.",
            "Retain all per-request errors/timeouts and all repetitions; do not drop slow requests.",
            "Run the five metric/safety gates on the native provider, including distractors and negatives.",
            "Require service-search P95 <= 500ms with zero discarded failures in the declared profile.",
            "Verify vector database create/write/search/delete separately if claimed as integrated.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = summarize_sdk_risk()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

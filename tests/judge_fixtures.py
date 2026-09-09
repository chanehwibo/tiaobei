"""Synthetic contract-test records only. Never use as external judge evidence."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.action_evaluation import make_cross_session_sample, run_sample
from os_agent_memory.action_judging import canonical_json, digest_json, evidence_sources


def synthetic_records(workspace):
    sample = make_cross_session_sample()
    manifest = {
        "schema": "action_run_manifest_v1", "run_id": "contract-self-test",
        "purpose": "integration",
        "frozen_at_utc": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(timespec="seconds"),
        "sample_sha256": digest_json(sample), "controller_source_sha256": "c" * 64,
        "roles": {"agent_operator": "self-test-agent", "judge_operator": "self-test-judge",
                  "label_custodian": "self-test-author"},
        "agent": {"image": "sha256:" + "a" * 64,
                  "model": {"id": "test-agent", "revision": "test-rev-a", "artifact_sha256": "d" * 64}},
        "judge": {"image": "sha256:" + "b" * 64,
                  "model": {"id": "test-judge", "revision": "test-rev-b", "artifact_sha256": "e" * 64}},
    }
    evidence = run_sample(sample, workspace, posthoc_mode="evidence_only", before_posthoc=lambda: None)
    evidence.update(scope=["configured_container_adapter_unverified_agent"],
        run_manifest_sha256=digest_json(manifest), controller_source_sha256=manifest["controller_source_sha256"],
        controller_source_unchanged=True, agent_model_declared=manifest["agent"]["model"],
        container={"engine": "docker", "image": manifest["agent"]["image"], "removed": True,
                   "guest_identity": {"is_required_v11": True}, "isolation_acknowledged_by_operator": True})
    return sample, evidence, manifest


def synthetic_reply(request):
    sources = evidence_sources(request["payload"]["evidence"])
    judgements = []
    for check in request["payload"]["checks"]:
        citations = []
        if not check["automatic_failure"]:
            if check["kind"] in {"action_slot", "reply_consistency"}:
                key = "artifact:" + check["path"]
                citations.append({"source": key, "quote": sources[key]})
            if check["kind"] == "reply_consistency":
                key = "response:" + check["turn_id"]
                citations.append({"source": key, "quote": sources[key]})
            if check["kind"] == "memory_slot":
                needle = canonical_json({check["slot"]: check["expected"]})
                key = next(k for k in check["sources"] if needle in sources[k])
                citations.append({"source": key, "quote": needle})
        judgements.append({"id": check["id"], "verdict": "pass",
                           "reason": "Synthetic validator self-test; not an LLM judgement.",
                           "citations": citations})
    return {"schema": "action_judge_response_v1", "request_sha256": request["request_sha256"],
            "model": request["payload"]["manifest"]["judge"]["model"], "judgements": judgements}

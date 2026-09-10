"""Compare versioned evidence policies on immutable, visible development cases."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from os_agent_memory.complex_retrieval import score_request, summarize_rows
from os_agent_memory.provider_config import provider_identity
from os_agent_memory.retrieval_evidence import MIN_COVERAGE, POLICIES
from os_agent_memory.schemas import KnowledgeMemory
from os_agent_memory.service import MemoryService
from scripts.verify_kylin_guest import file_hashes

DATA = Path("data/dev/evidence_coverage_v1.json")
SHA256 = "c615c042c4c912b1296c95f485fe28e108b442d4b7b025cf3457330ee4aa7a56"
CHALLENGE_DATA = Path("data/dev/evidence_coverage_challenge_v1.json")
CHALLENGE_SHA256 = "b4b81a47d46a46add96953bf4ff54e5db8a419b7930ac17545166831e1d61bd3"
METHOD = {
    "top_k": 3, "min_score": .265, "minimum_evidence_coverage": MIN_COVERAGE,
    "threshold_rule": "predeclared majority coverage; no frozen-test threshold sweep",
    "boundary": "MemoryService.search", "percentile": "nearest_rank", "rounds": 1,
    "policies": {
        "similarity": "legacy scoring without evidence abstention",
        "content_coverage_v1": "legacy top-k plus strict lexical coverage; no reranking",
        "focused_evidence_v2": "query focus with literal identity, exact-subject bundles and property-specific support",
    },
}


def load_suite(root=ROOT, *, challenge=False):
    root = Path(root)
    payload = (root / DATA).read_bytes()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError("development data changed; create a new version")
    suite = json.loads(payload)
    data_path, data_sha256 = DATA, SHA256
    if challenge:
        data_path = CHALLENGE_DATA
        payload = (root / data_path).read_bytes()
        if hashlib.sha256(payload).hexdigest() != CHALLENGE_SHA256:
            raise ValueError("development challenge changed; create a new version")
        additional = json.loads(payload)
        if additional.get("documents_from") != DATA.as_posix() or additional.get("documents_sha256") != SHA256:
            raise ValueError("challenge must use the unchanged development documents")
        suite = {**additional, "documents": suite["documents"]}
        data_sha256 = CHALLENGE_SHA256
    return suite, {
        "path": data_path.as_posix(), "sha256": data_sha256, "documents": len(suite["documents"]),
        "distinct_requests": len(suite["queries"]),
        "positive_requests": sum(bool(row["expected"]) for row in suite["queries"]),
        "no_answer_requests": sum(not row["expected"] for row in suite["queries"]),
        "challenge_added_after_initial_comparison": challenge,
    }


def evaluation_query(original):
    return {**original, "kind": "positive" if original["expected"] else "no_answer",
            "scenario": original["id"].rsplit("-", 1)[0], "category": "development"}


def evaluate(root=ROOT, *, challenge=False):
    root = Path(root)
    suite, dataset = load_suite(root, challenge=challenge)
    snapshot = file_hashes(root)
    service = MemoryService()
    for row in suite["documents"]:
        service.store.knowledge[row["id"]] = KnowledgeMemory(
            **row, tags=[], source_ids=[row["id"]], version=1,
            created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
            tenant_id="development", user_id="operator",
        )
    service.store.rebuild_index()
    profiles = []
    for policy in POLICIES:
        rows = []
        for original in suite["queries"]:
            query = evaluation_query(original)
            start = perf_counter()
            returned, error = [], None
            try:
                returned = service.search(query["query"], tenant_id="development", user_id="operator",
                                          top_k=3, min_score=.265, evidence_policy=policy)
            except Exception as exc:
                error = type(exc).__name__
            rows.append(score_request(query, returned, elapsed_ms=(perf_counter() - start) * 1000,
                                      error_type=error))
        profiles.append({"evidence_policy": policy, "summary": summarize_rows(rows), "rows": rows})
    return {
        "schema_version": 2, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "visible_development_check_not_blind_or_official_acceptance",
        "dataset": dataset, "method": dict(METHOD),
        "provider": provider_identity(service.store.embedding),
        "environment": {"system": platform.system(), "python": platform.python_version(),
                        "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random")},
        "source_sha256": snapshot, "source_unchanged_during_run": snapshot == file_hashes(root),
        "profiles": profiles, "competition_ready": False, "independent_blind": False,
        "limitations": [
            "Visible development requests, not production incidents or generalization evidence.",
            "Lexical coverage is not relation entailment or negation reasoning.",
            "v1 only abstains. v2 changes query focus and evidence selection; bundle scores are not direct similarities.",
            "The fixed .265 threshold gates direct seeds; a companion carries its seed's bundle relevance.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--challenge", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("refusing to overwrite development evidence")
    report = evaluate(challenge=args.challenge)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps([{"policy": row["evidence_policy"], **row["summary"]}
                      for row in report["profiles"]], ensure_ascii=False, indent=2))
    return 0 if report["source_unchanged_during_run"] and all(
        not row["summary"]["errors"] for row in report["profiles"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())

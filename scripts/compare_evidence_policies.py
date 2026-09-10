"""Recount same-run policy comparisons with strict quality and nonregression gates."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from os_agent_memory.complex_retrieval import COMPLETION_THRESHOLDS, SUITES
from os_agent_memory.embeddings import HashEmbedding
from os_agent_memory.focused_evidence import POLICY
from os_agent_memory.provider_config import provider_identity
from os_agent_memory.retrieval_evidence import POLICIES
from scripts.compare_retrieval_runs import validate_report
from scripts.verify_kylin_guest import file_hashes

REFERENCE = "similarity"
EXPERIMENT = "content_coverage_v1"
HIGHER_IS_BETTER = (
    "macro_recall_at_3", "precision_at_3", "mrr_at_3", "ndcg_at_3",
    "full_evidence_accuracy", "no_answer_accuracy", "scope_empty_correct",
)
LOWER_IS_BETTER = ("irrelevant_returned", "distractor_return_rate", "false_answers")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compare_rounds(before, after):
    """Keep per-request recall/success gates separate from aggregate ranking."""
    require([row["id"] for row in before["rows"]] == [row["id"] for row in after["rows"]],
            "unpaired requests")
    requests, metrics = [], []
    for old, new in zip(before["rows"], after["rows"]):
        reasons = []
        if old["passed"] and not new["passed"]:
            reasons.append("previously_correct_request_failed")
        if old["recall_at_3"] is not None and new["recall_at_3"] < old["recall_at_3"]:
            reasons.append("request_recall_decreased")
        if new["error_type"] is not None or new["invalid_ids"]:
            reasons.append("execution_or_scope_failure")
        if reasons:
            requests.append({"id": old["id"], "reasons": reasons})
    for name in (*HIGHER_IS_BETTER, *LOWER_IS_BETTER):
        old, new = before["summary"][name], after["summary"][name]
        if old is None or new is None:
            require(old is None and new is None, "metric denominator changed")
            continue
        regressed = new < old if name in HIGHER_IS_BETTER else new > old
        if regressed:
            metrics.append({"metric": name, "before": old, "after": new})
    return {"request_regressions": requests, "metric_regressions": metrics}


def compare_policies(report, *, root=ROOT, sizes=(1000, 10000), hard_fractions=(0.0, .75),
                     rounds=3, use_constraints=None, measured_snapshot=None):
    root = Path(root)
    identity = next(((name, path, digest) for name, (path, digest) in SUITES.items()
                     if path.as_posix() == report.get("dataset", {}).get("path")), None)
    require(identity is not None, "unknown frozen suite")
    name, path, digest = identity
    payload = (root / path).read_bytes()
    require(hashlib.sha256(payload).hexdigest() == digest, "frozen dataset bytes changed")
    suite = json.loads(payload)
    require(report.get("schema_version") == 2
            and report.get("scope") == "public_complex_retrieval_regression_not_official_acceptance",
            "policy comparison needs current request-level evidence")
    validate_report(report, suite)
    if use_constraints is None:
        use_constraints = name == "complex_constraints_v1"
    require(type(use_constraints) is bool and (name != "complex_retrieval_v1" or not use_constraints),
            "invalid explicit-constraint comparison")
    require(report["dataset"] == {
        "path": path.as_posix(), "sha256": digest, "documents": len(suite["documents"]),
        "distinct_requests": len(suite["queries"]),
        "kinds": dict(Counter(row["kind"] for row in suite["queries"])),
    }, "dataset denominator changed")
    method = {
        "boundary": "MemoryService.search: lock, query encoding, retrieval, reranking, serialization; no HTTP/Agent",
        "filler_fraction_denominator": "generated fillers only; fixed difficult documents always present",
        "percentile": "nearest_rank", "rounds": rounds, "query_order": "frozen file order, no query warmup",
        "repetition_is_independent_sample": False, "controlled_snapshot_bypasses_ingestion": True,
        "quality_thresholds": {"macro_recall_at_3": .85, "no_answer_accuracy": .85, "p95_ms": 500},
        "completion_thresholds": dict(COMPLETION_THRESHOLDS), "evidence_policies": list(POLICIES),
        "v2_score_boundary": "direct seed >= min_score; exact-subject companions carry seed bundle relevance",
        **({"constraint_modes": [use_constraints],
            "constraint_source": "explicit input terms; never generated from relevance labels"}
           if name == "complex_constraints_v1" else {}),
    }
    require(report["method"] == method, "measurement method, policies or repetitions changed")
    environment = report.get("environment", {})
    require(environment.get("python_hash_seed") == "0"
            and all(key in environment for key in ("system", "release", "machine", "python", "processor"))
            and type(environment.get("logical_cpu_count")) is int and environment["logical_cpu_count"] > 0
            and re.fullmatch(r"[0-9a-f]{64}", environment.get("host_fingerprint", "")),
            "missing environment identity or fixed tie-breaking seed")
    current = file_hashes(root)
    measured = current if measured_snapshot is None else measured_snapshot
    require(measured.get("lf_sha256") == current["lf_sha256"]
            and measured.get("excluded_generated_outputs") == current["excluded_generated_outputs"],
            "measured snapshot does not match current checkout")
    source = {key: value for key, value in measured["raw_sha256"].items()
              if key.startswith("src/") and key.endswith(".py")}
    require(report["source_sha256"] == source, "measured retrieval source changed")
    evaluator_paths = (path.as_posix(), "src/os_agent_memory/complex_retrieval.py",
                       "scripts/evaluate_complex_retrieval.py")
    require(report["evaluator_sha256"] == {key: measured["raw_sha256"][key] for key in evaluator_paths},
            "measured evaluator changed")
    expected = {(size, fraction, "hybrid", use_constraints, policy)
                for size in sizes for fraction in hard_fractions for policy in POLICIES}
    profiles = {(row["corpus"]["records"], row["corpus"]["requested_hard_fraction_of_fillers"],
                 row["mode"], row.get("required_terms_enabled", False), row["evidence_policy"]): row
                for row in report["profiles"]}
    require(bool(expected) and profiles.keys() == expected, "missing or unexpected comparison profile")
    require(all(row.get("provider") == provider_identity(HashEmbedding()) for row in profiles.values()),
            "policy provider or model configuration differs")
    require(all("groups" in repeat for row in profiles.values() for repeat in row["rounds"]),
            "missing stratified quality or latency")

    rows, request_regressions, metric_regressions, failures = [], [], [], []
    candidate_profiles = [row for key, row in profiles.items() if key[-1] == POLICY]
    for key in sorted({key[:4] for key in profiles}):
        original, experimental, candidate = (profiles[(*key, policy)] for policy in
                                              (REFERENCE, EXPERIMENT, POLICY))
        require(original["corpus"] == experimental["corpus"] == candidate["corpus"],
                "policies used different corpus snapshots")
        for first, control, second in zip(original["rounds"], experimental["rounds"], candidate["rounds"]):
            for old, abstained in zip(first["rows"], control["rows"]):
                require(not abstained["returned"] or (old["returned"], old["scores"])
                        == (abstained["returned"], abstained["scores"]), "legacy experiment changed ranking")
            identity = {"records": key[0], "hard_fraction": key[1], "mode": key[2],
                        "required_terms_enabled": key[3], "round": second["round"]}
            comparisons = {policy: compare_rounds(baseline, second)
                           for policy, baseline in ((REFERENCE, first), (EXPERIMENT, control))}
            for policy, differences in comparisons.items():
                request_regressions.extend({**identity, "reference_policy": policy, **item}
                                           for item in differences["request_regressions"])
            # The rejected experiment's empty results are not a production-quality
            # reference for precision. Its per-request successes remain protected.
            metric_regressions.extend({**identity, **item}
                                      for item in comparisons[REFERENCE]["metric_regressions"])
            failures.extend({**identity, "id": row["id"], "kind": row["kind"],
                             "expected": row["expected"], "returned": row["returned"],
                             "error_type": row["error_type"], "invalid_ids": row["invalid_ids"]}
                            for row in second["rows"] if not row["passed"])
            rows.append({
                **identity, "reference": first["summary"], "experiment": control["summary"],
                "candidate": second["summary"], "candidate_completion": second["completion"],
                "first_query_ms": {REFERENCE: first["first_query_ms"], EXPERIMENT: control["first_query_ms"],
                                   POLICY: second["first_query_ms"]},
                "comparisons": comparisons,
            })
    checks = {
        "source_unchanged_during_comparison": current == file_hashes(root),
        "full_evidence_and_abstention_100_percent": all(row["strict_quality_targets_met"]
                                                      for row in candidate_profiles),
        "previously_correct_requests_and_recall_preserved": not request_regressions,
        "ranking_and_distractors_nonregression_vs_similarity": not metric_regressions,
        "no_failed_requests_including_scope": not failures,
        "zero_errors_and_leaks": all(row["safety_passed"] for row in candidate_profiles),
        "p95_at_most_500ms_every_profile_and_round": all(row["latency_target_met"] for row in candidate_profiles),
    }
    return {
        "schema_version": 1, "scope": "same_source_public_regression_policy_nonregression_not_sdk_or_acceptance",
        "dataset": report["dataset"], "environment": environment,
        "measured_source_sha256": source, "evaluator_sha256": report["evaluator_sha256"],
        "checker_sha256": {key: current["raw_sha256"][key] for key in
                           ("scripts/compare_evidence_policies.py", "scripts/compare_retrieval_runs.py",
                            "scripts/verify_kylin_guest.py")},
        "reference_policy": REFERENCE, "experimental_control": EXPERIMENT, "candidate_policy": POLICY,
        "measurement_valid": True, "checks": checks, "optimization_gates_passed": all(checks.values()),
        "all_controls_meet_targets": report["all_targets_met"],
        "paired_request_count_per_reference": sum(row["candidate"]["requests"] for row in rows),
        "distinct_requests": len(suite["queries"]), "rows": rows,
        "request_regressions": request_regressions, "metric_regressions": metric_regressions,
        "candidate_failures": failures,
        "equivalent_output_speed_comparison": False, "competition_ready": False, "independent_blind": False,
        "interpretation": [
            "Recomputed all requests, scores, completion gates and summaries; controls retain their failures.",
            "Protect recall and previously correct requests against both controls.",
            "Compare aggregate ranking and distractor metrics against the former default similarity policy.",
            "Three repetitions and corpus sizes do not create additional independent requests.",
            "P95 must remain within 500ms; changed outputs do not establish equivalent-output acceleration.",
            "Public, visible-label HashEmbedding regression; no native SDK, blinded or competition acceptance claim.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", default="1000,10000")
    parser.add_argument("--hard-fractions", default="0,0.75")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--constraints", choices=("none", "enforce"))
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("refusing to overwrite a policy comparison")
    payload = args.input.read_bytes()
    result = compare_policies(
        json.loads(payload), sizes=tuple(int(value) for value in args.sizes.split(",")),
        hard_fractions=tuple(float(value) for value in args.hard_fractions.split(",")),
        rounds=args.rounds, use_constraints=None if args.constraints is None else args.constraints == "enforce",
    )
    result["input_sha256"] = hashlib.sha256(payload).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("checks", "optimization_gates_passed",
                                                  "paired_request_count_per_reference", "competition_ready")},
                     ensure_ascii=False, indent=2))
    return 0 if result["optimization_gates_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

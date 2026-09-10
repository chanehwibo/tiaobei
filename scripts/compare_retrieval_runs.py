"""Recount paired complex runs, preserving failures and measurement boundaries."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.complex_retrieval import (
    COMPLETION_THRESHOLDS, CONFIGURATION, FROZEN_SHA256, SUITE_PATH, SUITES, completion_summary,
    grouped_summaries, make_corpus, score_request, strict_quality_passed, summarize_rows, validate_suite, visible,
)
from os_agent_memory.focused_evidence import (
    POLICY as FOCUSED_EVIDENCE, bundle_supported, normalize_quantities, query_focus, subject_key,
    support_coverage, support_focus,
)
from os_agent_memory.memory_store import MemoryStore, _normalize_search_text
from os_agent_memory.retrieval_evidence import MIN_COVERAGE, POLICIES, content_coverage
from os_agent_memory.schemas import KnowledgeMemory


def validate_evidence_row(query, row, documents, policy, *, constrained=False, require_metadata=False):
    """Recompute declared support and attribution without trusting report flags."""
    metadata = row.get("evidence")
    if metadata is None:
        if require_metadata or policy == FOCUSED_EVIDENCE:
            raise ValueError("missing evidence attribution")
        return
    if not isinstance(metadata, list) or len(metadata) != len(row["returned"]):
        raise ValueError("evidence attribution length mismatch")
    if policy != FOCUSED_EVIDENCE:
        if any(item != {} for item in metadata):
            raise ValueError("legacy policy cannot claim propagated evidence")
        return
    if not row["returned"]:
        return
    fields = [tuple(_normalize_search_text(documents[key][field]).lower()
                    for field in ("title", "content")) for key in row["returned"]]
    text = normalize_quantities(query_focus(_normalize_search_text(query["query"]))).lower()
    constraints = MemoryStore._evidence_constraints(query.get("required_terms")) if constrained else []
    if not bundle_supported(text, fields, constraints=constraints):
        raise ValueError("returned set violates focused evidence support")
    coverage = round(support_coverage(support_focus(text), fields, constraints=constraints), 4)
    seed_id = row["returned"][0]
    subject = subject_key(fields[0][0])
    keys = {"policy", "direct_score", "origin", "seed_id", "coverage", "document_score", "passage_score"}
    for index, (item, score) in enumerate(zip(metadata, row["scores"])):
        if not isinstance(item, dict) or set(item) != keys:
            raise ValueError("invalid evidence attribution fields")
        numeric = [item[key] for key in ("direct_score", "document_score", "passage_score", "coverage")]
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in numeric):
            raise ValueError("invalid evidence attribution scores")
        if (item["policy"] != policy or item["seed_id"] != seed_id or item["coverage"] != coverage
                or item["direct_score"] != max(item["document_score"], item["passage_score"])
                or score != max(item["direct_score"], metadata[0]["direct_score"])
                or item["origin"] != ("direct" if index == 0 else "subject_companion")
                or (index == 0 and item["direct_score"] < CONFIGURATION["min_score"])
                or (index > 0 and (not subject or subject_key(fields[index][0]) != subject))):
            raise ValueError("evidence seed, companion, coverage or score attribution mismatch")


def validate_report(report, suite):
    """Never accept a summary that disagrees with the frozen query-level evidence."""
    identity = SUITES.get(suite.get("name"))
    version = report.get("schema_version")
    if (type(version) is not int or version not in (1, 2) or not report.get("source_unchanged_during_run")
            or report.get("competition_ready") is not False or report.get("independent_blind") is not False
            or identity is None or report["dataset"]["sha256"] != identity[1]
            or report["dataset"]["path"] != identity[0].as_posix()
            or report["dataset"]["distinct_requests"] != len(suite["queries"])
            or report["dataset"]["documents"] != len(suite["documents"])):
        raise ValueError("invalid report identity or readiness boundary")
    if not report["profiles"] or not report["source_sha256"] or not report["evaluator_sha256"]:
        raise ValueError("empty report evidence")
    if version == 2 and report["method"].get("completion_thresholds") != COMPLETION_THRESHOLDS:
        raise ValueError("completion thresholds changed")
    now = datetime.fromisoformat(report["generated_at_utc"])
    validate_suite(suite, now=now)
    seen = set()
    for profile in report["profiles"]:
        corpus = profile["corpus"]
        constrained = profile.get("required_terms_enabled", False)
        policy = profile.get("evidence_policy", "similarity")
        key = (corpus["records"], corpus["requested_hard_fraction_of_fillers"], profile["mode"], constrained, policy)
        if (policy not in POLICIES
                or profile.get("minimum_evidence_coverage") != (MIN_COVERAGE if policy != "similarity" else None)
                or policy not in report["method"].get("evidence_policies", ["similarity"])):
            raise ValueError("evidence policy or coverage threshold is inconsistent")
        if key in seen or profile["configuration"] != CONFIGURATION or profile["mode"] not in {"hybrid", "lexical", "semantic"}:
            raise ValueError("duplicate profile or changed configuration")
        if type(constrained) is not bool or (constrained and not all("required_terms" in q for q in suite["queries"])):
            raise ValueError("constraint policy does not match frozen inputs")
        seen.add(key)
        documents, expected_corpus = make_corpus(suite, *key[:2])
        if corpus != expected_corpus:
            raise ValueError("corpus does not match deterministic generation")
        by_id = {row["id"]: row for row in documents}
        repeats = profile["rounds"]
        if len(repeats) != report["method"]["rounds"] or not repeats:
            raise ValueError("missing repetition")
        for index, repeat in enumerate(repeats):
            if repeat["round"] != index + 1 or len(repeat["rows"]) != len(suite["queries"]):
                raise ValueError("missing or reordered requests")
            for row, query in zip(repeat["rows"], suite["queries"]):
                if any(row[key] != query[key] for key in ("id", "query", "expected", "category", "kind", "scenario")):
                    raise ValueError("query or label does not match frozen input")
                if (type(row["elapsed_ms"]) not in (float, int) or not math.isfinite(row["elapsed_ms"])
                        or row["elapsed_ms"] < 0 or len(row["returned"]) > 3
                        or len(row["returned"]) != len(row["scores"])
                        or any(type(score) not in (float, int) or not math.isfinite(score) for score in row["scores"])):
                    raise ValueError("invalid timing or returned scores")
                invalid = [key for key in row["returned"] if key not in by_id or not visible(by_id[key], query, now)]
                if constrained:
                    constraints = MemoryStore._evidence_constraints(query["required_terms"])
                    for identifier in row["returned"]:
                        document = by_id.get(identifier, {})
                        evidence = KnowledgeMemory(
                            id=identifier, title=document.get("title", ""), content=document.get("content", ""),
                            tags=[], source_ids=[], version=1, created_at="", updated_at="",
                        )
                        if not MemoryStore._supports_constraints(evidence, constraints):
                            raise ValueError("returned record violates explicit evidence constraints")
                if policy == "content_coverage_v1" and row["returned"] and not invalid:
                    fields = [tuple(_normalize_search_text(by_id[key][field]).lower()
                                    for field in ("title", "content")) for key in row["returned"]]
                    constraints = MemoryStore._evidence_constraints(query.get("required_terms")) if constrained else []
                    if content_coverage(_normalize_search_text(query["query"]).lower(), fields,
                                        constraints=constraints) < MIN_COVERAGE:
                        raise ValueError("returned set violates declared content coverage policy")
                if not invalid:
                    validate_evidence_row(query, row, by_id, policy, constrained=constrained,
                                          require_metadata=version == 2)
                metadata = row.get("evidence", [{} for _ in row["returned"]])
                recounted = score_request(
                    query, [{"memory_id": key, "score": score, "evidence": info}
                            for key, score, info in zip(row["returned"], row["scores"], metadata)],
                    elapsed_ms=row["elapsed_ms"], invalid_ids=invalid, error_type=row["error_type"],
                    include_evidence="evidence" in row,
                )
                if recounted != row:
                    raise ValueError("request scores or safety flags disagree with returned evidence")
            categories = {category: summarize_rows([row for row in repeat["rows"] if row["category"] == category])
                          for category in sorted({row["category"] for row in repeat["rows"]})}
            if repeat["summary"] != summarize_rows(repeat["rows"]) or repeat["categories"] != categories:
                raise ValueError("summary or category counts disagree with requests")
            if "groups" in repeat and repeat["groups"] != grouped_summaries(repeat["rows"]):
                raise ValueError("group counts or latency disagree with requests")
            if repeat["first_query_ms"] != repeat["rows"][0]["elapsed_ms"]:
                raise ValueError("first query timing mismatch")
            if version == 2 and repeat.get("completion") != completion_summary(repeat["rows"]):
                raise ValueError("completion counts or gates disagree with requests")
        summaries = [repeat["summary"] for repeat in repeats]
        quality = all(row["macro_recall_at_3"] >= .85 and row["no_answer_accuracy"] >= .85 for row in summaries)
        safety = all(row["leaked_records"] == 0 and row["errors"] == 0 for row in summaries)
        latency = all(row["latency_valid"] and row["p95_ms"] <= 500 for row in summaries)
        flags = {"quality_targets_met": quality, "safety_passed": safety,
                 "latency_target_met": latency, "all_targets_met": quality and safety and latency}
        if version == 2:
            strict = all(strict_quality_passed(repeat["completion"]) for repeat in repeats)
            flags.update(strict_quality_targets_met=strict, all_targets_met=quality and strict and safety and latency)
        if any(profile[key] is not value for key, value in flags.items()):
            raise ValueError("profile gate disagrees with measurements")
    keys = ("quality_targets_met", "safety_passed", "latency_target_met", "all_targets_met")
    for key in (*keys, *(("strict_quality_targets_met",) if version == 2 else ())):
        if report[key] is not all(profile[key] for profile in report["profiles"]):
            raise ValueError("run gate disagrees with profiles")


def compare_reports(before, after, suite):
    if suite.get("name") != "complex_retrieval_v1":
        raise ValueError("historical speed comparator only accepts the original unconstrained suite")
    validate_report(before, suite)
    validate_report(after, suite)
    if any(profile.get("evidence_policy", "similarity") != "similarity"
           for report in (before, after) for profile in report["profiles"]):
        raise ValueError("changed evidence policies are not an equivalent-output speed comparison")
    for key in ("dataset", "environment", "evaluator_sha256", "method"):
        if before[key] != after[key]:
            raise ValueError("cannot pair runs with different " + key)
    before_source, after_source = before["source_sha256"], after["source_sha256"]
    changed = sorted(key for key in before_source.keys() | after_source.keys()
                     if before_source.get(key) != after_source.get(key))
    if changed != ["src/os_agent_memory/memory_store.py"]:
        raise ValueError("paired optimization must change only memory_store.py in the measured source")
    if before["environment"]["python_hash_seed"] == "random":
        raise ValueError("paired candidate ties require a fixed PYTHONHASHSEED")
    def profiles(report):
        return {(row["corpus"]["records"], row["corpus"]["requested_hard_fraction_of_fillers"], row["mode"]): row
                for row in report["profiles"]}
    left, right = profiles(before), profiles(after)
    if left.keys() != right.keys():
        raise ValueError("profile sets differ")
    rows, regressions, changed_outputs = [], [], []
    for key in sorted(left):
        a, b = left[key], right[key]
        if a["corpus"] != b["corpus"] or a["provider"] != b["provider"]:
            raise ValueError("corpus or provider differs")
        for first, second in zip(a["rounds"], b["rounds"]):
            for old, new in zip(first["rows"], second["rows"]):
                if (old["returned"], old["scores"]) != (new["returned"], new["scores"]):
                    changed_outputs.append({"profile": list(key), "round": first["round"], "id": old["id"]})
                if ((old["passed"] and not new["passed"])
                        or (old["recall_at_3"] is not None and new["recall_at_3"] < old["recall_at_3"])
                        or new["error_type"] or new["invalid_ids"]):
                    regressions.append({"profile": list(key), "round": first["round"], "id": old["id"]})
            old_p95, new_p95 = first["summary"]["p95_ms"], second["summary"]["p95_ms"]
            rows.append({
                "records": key[0], "hard_fraction": key[1], "mode": key[2], "round": first["round"],
                "before_p95_ms": old_p95, "after_p95_ms": new_p95,
                "p95_reduction_percent": (old_p95 - new_p95) / old_p95 * 100 if old_p95 else None,
                "before_first_query_ms": first["first_query_ms"], "after_first_query_ms": second["first_query_ms"],
                "before_recall_at_3": first["summary"]["macro_recall_at_3"],
                "after_recall_at_3": second["summary"]["macro_recall_at_3"],
                "before_no_answer_accuracy": first["summary"]["no_answer_accuracy"],
                "after_no_answer_accuracy": second["summary"]["no_answer_accuracy"],
            })
    valid = before["safety_passed"] and after["safety_passed"]
    improved = all(row["after_p95_ms"] < row["before_p95_ms"] for row in rows)
    return {
        "schema_version": 1, "scope": "paired_development_machine_hash_retrieval_not_native_or_official",
        "dataset_sha256": FROZEN_SHA256, "changed_source_files": changed,
        "measurement_valid": valid, "quality_nonregression": not regressions,
        "identical_ranked_results_and_scores": not changed_outputs,
        "p95_improved_in_every_profile_and_round": improved,
        "performance_improvement_supported": valid and not regressions and improved,
        "complex_quality_targets_met": after["quality_targets_met"],
        "competition_ready": False, "rows": rows,
        "quality_regressions": regressions, "changed_outputs": changed_outputs,
        "interpretation": "Latency improvement does not remove complex no-answer failures or establish native SDK acceptance.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("refusing to overwrite a paired report")
    payloads = [path.read_bytes() for path in (args.before, args.after)]
    suite = json.loads((ROOT / SUITE_PATH).read_bytes())
    result = compare_reports(*(json.loads(payload) for payload in payloads), suite)
    result["input_sha256"] = dict(zip(("before", "after"), (hashlib.sha256(value).hexdigest() for value in payloads)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["measurement_valid"] and result["quality_nonregression"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

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
    CONFIGURATION, FROZEN_SHA256, SUITE_PATH, make_corpus, score_request, summarize_rows, validate_suite, visible,
)


def validate_report(report, suite):
    """Never accept a summary that disagrees with the frozen query-level evidence."""
    if (report.get("schema_version") != 1 or not report.get("source_unchanged_during_run")
            or report.get("competition_ready") is not False or report.get("independent_blind") is not False
            or report["dataset"]["sha256"] != FROZEN_SHA256 or report["dataset"]["distinct_requests"] != 120):
        raise ValueError("invalid report identity or readiness boundary")
    if not report["profiles"] or not report["source_sha256"] or not report["evaluator_sha256"]:
        raise ValueError("empty report evidence")
    now = datetime.fromisoformat(report["generated_at_utc"])
    validate_suite(suite, now=now)
    seen = set()
    for profile in report["profiles"]:
        corpus = profile["corpus"]
        key = (corpus["records"], corpus["requested_hard_fraction_of_fillers"], profile["mode"])
        if key in seen or profile["configuration"] != CONFIGURATION or profile["mode"] not in {"hybrid", "lexical", "semantic"}:
            raise ValueError("duplicate profile or changed configuration")
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
                recounted = score_request(
                    query, [{"memory_id": key, "score": score} for key, score in zip(row["returned"], row["scores"])],
                    elapsed_ms=row["elapsed_ms"], invalid_ids=invalid, error_type=row["error_type"],
                )
                if recounted != row:
                    raise ValueError("request scores or safety flags disagree with returned evidence")
            categories = {category: summarize_rows([row for row in repeat["rows"] if row["category"] == category])
                          for category in sorted({row["category"] for row in repeat["rows"]})}
            if repeat["summary"] != summarize_rows(repeat["rows"]) or repeat["categories"] != categories:
                raise ValueError("summary or category counts disagree with requests")
            if repeat["first_query_ms"] != repeat["rows"][0]["elapsed_ms"]:
                raise ValueError("first query timing mismatch")
        summaries = [repeat["summary"] for repeat in repeats]
        quality = all(row["macro_recall_at_3"] >= .85 and row["no_answer_accuracy"] >= .85 for row in summaries)
        safety = all(row["leaked_records"] == 0 and row["errors"] == 0 for row in summaries)
        latency = all(row["latency_valid"] and row["p95_ms"] <= 500 for row in summaries)
        flags = {"quality_targets_met": quality, "safety_passed": safety,
                 "latency_target_met": latency, "all_targets_met": quality and safety and latency}
        if any(profile[key] is not value for key, value in flags.items()):
            raise ValueError("profile gate disagrees with measurements")
    for key in ("quality_targets_met", "safety_passed", "latency_target_met", "all_targets_met"):
        if report[key] is not all(profile[key] for profile in report["profiles"]):
            raise ValueError("run gate disagrees with profiles")


def compare_reports(before, after, suite):
    validate_report(before, suite)
    validate_report(after, suite)
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

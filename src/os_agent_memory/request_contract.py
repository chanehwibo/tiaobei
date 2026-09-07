"""Release gates for the frozen public regression, not official certification."""
from __future__ import annotations

import math

from .benchmark import _percentile
from .evaluation import precision_recall_f1
from .official_contract import assess_official_metrics


FROZEN_DATASET_SHA256 = "51ce224491a4252b69d282138785b28f4a9b8a64212b512f587dd48bfbcd1a98"
FROZEN_COUNTS = {
    "preference_accuracy": 68,
    "knowledge_recall": 60,
    "conflict_accuracy": 60,
    "retrieval_p95_ms": 80,
    "sensitive_f1": 50,
}
SAFETY_CHECKS = (
    "durable_preferences", "knowledge_ingestion", "no_scope_leaks",
    "no_answer_85", "no_redaction_leaks",
)
FROZEN_PROVIDER = {
    "implementation": "os_agent_memory.embeddings.HashEmbedding",
    "dimensions": 256,
    "ngram": 2,
}


def assess_request_targets(report):
    rubric = assess_official_metrics(report.get("metrics", {}), report.get("observation_counts", {}))
    checks = {
        "five_numeric_targets": rubric["all_targets_met"],
        "required_safety_checks": (
            all(report.get("safety_checks", {}).get(key) is True for key in SAFETY_CHECKS)
            and all(value is True for value in report.get("safety_checks", {}).values())
        ),
    }
    return {"passed": all(checks.values()), "checks": checks, "rubric": rubric}


def assess_frozen_requests(report):
    target = assess_request_targets(report)
    counts = report.get("observation_counts", {})
    retrieval = report.get("retrieval", {})
    checks = {
        **target["checks"],
        "frozen_dataset": report.get("dataset", {}).get("sha256") == FROZEN_DATASET_SHA256,
        "frozen_request_counts": (
            set(counts) == set(FROZEN_COUNTS)
            and all(type(counts.get(key)) is int and counts[key] == count for key, count in FROZEN_COUNTS.items())
        ),
        "frozen_retrieval_configuration": (
            retrieval.get("records") == 10000 and retrieval.get("top_k") == 3
            and retrieval.get("threshold") == 0.265 and retrieval.get("provider") == FROZEN_PROVIDER
        ),
        "honest_evidence_scope": (
            report.get("independent_blind") is False and report.get("official_validation_ready") is False
            and report.get("all_targets_met") is True
        ),
    }
    try:
        preference, conflict, sensitive = (report[key] for key in ("preference", "conflict", "sensitive"))
        groups = (preference, retrieval, conflict, sensitive)
        checks["distinct_request_rows"] = all(
            len(group["rows"]) == group["requests"]
            and len({row["id"] for row in group["rows"]}) == group["requests"] for group in groups
        )
        checks["denominators_match_rows"] = (
            preference["requests"] == counts["preference_accuracy"]
            and conflict["requests"] == counts["conflict_accuracy"]
            and sensitive["requests"] == counts["sensitive_f1"]
            and retrieval["requests"] == counts["retrieval_p95_ms"]
            and sum(bool(row["expected"]) for row in retrieval["rows"]) == counts["knowledge_recall"]
            and retrieval["positive_requests"] == counts["knowledge_recall"]
            and retrieval["no_answer_requests"] == 12 and retrieval["scope_requests"] == 8
        )
        metrics = report["metrics"]
        checks["summary_matches_details"] = (
            metrics["preference_accuracy"] == preference["accuracy"]
            == preference["correct"] / preference["requests"]
            and metrics["conflict_accuracy"] == conflict["accuracy"] == conflict["correct"] / conflict["requests"]
            and metrics["knowledge_recall"] == retrieval["positive_recall_at_3"]
            and metrics["retrieval_p95_ms"] == retrieval["p95_ms"]
            and metrics["sensitive_f1"] == sensitive["f1"]
            and preference["durable_checks_passed"] is True and retrieval["ingestion"]["passed"] is True
            and retrieval["scope_leaks"] == 0 and retrieval["no_answer_accuracy"] >= 0.85
            and sensitive["redaction_leaks"] == 0
        )
        positives = [row for row in retrieval["rows"] if row["expected"]]
        negatives = [row for row in retrieval["rows"] if not row["expected"] and row["category"] != "scope"]
        scoped = [row for row in retrieval["rows"] if row["category"] == "scope"]
        timings = [row["elapsed_ms"] for row in retrieval["rows"]]
        entity_counts = {key: sum(row[key] for row in sensitive["rows"]) for key in ("tp", "fp", "fn")}
        checks["aggregates_match_request_rows"] = (
            all(type(row["passed"]) is bool for group in groups for row in group["rows"])
            and preference["correct"] == sum(row["passed"] for row in preference["rows"])
            and conflict["correct"] == sum(row["passed"] for row in conflict["rows"])
            and preference["durable_checks_passed"] == all(
                row.get("durable_passed", True) is True for row in preference["rows"])
            and all(len(row["returned"]) <= 3 and len(row["returned"]) == len(set(row["returned"]))
                    for row in retrieval["rows"])
            and all(row["recall_at_3"] == len(set(row["expected"]) & set(row["returned"])) / len(set(row["expected"]))
                    for row in positives)
            and retrieval["positive_recall_at_3"] == sum(row["recall_at_3"] for row in positives) / len(positives)
            and len(negatives) == retrieval["no_answer_requests"]
            and retrieval["no_answer_accuracy"] == sum(not row["returned"] for row in negatives) / len(negatives)
            and len(scoped) == retrieval["scope_requests"]
            and retrieval["scope_leaks"] == sum(bool(row["returned"]) for row in scoped)
            and all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in timings)
            and retrieval["p95_ms"] == _percentile(timings, .95)
            and all(type(row[key]) is int and row[key] >= 0 for row in sensitive["rows"] for key in entity_counts)
            and all(sensitive[key] == value for key, value in entity_counts.items())
            and sensitive["f1"] == precision_recall_f1(*(entity_counts[key] for key in ("tp", "fp", "fn")))["f1"]
            and sensitive["redaction_leaks"] == sum(row["redaction_leak"] for row in sensitive["rows"])
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        checks["valid_request_details"] = False
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "rubric": target["rubric"],
        "scope": "frozen_public_synthetic_regression_not_independent_blind_or_official_certification",
    }

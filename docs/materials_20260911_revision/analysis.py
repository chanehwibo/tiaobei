"""Derived document analysis, never a new performance run."""
from __future__ import annotations

import math

from docs.materials_20260911.evidence import BASE, ROOT, load_json, require, select_profile, sha256


def wilson(successes, total, z=1.959963984540054):
    require(type(successes) is int and type(total) is int
            and 0 <= successes <= total and total > 0, "invalid binomial counts")
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def worked_example():
    expected, returned = {"g1", "g2"}, ["g1", "d1", "g2"]
    hits = expected.intersection(returned)
    dcg = sum(1 / math.log2(i + 2) for i, value in enumerate(returned) if value in expected)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(3, len(expected))))
    return {
        "scope": "illustrative_metric_example_not_an_experiment",
        "expected": sorted(expected), "returned": returned,
        "recall_at_3": len(hits) / len(expected), "full_evidence": hits == expected,
        "precision_at_3": len(hits) / 3, "mrr_at_3": 1.0,
        "dcg": dcg, "ideal_dcg": ideal, "ndcg_at_3": dcg / ideal,
        "distractor_return_rate": (len(returned) - len(hits)) / len(returned),
    }


def derive_analysis(provenance):
    relative = (BASE / "complex-policies.json").as_posix()
    path = ROOT / relative
    expected = provenance.get("input_raw_sha256", {}).get(relative)
    require(expected is not None and sha256(path) == expected,
            "analysis input does not match validated provenance")
    report = load_json(path)
    require(sha256(path) == expected, "analysis input changed during reading")
    names = ("similarity", "content_coverage_v1", "focused_evidence_v2")
    profiles = {name: select_profile(report, policy=name) for name in names}
    rows = {}
    for name, profile in profiles.items():
        first = profile["rounds"][0]
        s = first["summary"]
        rows[name] = {
            key: s[key] for key in (
                "positive_requests", "full_evidence_correct", "no_answer_requests",
                "no_answer_correct", "macro_recall_at_3", "precision_at_3",
                "mrr_at_3", "ndcg_at_3", "irrelevant_returned",
                "positive_results_returned", "distractor_return_rate", "p95_ms",
            )
        }
        rows[name]["multi_document_correct"] = first["completion"]["multi_document_correct"]
        rows[name]["p95_rounds_ms"] = [r["summary"]["p95_ms"] for r in profile["rounds"]]
    old, experiment, new = (rows[name] for name in names)
    require((old["full_evidence_correct"], old["no_answer_correct"]) == (68, 1)
            and (experiment["full_evidence_correct"], experiment["no_answer_correct"]) == (59, 22)
            and (new["full_evidence_correct"], new["no_answer_correct"]) == (72, 24),
            "revision prose no longer matches policy counts")
    return {
        "scope": "recomputed_frozen_results_and_illustrative_statistics_not_new_measurements",
        "input_raw_sha256": provenance["input_raw_sha256"],
        "profile": {"records": 10000, "hard_fraction_of_fillers": .75,
                    "round_for_quality": 1, "distinct_requests": 120,
                    "provider": "HashEmbedding", "top_k": 3, "min_score": .265},
        "policies": rows,
        "delta_vs_similarity": {
            "full_evidence_requests": new["full_evidence_correct"] - old["full_evidence_correct"],
            "correct_no_answer_requests": new["no_answer_correct"] - old["no_answer_correct"],
            "recall_percentage_points": 100 * (new["macro_recall_at_3"] - old["macro_recall_at_3"]),
            "precision_percentage_points": 100 * (new["precision_at_3"] - old["precision_at_3"]),
            "distractor_rate_percentage_points":
                100 * (new["distractor_return_rate"] - old["distractor_return_rate"]),
            "p95_first_round_ms": new["p95_ms"] - old["p95_ms"],
            "p95_first_round_relative_increase": new["p95_ms"] / old["p95_ms"] - 1,
        },
        "wilson_95_illustration": [
            {"successes": n, "total": n, "lower": wilson(n, n)[0], "upper": wilson(n, n)[1]}
            for n in (72, 24, 12, 6)
        ],
        "wilson_assumptions_met": False,
        "wilson_interpretation": "Independent Bernoulli illustration only; visible clustered regression is not a population sample.",
        "worked_example": worked_example(),
        "new_performance_run": False, "independent_blind": False,
        "external_benchmark_executed": False, "competition_ready": False,
    }

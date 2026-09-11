"""Read and revalidate existing measurements without changing runtime evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from scripts.compare_evidence_policies import compare_policies
from scripts.generate_review_materials import (
    validate_development_evidence, validate_windows_evidence,
)
from scripts.summarize_sdk_risk import summarize_sdk_risk
from scripts.verify_kylin_guest import file_hashes

BASE = Path("artifacts/verification/feedback/focused-20260911")
DATA_HASHES = {
    "data/eval/request_regression_v1.json":
        "51ce224491a4252b69d282138785b28f4a9b8a64212b512f587dd48bfbcd1a98",
    "data/eval/complex_retrieval_v1.json":
        "04b9a5266535e40a4542ae4647a4bba51aabf8edc32bd3a169713a4c4c1f2212",
    "data/eval/complex_constraints_v1.json":
        "9f03254a21bd93d24e217f470524f55569776ce46a263fc4e53ddb48d44cb5fc",
}
POLICY = "focused_evidence_v2"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lf_sha256(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def load_json(path):
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique_object)


def select_profile(report, size=10000, hard=.75, policy=POLICY):
    matches = [row for row in report["profiles"]
               if row["corpus"]["records"] == size
               and row["corpus"]["requested_hard_fraction_of_fillers"] == hard
               and row["evidence_policy"] == policy]
    require(len(matches) == 1, "missing or ambiguous measured profile")
    return matches[0]


def pct(value):
    return f"{value * 100:.2f}%"


def validate_claims(windows, requests, reports, development, service, sdk):
    """Guard prose numbers as well as generated tables against evidence drift."""
    require(windows["unit_tests"]["tests_run"] == 392 and len(windows["checks"]) == 17,
            "update prose: engineering counts changed")
    require(re.search(r"OK \(skipped=1\)", windows["unit_tests"]["output_tail"]),
            "update prose: skipped tests changed")
    require(requests["observation_counts"] == {
        "preference_accuracy": 68, "knowledge_recall": 60, "conflict_accuracy": 60,
        "retrieval_p95_ms": 80, "sensitive_f1": 50,
    }, "update prose: frozen denominators changed")
    require(all(value == 1.0 for key, value in requests["metrics"].items()
                if key != "retrieval_p95_ms")
            and f'{requests["metrics"]["retrieval_p95_ms"]:.3f}' == "48.145",
            "update prose: frozen measurements changed")
    expected_group_p95 = (
        ("64.735", "87.846", "4.730"),
        ("17.475", "15.088", "5.235"),
        ("18.722", "14.546", "5.310"),
    )
    for i, report in enumerate(reports):
        expected = (72, 12, 24, 24) if i == 0 else (24, 6, 12, 12)
        require(report["dataset"]["distinct_requests"] == (120 if i == 0 else 48)
                and report["dataset"]["documents"] == (132 if i == 0 else 78),
                "update prose: complex data changed")
        for profile in report["profiles"]:
            if profile["evidence_policy"] != POLICY:
                continue
            require(profile["all_targets_met"] is True, "candidate failed a measured gate")
            for repeat in profile["rounds"]:
                summary, completion = repeat["summary"], repeat["completion"]
                actual = (summary["full_evidence_correct"], completion["multi_document_correct"],
                          summary["no_answer_correct"], summary["scope_empty_correct"])
                require(actual == expected and summary["errors"] == summary["leaked_records"] == 0,
                        "update prose: complex success counts changed")
                if i:
                    for category in ("absent_version", "unsupported_relation"):
                        require(repeat["categories"][category]["no_answer_correct"] == 6,
                                "update prose: constraint negative subgroup changed")
        repeat = select_profile(report)["rounds"][0]
        values = tuple(f'{repeat["groups"]["kind"][kind]["p95_ms"]:.3f}'
                       for kind in ("positive", "no_answer", "scope"))
        require(values == expected_group_p95[i], "update prose: stratified P95 changed")
        s = repeat["summary"]
        require((s["irrelevant_returned"], s["positive_results_returned"])
                == ((39, 123) if i == 0 else (9, 39)),
                "update prose: distractor counts changed")
    control = select_profile(reports[0], policy="similarity")["rounds"][0]["summary"]
    require((control["irrelevant_returned"], control["positive_results_returned"]) == (110, 190),
            "update prose: legacy distractors changed")
    for size in (1000, 10000):
        s = select_profile(reports[0], size, 0)["rounds"][0]["summary"]
        require((s["irrelevant_returned"], s["positive_results_returned"]) == (40, 124),
                "update prose: fixed-difficulty distractors changed")
    for i, report in enumerate(development):
        s = next(row["summary"] for row in report["profiles"] if row["evidence_policy"] == POLICY)
        require((s["full_evidence_correct"], s["no_answer_correct"]) == ((10, 10) if i == 0 else (6, 4))
                and s["errors"] == 0
                and f'{s["p95_ms"]:.3f}' == ("1.685" if i == 0 else "4.330"),
                "update prose: development results changed")
    large = service["results"][-1]
    require(large["records"] == 1000 and large["mixed_query_p95_ms"] == 9.882
            and large["http_query_p99_ms"] == 18.543 and large["sqlite_bytes"] == 5279744
            and large["process_resources"]["rss_after_bytes"] == 237113344
            and large["process_resources"]["lifetime_peak_rss_bytes"] == 701325312,
            "update prose: service resources changed")
    old = windows["official_diagnostics"]["metrics"]
    require(round(old["preference_accuracy"] * 100, 2) == 46.15
            and round(old["knowledge_recall"] * 100, 2) == 91.67
            and old["conflict_accuracy"] == 1.0,
            "update prose: adverse historical diagnostic changed")
    require(sdk["latency_status"] == "待复测风险项" and sdk["native_p95_ms"] is None
            and sdk["native_latency_passed"] is False and sdk["observations"] == 1
            and sdk["dimensions"] == 768 and f'{sdk["single_probe_ms"]:,.3f}' == "13,390.615",
            "update prose: native SDK risk changed")


def load_evidence(root=ROOT):
    root = Path(root).resolve()
    inputs = {}

    def read(relative):
        path = (root / relative).resolve()
        require(path.is_relative_to(root) and path.is_file(), "missing or unsafe evidence path")
        inputs[path.relative_to(root).as_posix()] = sha256(path)
        return load_json(path)

    current = file_hashes(root)
    for relative, expected in DATA_HASHES.items():
        read(relative)
        require(inputs[relative] == expected, "frozen data bytes changed")
    windows = read(BASE / "windows-final/final_verification.json")
    requests = read(BASE / "windows-final/requests.json")
    service = read(BASE / "windows-final/service_workload.json")
    frozen_gate = validate_windows_evidence(current, windows, requests, service)
    reports, comparison_results = [], []
    for report_name, comparison_name, constraints in (
        ("complex-policies.json", "complex-policy-comparison.json", False),
        ("constraints-policies-enforce.json", "constraints-comparison-enforce.json", True),
        ("constraints-policies-none.json", "constraints-comparison-none.json", False),
    ):
        report = read(BASE / report_name)
        result = compare_policies(report, root=root, use_constraints=constraints,
                                  measured_snapshot=windows["file_hashes"])
        result["input_sha256"] = inputs[(BASE / report_name).as_posix()]
        saved = read(BASE / comparison_name)
        require(result == saved, "saved policy comparison disagrees with recomputed evidence")
        require(result["optimization_gates_passed"] is True and len(result["checks"]) == 7,
                "a measured policy nonregression gate failed")
        require(result["all_controls_meet_targets"] is False,
                "legacy failures must remain visible")
        reports.append(report)
        comparison_results.append({
            "input": report_name, "comparison": comparison_name, "checks": result["checks"],
            "distinct_requests": result["distinct_requests"],
            "optimization_gates_passed": result["optimization_gates_passed"],
            "all_controls_meet_targets": result["all_controls_meet_targets"],
        })
    development = []
    for name, challenge in (("development-final.json", False),
                            ("development-challenge-final.json", True)):
        report = read(BASE / name)
        validate_development_evidence(root, current, report, challenge=challenge)
        read(report["dataset"]["path"])
        development.append(report)
    sdk = read("artifacts/verification/feedback/sdk_risk.json")
    read(sdk["source"])
    require(sdk == summarize_sdk_risk(root), "SDK summary differs from the original probe")
    validate_claims(windows, requests, reports, development, service, sdk)

    metrics = requests["metrics"]
    counts = requests["observation_counts"]
    names = (
        ("preference_accuracy", "偏好准确率", "≥85%"),
        ("knowledge_recall", "知识 Recall@3", "≥85%"),
        ("conflict_accuracy", "冲突正确率", "≥88%"),
        ("retrieval_p95_ms", "检索 P95", "≤500ms"),
        ("sensitive_f1", "敏感实体微 F1", "≥90%"),
    )
    e = {
        "tests": windows["unit_tests"]["tests_run"], "skipped": 1, "checks": len(windows["checks"]),
        "frozen_p95": metrics["retrieval_p95_ms"],
        "frozen_rows": [[name, f"{metrics[key]:.3f}ms" if key.endswith("_ms") else pct(metrics[key]),
                         str(counts[key]), target] for key, name, target in names],
        "complex_rows": [], "ranking_rows": [], "latency_rows": [], "service_rows": [],
        "data_hashes": dict(zip(("request", "complex", "constraints"), DATA_HASHES.values())),
    }
    for name, report in zip(("原120 / 无约束", "约束48 / 开启", "约束48 / 关闭"), reports):
        p = select_profile(report)
        s, c = p["rounds"][0]["summary"], p["rounds"][0]["completion"]
        e["complex_rows"].append([
            name, f'{s["full_evidence_correct"]}/{s["positive_requests"]}',
            f'{c["multi_document_correct"]}/{c["multi_document_requests"]}',
            f'{s["no_answer_correct"]}/{s["no_answer_requests"]}',
            f'{s["scope_empty_correct"]}/{s["scope_requests"]}',
        ])
        for size in (1000, 10000):
            for hard in (0, .75):
                old = select_profile(report, size, hard, "similarity")
                new = select_profile(report, size, hard)
                e["latency_rows"].append([
                    name, f"{size:,} / {hard:.0%}",
                    " / ".join(f'{r["summary"]["p95_ms"]:.3f}' for r in old["rounds"]),
                    " / ".join(f'{r["summary"]["p95_ms"]:.3f}' for r in new["rounds"]),
                ])
    for name, report, policy in (
        ("原120 / 旧默认", reports[0], "similarity"),
        ("原120 / 新默认", reports[0], POLICY),
        ("约束48 / 开启", reports[1], POLICY),
        ("约束48 / 关闭", reports[2], POLICY),
    ):
        s = select_profile(report, policy=policy)["rounds"][0]["summary"]
        e["ranking_rows"].append([
            name, pct(s["macro_recall_at_3"]), pct(s["precision_at_3"]),
            f'{s["mrr_at_3"]:.4f}', f'{s["ndcg_at_3"]:.4f}',
            f'{s["irrelevant_returned"]}/{s["positive_results_returned"]}\n'
            f'{pct(s["distractor_return_rate"])}',
        ])
    for field, name, boundary in (
        ("service_ingest_ms", "整批接入 ms", "MemoryService.ingest"),
        ("single_add_ms", "单条增量 ms", "接入、状态与持久化"),
        ("restart_load_ms", "重启加载 ms", "恢复同一SQLite"),
        ("mixed_query_p50_ms", "服务查询 P50 ms", "服务调用"),
        ("mixed_query_p95_ms", "服务查询 P95 ms", "服务调用"),
        ("mixed_query_p99_ms", "服务查询 P99 ms", "服务调用"),
        ("http_query_p99_ms", "HTTP 查询 P99 ms", "HTTP往返，非服务P95"),
    ):
        e["service_rows"].append([
            name, *(f"{row[field]:.3f}" for row in service["results"]), boundary,
        ])
    require(current == file_hashes(root), "runtime source changed during document evidence validation")
    provenance = {
        "scope": "anonymous_documents_from_existing_windows_public_regression",
        "measured_at_utc": windows["generated_at_utc"],
        "runtime_file_count": len(current["lf_sha256"]),
        "runtime_lf_sha256": current["lf_sha256"],
        "excluded_generated_outputs": current["excluded_generated_outputs"],
        "input_raw_sha256": inputs,
        "checks": {
            "current_source_matches_measured_windows": True,
            "frozen_requests_recounted": frozen_gate["passed"],
            "three_policy_matrices_recounted": True,
            "development_requests_recounted": True,
            "sdk_risk_matches_original_probe": True,
            "runtime_source_unchanged": True,
        },
        "comparisons": comparison_results,
        "native_latency_passed": False, "current_v11_verified": False,
        "independent_blind": False, "competition_ready": False,
        "new_performance_run": False, "packaged": False, "uploaded": False,
    }
    return e, provenance

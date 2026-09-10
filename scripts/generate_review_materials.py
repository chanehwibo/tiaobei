"""Generate source-bound review material without claiming current V11 acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from os_agent_memory.complex_retrieval import (
    CONSTRAINT_SHA256, CONSTRAINT_SUITE_PATH, FROZEN_SHA256, SUITE_PATH, score_request, summarize_rows,
)
from os_agent_memory.embeddings import HashEmbedding
from os_agent_memory.memory_store import _normalize_search_text
from os_agent_memory.provider_config import provider_identity
from os_agent_memory.request_contract import FROZEN_DATASET_SHA256, assess_frozen_requests
from os_agent_memory.retrieval_evidence import MIN_COVERAGE, POLICIES, content_coverage
from scripts.check_deliverables import inspect_ooxml
from scripts.compare_retrieval_runs import compare_reports, validate_report
from scripts.evaluate_evidence_development import (
    CHALLENGE_DATA, DATA as DEVELOPMENT_DATA, METHOD as DEVELOPMENT_METHOD, evaluation_query, load_suite,
)
from scripts.generate_takeover_materials import METRICS, WINDOWS_CHECKS, digest, require, validate_service
from scripts.material_status import INITIAL_STATUS, SDK_RISK_STATUS
from scripts.summarize_sdk_risk import summarize_sdk_risk
from scripts.verify_kylin_guest import file_hashes

EVIDENCE = Path("artifacts/verification/feedback")
CURRENT_EVIDENCE = EVIDENCE / "implementation-20260910"
WINDOWS_EVIDENCE = CURRENT_EVIDENCE / "windows"
OUTPUT = Path("deliverables/review-20260910-implementation")
OFFICE_NAMES = ("OS_Agent_反馈落实答辩稿.pptx", "OS_Agent_技术方案与复测报告.docx")
DOCUMENTS = (
    "docs/09_技术方案正文.md",
    "docs/38_相关工作与创新边界.md",
    "docs/39_评测口径与可信度.md",
    "docs/40_复杂场景与检索性能复测.md",
    "docs/41_复杂约束场景补测.md",
    "docs/43_近期相关工作与评测对照.md",
    "docs/44_正文证据检查与反例.md",
)
OBSOLETE = ("INCOMPLETE", "第五轮", "未完成")


def validate_windows_evidence(current, windows, requests, service):
    checks = windows.get("checks", {})
    require(WINDOWS_CHECKS.issubset(checks) and all(value is True for value in checks.values())
            and windows.get("local_release_checks_passed") is True
            and windows.get("competition_submission_ready") is False,
            "Windows engineering checks failed or acceptance was overstated")
    snapshot = windows.get("file_hashes", {})
    require(snapshot.get("lf_sha256") == current["lf_sha256"]
            and snapshot.get("excluded_generated_outputs") == current["excluded_generated_outputs"],
            "Windows measured source does not match current source")
    tests = windows.get("unit_tests", {})
    match = re.search(r"Ran (\d+) tests?", tests.get("output_tail", ""))
    require(tests.get("passed") is True and type(tests.get("tests_run")) is int
            and tests["tests_run"] > 0 and match is not None
            and int(match.group(1)) == tests["tests_run"]
            and re.search(r"(?m)^OK(?:\s|$)", tests["output_tail"]) is not None,
            "Windows test count or completion log mismatch")
    source = {key: value for key, value in snapshot.get("raw_sha256", {}).items()
              if key.startswith("src/") and key.endswith(".py")}
    gate = assess_frozen_requests(requests)
    require(bool(source) and requests.get("source_sha256") == source and gate["passed"]
            and requests.get("environment", {}).get("system") == "Windows"
            and windows.get("request_metrics") == requests["metrics"]
            and windows.get("request_counts") == requests["observation_counts"],
            "Windows frozen request details or source mismatch")
    validate_service(service)
    require(windows.get("service_workload") == service, "Windows service evidence mismatch")
    return gate


def frozen_block(windows):
    lines = [
        "<!-- BEGIN CURRENT WINDOWS EVIDENCE -->",
        "本次当前源码实测仅覆盖Windows开发机的公开合成冻结回归，不是第三方盲测或官方认证。",
        "HashEmbedding 256维、ngram=2、10,000条记录、top_k=3、阈值0.265；实际调用MemoryService.search。",
        "",
        "| 指标 | 门槛 | 当前Windows | 请求数 |",
        "| --- | --- | --- | --- |",
        *["| " + " | ".join(row) + " |" for row in metric_rows({"windows": windows})],
        "",
        f"自动化测试：Windows运行{windows['tests_run']}项，无失败，跳过{windows['tests_skipped']}项；"
        f"{windows['engineering_checks']}项工程检查通过。",
        "当前源码的V11部署待独立复验，不沿用历史V11通过数据。原生SDK仍是待复测风险项。",
        "五项及附加安全门槛均通过；敏感识别为实体级微平均，不代表任意敏感实体均可识别。",
        "",
        "数据原始SHA256：`" + FROZEN_DATASET_SHA256 + "`。",
        "原始逐请求报告：`" + (WINDOWS_EVIDENCE / "requests.json").as_posix() + "`；",
        "测试日志、检查结果与完整源码摘要：`" + (WINDOWS_EVIDENCE / "final_verification.json").as_posix() + "`。",
        "<!-- END CURRENT WINDOWS EVIDENCE -->",
    ]
    return "\n".join(lines)


def validate_current_complex(root, current, report, suite, *, expected_profiles, rounds, measured_snapshot=None):
    validate_report(report, suite)
    actual = {(row["corpus"]["records"], row["corpus"]["requested_hard_fraction_of_fillers"],
               row["mode"], row.get("required_terms_enabled", False), row.get("evidence_policy", "similarity"))
              for row in report["profiles"]}
    require(actual == expected_profiles and report["method"]["rounds"] == rounds,
            "current complex profiles or repetitions changed")
    policies = [policy for policy in POLICIES if any(row[4] == policy for row in expected_profiles)]
    require(report["method"].get("evidence_policies") == policies, "current evidence policy attribution changed")
    expected_method = {
        "boundary": "MemoryService.search: lock, query encoding, retrieval, reranking, serialization; no HTTP/Agent",
        "filler_fraction_denominator": "generated fillers only; fixed difficult documents always present",
        "percentile": "nearest_rank", "query_order": "frozen file order, no query warmup",
        "repetition_is_independent_sample": False, "controlled_snapshot_bypasses_ingestion": True,
        "quality_thresholds": {"macro_recall_at_3": .85, "no_answer_accuracy": .85, "p95_ms": 500},
    }
    require(all(report["method"].get(key) == value for key, value in expected_method.items())
            and all(row["provider"] == provider_identity(HashEmbedding()) for row in report["profiles"]),
            "current complex measurement boundary or provider changed")
    measured = current if measured_snapshot is None else measured_snapshot
    require(measured.get("lf_sha256") == current["lf_sha256"]
            and measured.get("excluded_generated_outputs") == current["excluded_generated_outputs"],
            "complex measured snapshot does not match current source")
    # Bind raw report hashes to the measured checkout, then compare normalized source.
    source = {key: value for key, value in measured["raw_sha256"].items()
              if key.startswith("src/") and key.endswith(".py")}
    require(report["source_sha256"] == source, "complex measured source does not match current source")
    paths = {report["dataset"]["path"], "src/os_agent_memory/complex_retrieval.py",
             "scripts/evaluate_complex_retrieval.py"}
    require(report["evaluator_sha256"] == {key: measured["raw_sha256"].get(key) for key in paths}
            and report["evaluator_sha256"][report["dataset"]["path"]]
            == digest(root / report["dataset"]["path"]),
            "complex evaluator source changed")
    require(report["environment"]["system"] == "Windows"
            and report["environment"]["python_hash_seed"] == "0"
            and report["safety_passed"] is True and report["latency_target_met"] is True,
            "current complex environment, safety or latency check failed")
    require(all("groups" in repeat for row in report["profiles"] for repeat in row["rounds"]),
            "current complex reports require grouped timing and quality")
    if suite["name"] == "complex_constraints_v1":
        require(report["method"].get("constraint_modes") == sorted({row[3] for row in expected_profiles})
                and report["method"].get("constraint_source")
                == "explicit input terms; never generated from relevance labels",
                "constraint comparison must preserve declared modes and explicit input attribution")
    if len(policies) > 1:
        validate_abstention_comparison(report)


def validate_abstention_comparison(report):
    groups = {}
    for profile in report["profiles"]:
        key = (profile["corpus"]["records"], profile["corpus"]["requested_hard_fraction_of_fillers"],
               profile["mode"], profile.get("required_terms_enabled", False))
        groups.setdefault(key, {})[profile["evidence_policy"]] = profile
    for profiles in groups.values():
        require(set(profiles) == set(POLICIES), "missing default or experimental comparison")
        original, experimental = (profiles[policy] for policy in POLICIES)
        require(original["corpus"] == experimental["corpus"]
                and original["provider"] == experimental["provider"], "policy comparison inputs differ")
        for first, second in zip(original["rounds"], experimental["rounds"]):
            for before, after in zip(first["rows"], second["rows"]):
                require(not after["returned"] or (before["returned"], before["scores"])
                        == (after["returned"], after["scores"]), "abstention policy changed ranking or scores")


def validate_development_evidence(root, current, report, *, challenge=False):
    suite, dataset = load_suite(root, challenge=challenge)
    require(report.get("schema_version") == 1 and report.get("dataset") == dataset
            and report.get("method") == DEVELOPMENT_METHOD
            and report.get("provider") == provider_identity(HashEmbedding())
            and report.get("competition_ready") is False and report.get("independent_blind") is False,
            "development identity, method or readiness changed")
    snapshot = report.get("source_sha256", {})
    require(report.get("source_unchanged_during_run") is True
            and snapshot.get("lf_sha256") == current["lf_sha256"]
            and snapshot.get("excluded_generated_outputs") == current["excluded_generated_outputs"]
            and report["environment"].get("system") == "Windows"
            and report["environment"].get("python_hash_seed") == "0",
            "development measured source or environment changed")
    profiles = report.get("profiles", [])
    require([row["evidence_policy"] for row in profiles] == list(POLICIES),
            "development must preserve both policies")
    documents = {row["id"]: row for row in suite["documents"]}
    for profile in profiles:
        rows = profile["rows"]
        require(len(rows) == len(suite["queries"]), "development request denominator changed")
        for row, original in zip(rows, suite["queries"]):
            query = evaluation_query(original)
            require(type(row["elapsed_ms"]) in (float, int) and math.isfinite(row["elapsed_ms"])
                    and row["elapsed_ms"] >= 0 and len(row["returned"]) <= 3
                    and len(row["returned"]) == len(row["scores"])
                    and all(identifier in documents for identifier in row["returned"])
                    and all(type(value) in (float, int) and math.isfinite(value) for value in row["scores"]),
                    "development has invalid timing or returned evidence")
            returned = [{"memory_id": key, "score": value} for key, value in zip(row["returned"], row["scores"])]
            require(score_request(query, returned, elapsed_ms=row["elapsed_ms"], error_type=row["error_type"]) == row,
                    "development query, labels or scores disagree with evidence")
            if profile["evidence_policy"] == "content_coverage_v1" and row["returned"]:
                fields = [tuple(_normalize_search_text(documents[key][field]).lower()
                                for field in ("title", "content")) for key in row["returned"]]
                require(content_coverage(_normalize_search_text(query["query"]).lower(), fields) >= MIN_COVERAGE,
                        "development output violates declared coverage")
        require(profile["summary"] == summarize_rows(rows) and profile["summary"]["errors"] == 0,
                "development summary or execution failed")
    for before, after in zip(profiles[0]["rows"], profiles[1]["rows"]):
        require(not after["returned"] or (before["returned"], before["scores"])
                == (after["returned"], after["scores"]), "development abstention changed ranking or scores")


def profile_summary(report):
    return [{
        "records": profile["corpus"]["records"],
        "hard_fraction": profile["corpus"]["requested_hard_fraction_of_fillers"],
        "mode": profile["mode"],
        "required_terms_enabled": profile.get("required_terms_enabled", False),
        "evidence_policy": profile.get("evidence_policy", "similarity"),
        "minimum_evidence_coverage": profile.get("minimum_evidence_coverage"),
        "rounds": [repeat["summary"] for repeat in profile["rounds"]],
        "categories": [repeat["categories"] for repeat in profile["rounds"]],
        "groups": [repeat["groups"] for repeat in profile["rounds"]],
    } for profile in report["profiles"]]


def build_summary(root=ROOT):
    root = Path(root).resolve()
    hashes = {}

    def read(relative, *, text=False):
        path = (root / relative).resolve()
        require(path.is_relative_to(root) and path.is_file(), "missing or unsafe review evidence")
        payload = path.read_bytes()
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(payload).hexdigest()
        return payload.decode("utf-8") if text else json.loads(payload)

    current = file_hashes(root)
    require(digest(root / "data/eval/request_regression_v1.json") == FROZEN_DATASET_SHA256
            and digest(root / SUITE_PATH) == FROZEN_SHA256
            and digest(root / CONSTRAINT_SUITE_PATH) == CONSTRAINT_SHA256, "frozen dataset bytes changed")
    windows = read(WINDOWS_EVIDENCE / "final_verification.json")
    requests = read(WINDOWS_EVIDENCE / "requests.json")
    service = read(WINDOWS_EVIDENCE / "service_workload.json")
    validate_windows_evidence(current, windows, requests, service)
    before = read(EVIDENCE / "complex_before.json")
    after = read(EVIDENCE / "complex_after.json")
    suite = read(SUITE_PATH)
    comparison = compare_reports(before, after, suite)
    comparison["input_sha256"] = {
        name: hashes[(EVIDENCE / ("complex_" + name + ".json")).as_posix()]
        for name in ("before", "after")
    }
    require(comparison == read(EVIDENCE / "complex_comparison.json"), "paired comparison was changed")
    require(comparison["performance_improvement_supported"] is True
            and comparison["identical_ranked_results_and_scores"] is True
            and after["safety_passed"] is True and after["latency_target_met"] is True,
            "paired performance or unchanged-output claim is unsupported")
    expected_profiles = {(size, fraction, "hybrid", False, "similarity")
                         for size in (1000, 10000) for fraction in (0, .75)}
    require({(row["corpus"]["records"], row["corpus"]["requested_hard_fraction_of_fillers"], row["mode"])
             for row in after["profiles"]} == {row[:3] for row in expected_profiles}
            and after["method"]["rounds"] == 3,
            "paired review needs all four profiles and three repetitions")
    measured = read(CURRENT_EVIDENCE / "complex_current.json")
    validate_current_complex(root, current, measured, suite, expected_profiles=expected_profiles, rounds=3,
                             measured_snapshot=windows["file_hashes"])
    ablations = read(CURRENT_EVIDENCE / "complex_ablations.json")
    validate_current_complex(root, current, ablations, suite,
                             expected_profiles={(1000, .75, mode, False, "similarity")
                                                for mode in ("lexical", "semantic", "hybrid")}, rounds=1,
                             measured_snapshot=windows["file_hashes"])
    constraint_suite = read(CONSTRAINT_SUITE_PATH)
    constraints = read(CURRENT_EVIDENCE / "complex_constraints.json")
    validate_current_complex(root, current, constraints, constraint_suite,
                             expected_profiles={(size, fraction, "hybrid", enabled, "similarity")
                                                for size in (1000, 10000) for fraction in (0, .75)
                                                for enabled in (False, True)}, rounds=3,
                             measured_snapshot=windows["file_hashes"])
    policy_complex = read(CURRENT_EVIDENCE / "complex_policy_comparison.json")
    validate_current_complex(root, current, policy_complex, suite,
                             expected_profiles={(1000, .75, "hybrid", False, policy) for policy in POLICIES},
                             rounds=3, measured_snapshot=windows["file_hashes"])
    policy_constraints = read(CURRENT_EVIDENCE / "constraints_policy_comparison.json")
    validate_current_complex(root, current, policy_constraints, constraint_suite,
                             expected_profiles={(1000, .75, "hybrid", True, policy) for policy in POLICIES},
                             rounds=3, measured_snapshot=windows["file_hashes"])
    development = []
    for filename, challenge in (("development_current.json", False), ("development_challenge_current.json", True)):
        report = read(CURRENT_EVIDENCE / filename)
        validate_development_evidence(root, current, report, challenge=challenge)
        development.append({
            "dataset": report["dataset"], "method": report["method"],
            "profiles": [{"evidence_policy": row["evidence_policy"], "summary": row["summary"]}
                         for row in report["profiles"]],
        })
    read(DEVELOPMENT_DATA)
    read(CHALLENGE_DATA)
    sdk = read(EVIDENCE / "sdk_risk.json")
    require(sdk == summarize_sdk_risk(root), "SDK risk does not match the raw probe")
    read(sdk["source"])
    discovery = read(CURRENT_EVIDENCE / "native_windows_discovery.json")
    require(discovery.get("display_status") == INITIAL_STATUS and discovery.get("latency_status") == SDK_RISK_STATUS
            and discovery.get("system") == "Windows" and discovery.get("probe_mode") == "discovery"
            and discovery.get("observations") == 0 and discovery.get("native_p95_ms") is None
            and discovery.get("native_latency_passed") is False and discovery.get("competition_ready") is False
            and discovery.get("real_embedding_executed") is False,
            "discovery must not be presented as native execution or latency acceptance")
    acceptance = read(Path("artifacts/verification/x01-x02/organizer_acceptance_reported_20260909.json"))
    require(acceptance.get("reported_organizer_acceptance") is True
            and acceptance.get("organizer_acceptance_verified") is False,
            "organizer acceptance attribution changed")
    windows_summary = {
        "tests_run": windows["unit_tests"]["tests_run"], "engineering_checks": len(windows["checks"]),
        "tests_skipped": int(match.group(1)) if (match := re.search(
            r"OK \(skipped=(\d+)\)", windows["unit_tests"]["output_tail"])) else 0,
        "metrics": requests["metrics"], "observation_counts": requests["observation_counts"],
        "environment": requests["environment"], "service": service["results"][-1],
    }
    for relative in DOCUMENTS:
        text = read(relative, text=True)
        require(INITIAL_STATUS in text and not any(value in text for value in OBSOLETE),
                "obsolete status in current document: " + relative)
        require("ROUND5 EVIDENCE" not in text, "replace the historical current-metrics block first")
        if relative == DOCUMENTS[0]:
            require(frozen_block(windows_summary) in text, "solution metrics do not match current Windows evidence")
    profiles = profile_summary(measured)
    ablation_rows = [{
        "mode": profile["mode"], **profile["rounds"][0]["summary"],
    } for profile in ablations["profiles"]]
    return {
        "schema_version": 3,
        "generated_at_utc": windows["generated_at_utc"],
        "scope": "current_windows_hash_public_synthetic_review_not_official_acceptance",
        "display_status": INITIAL_STATUS,
        "competition_ready": False,
        "windows": windows_summary,
        "v11_current_source_verified": False,
        "v11_status": "待当前版复验；历史安装或测试结果不替代当前服务部署证明",
        "sdk": sdk,
        "sdk_discovery": discovery,
        "complex": {
            "dataset_sha256": FROZEN_SHA256, "distinct_requests": 120,
            "positive_requests": 72, "no_answer_requests": 24, "scope_requests": 24,
            "profiles": profiles, "comparison": comparison, "ablations": ablation_rows,
            "comparison_scope": "historical_paired_optimization_not_current_source_timing",
            "quality_targets_met": measured["quality_targets_met"],
            "safety_passed": measured["safety_passed"],
            "latency_target_met": measured["latency_target_met"],
        },
        "constraints": {
            "dataset_sha256": CONSTRAINT_SHA256, "distinct_requests": 48,
            "positive_requests": 24, "no_answer_requests": 12, "scope_requests": 12,
            "profiles": profile_summary(constraints),
            "quality_targets_met": constraints["quality_targets_met"],
            "safety_passed": constraints["safety_passed"],
            "latency_target_met": constraints["latency_target_met"],
            "scope": "explicit_input_constraint_ablation_not_general_answerability_or_identical_output_speedup",
        },
        "evidence_experiment": {
            "default_policy": "similarity", "experimental_policy": "content_coverage_v1",
            "minimum_evidence_coverage": MIN_COVERAGE, "production_recommended": False,
            "complex_profiles": profile_summary(policy_complex),
            "constraint_profiles": profile_summary(policy_constraints),
            "development": development,
            "quality_targets_met": policy_complex["quality_targets_met"] and policy_constraints["quality_targets_met"],
            "scope": "visible_development_and_frozen_regression_not_blind_generalization_or_default_behavior",
        },
        "organizer_acceptance": acceptance,
        "source_lf_sha256": current["lf_sha256"],
        "evidence_sha256": hashes,
    }


def main_complex(summary):
    return next(row["rounds"][0] for row in summary["complex"]["profiles"]
                if row["records"] == 10000 and row["hard_fraction"] == .75)


def main_constraints(summary, enabled):
    return next(row for row in summary["constraints"]["profiles"]
                if row["records"] == 10000 and row["hard_fraction"] == .75
                and row["required_terms_enabled"] is enabled)


def metric_rows(summary):
    windows = summary["windows"]
    return [[label, target, f"{windows['metrics'][key]:.3f}ms" if key == "retrieval_p95_ms"
             else f"{windows['metrics'][key]:.2%}", str(windows["observation_counts"][key])]
            for key, label, target in METRICS]


def slide_sections(summary):
    windows, complex_result = summary["windows"], summary["complex"]
    service, quality = windows["service"], main_complex(summary)
    paired = complex_result["comparison"]
    constrained = main_constraints(summary, True)
    constrained_quality = constrained["rounds"][0]
    return [
        ("OS Agent 多源融合记忆优化系统", [
            "XA-202612 | 出题方反馈落实与当前源码复测 | " + summary["generated_at_utc"][:10],
            INITIAL_STATUS,
            "端侧记忆治理、作用域隔离、混合检索与可核验的遗忘。",
            "当前成绩：Windows + HashEmbedding + 公开合成数据。",
            "真实SDK：" + SDK_RISK_STATUS + "；V11待当前版复验。",
        ]),
        ("四项反馈的落实范围", [
            "状态：当前入口、Word/PPT统一为“" + INITIAL_STATUS + "”。",
            "SDK：保留真实慢调用，明确复测风险和解除条件。",
            "创新与可信度：五项基础工作及四项近期来源、分母和时延口径。",
            "复杂干扰：原12场景120请求；新增6场景48请求及显式约束对照。",
            "新增难例揭示近主题误答风险；不能概括为所有复杂质量达标。",
        ]),
        ("方案与工程贡献", [
            "事件 -> 校验/脱敏 -> 授权晋升 -> 偏好/知识 -> 召回/遗忘。",
            "显式设置优先，行为证据衰减；失败工具不能自动成为偏好。",
            "待决冲突、过期、隔离内容不进入普通检索。",
            "tenant/user/scene作用域贯穿索引、持久化、预览和确认。",
            "创新限定为OS Agent约束下的集成一致性，不声称基础算法首创。",
        ]),
        ("相关工作与创新边界", [
            "MemGPT：分层上下文管理；本项目侧重事件授权与治理。",
            "MemoryBank：长期记忆和遗忘；本项目增加显式决策与版本证据。",
            "Generative Agents：观察/反思/规划；本项目不声称复现智能体。",
            "LongMem：训练式记忆读取；本项目为可替换模型的低依赖原型。",
            "FAISS：向量索引；本项目不是ANN创新，也不作跨论文数字比较。",
        ]),
        ("近期记忆系统：先例与工程差异", [
            "Mem0：提取、整合、检索及图记忆变体；arXiv:2504.19413v1。",
            "MemoryOS：三层存储、更新、检索、生成；arXiv:2506.06326v1。",
            "持久记忆、三层划分和OS类比已有直接先例，不能声称首创。",
            "本项目差异：OS事件授权、失败工具降权、作用域及遗忘一致性。",
            "没有同条件运行这些系统，不挪用论文分数或宣称全面优于它们。",
        ]),
        ("公开基准：评测能力与现有缺口", [
            "LongMemEval：500问题，提取、跨会话、时间、更新、拒答。",
            "来源arXiv:2410.10813v2；索引、检索与最终阅读应分开评估。",
            "LongMemEval-V2：451问题，Web环境经验；arXiv:2605.12493v1。",
            "涵盖状态跟踪、工作流程、环境陷阱与前提识别；不是赛事标准。",
            "当前168个复杂请求是合成快照；没有外部基准分数或真实轨迹证明。",
        ]),
        ("评测口径与性能可信度", [
            "冻结五项分母为68/60/60/80/50；复杂集另报，绝不混分母。",
            "10,000条、Hash256/ngram2、top_k=3、阈值0.265。",
            "Recall取查询宏平均；实体F1取微平均；无答案、越域单列。",
            "P95使用nearest-rank；保留所有异常、超时与逐轮结果。",
            "服务计时包含锁、编码、召回、重排、序列化；不含HTTP/Agent。",
        ]),
        ("当前Windows冻结五项", [
            "公开合成回归；五项数值和附加安全门槛共同校验。",
        ]),
        ("复杂场景与干扰设计", [
            "12个虚构桌面场景，132条固定难例，120个不同查询。",
            "72正例、24近主题无答案、24作用域检查；12例需双证据。",
            "覆盖相似实体、条件差异、版本时效、长文和跨域污染。",
            "1,000/10,000条规模；0/75%相似填充，固定难例始终存在。",
            "75%的分母仅为生成填充记录；数据由开发者编写，不是盲测。",
        ]),
        ("历史配对：相同结果下的检索优化", [
            f"历史1,440对返回ID、排序和分数一致：{paired['identical_ranked_results_and_scores']}。",
            "这是旧源码配对证据；当前源码另测，不沿用历史时延。",
        ]),
        ("优化做了什么", [
            "倒排交集计数，替代逐候选重复构造集合。",
            "有界堆选择候选和top-k，替代全量排序。",
            "明确tenant/user时直接使用授权作用域，保留歧义拒绝。",
            "4096项有界缓存只解析不可变时间字符串，不缓存权限或答案。",
            "仅为最终命中构造结果；独立全排序参考与变更/过期测试兜底。",
        ]),
        ("复杂质量与误召回风险", [
            "10,000条、75%相似填充、首轮；全部请求保留。",
            "作用域零泄漏不等于近主题拒答可靠，后者仍需改进。",
        ]),
        ("本地检索消融", [
            "1,000条、75%相似填充、同一阈值0.265、各一次完整运行。",
            "这是固定阈值诊断，不是调参后的最优基线或论文复现。",
        ]),
        ("新增复杂运维与显式证据约束", [
            "6场景48请求：离线升级、故障转移、LSN恢复、证书、单位导出、IPC。",
            "78条固定记录；24正例、12无答案、12作用域检查；6例需双证据。",
            "相似编号/版本、元数据诱饵、混合日志及失效/越域记录作为干扰。",
            "required_terms由调用方显式提供，标题/正文逐项匹配后再取top-k。",
            "没有匹配授权记录时跳过编码；不从答案标签推导约束。",
        ]),
        ("显式约束开关对照：质量与时延", [
            "新集、当前同一源码、1万条/75%相似填充、首轮48请求。",
            "返回集合会改变；不是等输出加速或通用可回答性判断。",
        ]),
        ("约束效果的分母与剩余风险", [
            f"缺版本正确拒答{constrained['categories'][0]['absent_version']['no_answer_correct']}/6；"
            f"关系缺证据正确拒答{constrained['categories'][0]['unsupported_relation']['no_answer_correct']}/6。",
            "下表按请求类型单列P95；空作用域快返回不替代正例响应时延。",
        ]),
        ("可选正文证据检查：实现与决策", [
            "content_coverage_v1只检查已授权top-k的标题/正文，不读取标签。",
            "折扣共有标题与显式约束，以固定0.5词面覆盖决定是否拒答。",
            "只拒答、不重排、不改分；不缓存问句或正文。",
            "默认仍为similarity；实验会误拒同义问法和长背景。",
            "词汇覆盖不是关系蕴含，开发集高分不足以支持业务启用。",
        ]),
        ("实验对照：拒答收益伴随漏召回", [
            "1,000条/75%相似填充、同源串行三轮，下表首轮；约束集启用显式约束。",
            "两套复杂集均不能同时满足召回与拒答>=85%，不推荐默认启用。",
        ]),
        ("开发反例：保留失效结果", [
            "先测20个开发请求；公开对照后再追加10个长背景/同义及关系反例。",
            "追加数据不是盲测；不与168个复杂请求合并，不据此调阈值或删题。",
        ]),
        ("真实SDK：待复测风险项", [
            f"旧ABI真实执行1次，768维；总耗时{summary['sdk']['single_probe_ms']:,.3f}ms。",
            "含隔离进程、会话及模型初始化；单次不是P95。",
            "当前provider每次调用初始化，不能假定后续自动摊销。",
            "新ABI缺符号；模型身份/版本及向量库往返尚无完整验证。",
            "本机发现探针调用0次；解除需核验模型，至少50不同请求、三轮全服务P95<=500ms。",
        ]),
        ("工程验证与部署边界", [
            f"Windows运行{windows['tests_run']}项测试，无失败，跳过{windows['tests_skipped']}项；"
            f"{windows['engineering_checks']}项工程检查通过。",
            f"1,000条真实服务负载：查询P95 {service['mixed_query_p95_ms']:.3f}ms；"
            f"HTTP P99 {service['http_query_p99_ms']:.3f}ms。",
            f"进程RSS末值 {service['process_resources']['rss_after_bytes']} bytes；不含模型服务。",
            "V11待当前版复验；历史HTTP曾受系统网络管控影响，失败保留。",
            "主办方部署/资源/评分认可按参赛者确认处理，原件待归档。",
        ]),
        ("复现与证据绑定", [
            "源码、冻结数据、逐请求结果、对比报告分别记录SHA256。",
            "运行unittest、check_source、evaluate_requests、verify_release。",
            "复杂回归使用PYTHONHASHSEED=0；两套数据按规模/干扰各三轮。",
            "本轮仅做允许列表预检，不打包；封包后须另行解包复测。",
            "旧ZIP和失败记录只作追溯，不覆盖、不冒充当前版通过。",
        ]),
        ("当前结论与验收边界", [
            f"复杂正例Recall@3 {quality['macro_recall_at_3']:.2%}；"
            f"近主题无答案正确率 {quality['no_answer_accuracy']:.2%}。",
            f"新集显式约束后Recall@3 {constrained_quality['macro_recall_at_3']:.2%}；"
            f"无答案正确率 {constrained_quality['no_answer_accuracy']:.2%}。",
            "显式约束改善特定干扰；复杂拒答、真实SDK和V11当前版仍有风险。",
            "词面证据实验暴露副作用，保持默认关闭；实现通过不等于质量达标。",
            "独立Agent/Judge、保密标签、授权真实案例和赛事材料需外部证据。",
            "技术创新性30分、性能可信度25分仅为反馈组织依据，不是自评得分。",
            INITIAL_STATUS + "；不自动提交或发送邮件。",
        ]),
    ]


def slide_tables(summary):
    quality = main_complex(summary)
    comparison = summary["complex"]["comparison"]
    return {
        8: [["指标", "门槛", "Windows", "请求数"], *metric_rows(summary)],
        10: [["记录数", "相似填充", "优化前P95", "优化后P95"],
            *[[f"{row['records']:,}", f"{row['hard_fraction']:.0%}",
               f"{row['before_p95_ms']:.3f}ms", f"{row['after_p95_ms']:.3f}ms"]
              for row in comparison["rows"] if row["round"] == 1]],
        12: [["质量项", "实测值", "解释"],
             ["正例宏Recall@3", f"{quality['macro_recall_at_3']:.2%}", "不是拒答正确率"],
             ["固定分母P@3", f"{quality['precision_at_3']:.2%}", "按正例查询数乘3"],
             ["近主题无答案", f"{quality['no_answer_accuracy']:.2%}",
              f"{quality['no_answer_correct']}/{quality['no_answer_requests']}正确，{quality['false_answers']}例误答"],
             ["干扰返回占比", f"{quality['distractor_return_rate']:.2%}", "正例返回片段中的无关项"],
             ["跨域泄漏 / 异常", f"{quality['leaked_records']} / {quality['errors']}", "不能覆盖近主题误答风险"],
             ["当前服务P95", f"{quality['p95_ms']:.3f}ms", "120个不同请求，非HTTP"]],
        13: [["模式", "Recall@3", "无答案正确率", "P95"],
             *[[row["mode"], f"{row['macro_recall_at_3']:.2%}", f"{row['no_answer_accuracy']:.2%}",
                f"{row['p95_ms']:.3f}ms"] for row in summary["complex"]["ablations"]]],
        15: [["显式约束", "Recall@3", "无答案正确率", "全请求P95"],
             *[["启用" if enabled else "关闭", f"{quality['macro_recall_at_3']:.2%}",
                f"{quality['no_answer_accuracy']:.2%}", f"{quality['p95_ms']:.3f}ms"]
               for enabled in (False, True)
               for quality in [main_constraints(summary, enabled)["rounds"][0]]]],
        16: [["类型", "请求数", "约束开启P95"],
             *[[label, str(row["requests"]), f"{row['p95_ms']:.3f}ms"]
               for kind, label in (("positive", "正例"), ("no_answer", "无答案"), ("scope", "作用域"))
               for row in [main_constraints(summary, True)["groups"][0]["kind"][kind]]]],
        18: [["数据/策略", "Recall@3", "无答案正确率", "全请求P95"],
             *[[label + (" / 默认" if profile["evidence_policy"] == "similarity" else " / 实验"),
                f"{row['macro_recall_at_3']:.2%}", f"{row['no_answer_accuracy']:.2%}", f"{row['p95_ms']:.3f}ms"]
               for field, label in (("complex_profiles", "原复杂集"), ("constraint_profiles", "约束集"))
               for profile in summary["evidence_experiment"][field] for row in [profile["rounds"][0]]]],
        19: [["开发集/策略", "Recall@3", "无答案正确", "不同请求"],
             *[[("追加反例" if report["dataset"]["challenge_added_after_initial_comparison"] else "初始开发")
                + (" / 默认" if profile["evidence_policy"] == "similarity" else " / 实验"),
                f"{row['macro_recall_at_3']:.2%}", f"{row['no_answer_correct']}/{row['no_answer_requests']}",
                str(report["dataset"]["distinct_requests"])]
               for report in summary["evidence_experiment"]["development"]
               for profile in report["profiles"] for row in [profile["summary"]]]],
    }


def render_markdown(summary):
    lines = ["# 当前源码反馈落实与复测摘要", "", "状态：**" + INITIAL_STATUS + "**。", ""]
    tables = slide_tables(summary)
    for index, (title, body) in enumerate(slide_sections(summary), 1):
        lines.extend([f"## {index}. {title}", ""])
        lines.extend("- " + value for value in body)
        lines.append("")
        if index in tables:
            rows = tables[index]
            lines += ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * len(rows[0])) + " |"]
            lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
            lines.append("")
    lines += ["## 可追溯证据", "",
              "冻结五项SHA256：`" + FROZEN_DATASET_SHA256 + "`。",
              "复杂数据SHA256：`" + FROZEN_SHA256 + "`。",
              "显式约束数据SHA256：`" + CONSTRAINT_SHA256 + "`。",
              "完整文件摘要与当前源码LF摘要见同目录evidence_summary.json。", ""]
    return "\n".join(lines)


def build_office(root, summary, output):
    from docx import Document
    from docx.oxml import OxmlElement as DocElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt as DocPt
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.util import Inches, Pt
    from scripts.generate_technical_doc import _add_markdown

    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2)
    section.left_margin = section.right_margin = Cm(2.2)
    for name, size in (("Normal", 10.5), ("Heading 1", 18), ("Heading 2", 14), ("Heading 3", 12)):
        style = document.styles[name]
        style.font.name, style.font.size = "Microsoft YaHei", DocPt(size)
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Microsoft YaHei")
    _add_markdown(document, output / "current_report.md")
    for relative in DOCUMENTS:
        first_paragraph = len(document.paragraphs)
        _add_markdown(document, Path(root) / relative)
        document.paragraphs[first_paragraph].paragraph_format.page_break_before = True
    for table in document.tables:
        table.rows[0]._tr.get_or_add_trPr().append(DocElement("w:tblHeader"))
        for row in table.rows:
            row._tr.get_or_add_trPr().append(DocElement("w:cantSplit"))
    footer = section.footer.paragraphs[0]
    footer.text = "OS Agent | " + INITIAL_STATUS + " | "
    field = DocElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    footer.runs[0].font.size = DocPt(8)
    document.core_properties.author = document.core_properties.last_modified_by = ""
    document.core_properties.title = "OS Agent 技术方案、相关工作与当前源码复测报告"
    document.core_properties.subject = INITIAL_STATUS
    document.save(output / OFFICE_NAMES[1])

    presentation = Presentation()
    presentation.slide_width, presentation.slide_height = Inches(13.333), Inches(7.5)
    presentation.core_properties.author = presentation.core_properties.last_modified_by = ""
    presentation.core_properties.title = "OS Agent 反馈落实答辩稿"
    presentation.core_properties.subject = INITIAL_STATUS
    tables = slide_tables(summary)

    def style_paragraph(paragraph, size, color, bold=False):
        font = paragraph.font
        font.name, font.size, font.bold = "Microsoft YaHei", Pt(size), bold
        font.color.rgb = RGBColor(*color)
        east_asia = OxmlElement("a:ea")
        east_asia.set("typeface", "Microsoft YaHei")
        font._rPr.append(east_asia)

    sections = slide_sections(summary)
    for index, (title, body) in enumerate(sections, 1):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])

        def text_box(x, y, width, height, lines, size, color=(35, 42, 42), bold=False):
            frame = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height)).text_frame
            frame.word_wrap = True
            for number, text in enumerate(lines):
                paragraph = frame.paragraphs[0] if number == 0 else frame.add_paragraph()
                paragraph.text = text
                paragraph.space_after = Pt(16)
                style_paragraph(paragraph, size, color, bold)

        text_box(.65, .4, 12, .8, [title], 28, bold=True)
        text_box(.7, 1.45, 11.9, 1.5 if index in tables else 5.1, body,
                 17 if index in tables else 19)
        if index in tables:
            rows = tables[index]
            table = slide.shapes.add_table(len(rows), len(rows[0]), Inches(.75), Inches(3.05),
                                           Inches(11.8), Inches(3.5)).table
            widths = (3.9, 2.0, 5.9) if len(rows[0]) == 3 else (3.2, 2.5, 3.5, 2.6)
            for column, width in zip(table.columns, widths):
                column.width = Inches(width)
            for row_index, row in enumerate(rows):
                for column_index, value in enumerate(row):
                    cell = table.cell(row_index, column_index)
                    cell.text = value
                    cell.margin_top = cell.margin_bottom = Inches(.08)
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = RGBColor(*((32, 104, 91) if row_index == 0 else (244, 247, 246)))
                    for paragraph in cell.text_frame.paragraphs:
                        style_paragraph(paragraph, 16, (255, 255, 255) if row_index == 0 else (35, 42, 42))
        text_box(.7, 6.92, 11, .35, ["公开合成回归 | HashEmbedding | " + INITIAL_STATUS], 11, (145, 51, 54))
        text_box(12, 6.92, .65, .35, [f"{index}/{len(sections)}"], 11)
    presentation.save(output / OFFICE_NAMES[0])


def verify_outputs(root, output, *, require_office=True):
    summary = build_summary(root)
    issues = []
    if json.loads((output / "evidence_summary.json").read_bytes()) != summary:
        issues.append("summary_does_not_match_current_evidence")
    if (output / "current_report.md").read_text(encoding="utf-8") != render_markdown(summary):
        issues.append("markdown_does_not_match_current_evidence")
    reports = {}
    if require_office:
        quality = main_complex(summary)
        expected = [INITIAL_STATUS, SDK_RISK_STATUS, "HashEmbedding", "V11", "MemGPT", "FAISS",
                    "nearest-rank", f"{quality['no_answer_accuracy']:.2%}", f"{quality['macro_recall_at_3']:.2%}",
                    f"{summary['sdk']['single_probe_ms']:,.3f}",
                    str(summary["windows"]["tests_run"])]
        expected += [row[2] for row in metric_rows(summary)]
        expected += ["required_terms", "48请求", "关系缺证据",
                     f"{main_constraints(summary, True)['rounds'][0]['no_answer_accuracy']:.2%}"]
        expected += ["Mem0", "MemoryOS", "LongMemEval", "LongMemEval-V2", "content_coverage_v1",
                     "默认仍为similarity", "追加反例", "不推荐默认启用", "不打包"]
        for name in OFFICE_NAMES:
            path = output / name
            report = inspect_ooxml(path, expected_slide_count=len(slide_sections(summary)))
            text = "\n".join(report.pop("texts"))
            report["missing_values"] = sorted({value for value in expected if value not in text})
            report["obsolete_status"] = [value for value in OBSOLETE if value in text]
            report["passed"] = report["passed"] and not report["missing_values"] and not report["obsolete_status"]
            report["sha256"] = digest(path) if path.is_file() else None
            reports[name] = report
    return {
        "passed": not issues and all(row["passed"] for row in reports.values()),
        "scope": "current_windows_source_and_review_evidence_not_current_v11_or_official_acceptance",
        "issues": issues, "deliverables": reports, "visual_render_verified": False,
        "complex_quality_targets_met": summary["complex"]["quality_targets_met"],
        "constraint_quality_targets_met": summary["constraints"]["quality_targets_met"],
        "experimental_quality_targets_met": summary["evidence_experiment"]["quality_targets_met"],
        "experimental_policy_default_enabled": False,
        "native_latency_passed": summary["sdk"]["native_latency_passed"],
        "v11_current_source_verified": False, "competition_ready": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / OUTPUT)
    parser.add_argument("--office", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    require(args.report is None or not args.report.exists(), "refusing to overwrite review verification")
    if not args.check_only:
        require(not args.output_dir.exists(), "refusing to overwrite review materials")
        summary = build_summary(ROOT)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "evidence_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "current_report.md").write_text(render_markdown(summary), encoding="utf-8")
        if args.office:
            build_office(ROOT, summary, args.output_dir)
    report = verify_outputs(ROOT, args.output_dir, require_office=args.office or args.check_only)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

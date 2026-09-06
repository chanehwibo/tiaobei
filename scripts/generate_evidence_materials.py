"""Generate one evidence summary and current reports from fixed raw results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/verification/round2"


def generate():
    verification = json.loads((EVIDENCE / "final_verification.json").read_text(encoding="utf-8"))
    ablations = json.loads((EVIDENCE / "ablations.json").read_text(encoding="utf-8"))
    workload = json.loads((ROOT / "artifacts/verification/round2_service_after.json").read_text(encoding="utf-8"))
    largest = verification["benchmark"]["results"][-1]
    summary = {
        "generated_at_utc": verification["generated_at_utc"], "tests": verification["unit_tests"]["tests_run"],
        "local_checks_passed": verification["local_release_checks_passed"],
        "quality_targets": verification["internal_quality_targets"],
        "competition_ready": verification["competition_submission_ready"],
        "evaluation": verification["evaluations"]["v3"]["test"],
        "performance": largest, "service": workload["results"][-1],
        "dataset": {"events": 42, "topics": 18, "queries": 54, "test_queries": 18},
        "comparisons": [{k: v for k, v in row["result"].items() if k != "rows"}
                        for row in ablations["retrieval_comparisons"]],
        "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in (EVIDENCE / "final_verification.json", EVIDENCE / "ablations.json",
                                        ROOT / "artifacts/verification/round2_service_after.json")},
    }
    (EVIDENCE / "evidence_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = summary["evaluation"]
    lines = [
        "# 第二轮本地工程与评测报告",
        "",
        f"固定证据生成时间（UTC）：{summary['generated_at_utc']}。本报告与 PPT 共用 evidence_summary.json。",
        "",
        "## 验收结论",
        "",
        f"- 工程检查通过：{summary['local_checks_passed']}；自动化测试 {summary['tests']} 项全部通过。",
        f"- 内部质量目标全部满足：{all(summary['quality_targets'].values())}；正式赛事就绪：{summary['competition_ready']}。",
        "- 真实 SDK、麒麟、盲测、授权案例、视频和赛事凭证仍未取得；本轮仅验收本地任务。",
        "",
        "## 第二轮实质改造",
        "",
        "服务、CLI 与评测统一经过生命周期门槛；检索检查有效期；软删除重启后不恢复向量；",
        "持久化失败回滚内存、阶段证据和确认状态。SQLite 按主键增量写入，跨请求/重启去重，",
        "确认回执幂等，删除同时清理阶段证据。冲突/遗忘确认绑定租户与用户。",
        "词法倒排候选与近似语义候选合并，冲突补数字、条件、场景判断。",
        "embedding 配置贯穿服务、评测与基准，模型版本/维度变化时重建缓存，限制超时调用。",
        "界面新增合成场景、偏好历史、冲突前后对照、目标预览与演示租户恢复。",
        "",
        "## 数据与协议",
        "",
        "v3 含 42 个输入事件、18 个办公主题、54 个查询。每分区 14 个事件和 18 个查询，",
        "其中 12 个正例、6 个无答案。正文、模板族跨分区交集均为零，含改写及跨用户干扰。",
        "全部为开发者持有标签的合成内部评测，不是独立盲测；题量不足以证明开放域泛化。",
        f"仅用 dev 选择统一阈值 {result['threshold']}，然后测试。配置及 dev 摘要见 evaluation_v3.json。",
        "测试标签在开发过程中可见，后续修改必须如实注明再次接触 test；本轮不能称为盲测。",
        "",
        "## 检索对照",
        "",
        "| 模式 | 正例 Recall@3 | 无答案正确率 | 平衡得分 | dev 阈值 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["comparisons"]:
        lines.append(f"| {row['mode']} | {row['positive_recall_at_3']:.4f} | {row['no_answer_accuracy']:.4f} | {row['balanced_score']:.4f} | {row['threshold']} |")
    lines += [
        "",
        "平衡得分为正例召回与无答案正确率的平均值，各模式分别在 dev 定阈值。",
        "当前混合方案没有稳定胜过词法基线，不应宣称算法全面领先。语义候选覆盖更广，但也引入干扰。",
        "质量目标仍为两项各 ≥0.85；未达目标如实保留，不通过降低门槛把结果标绿。",
        "缓存消融统计编码次数并核对返回结果一致；衰减诊断出现持平也保留，单一诊断不等于统计提升。",
        "旧 v1/v2 标签包含一次性低证据：门控后存在漏报和目标未满足，旧版 1.0 不再作为当前成绩。",
        "",
        "## 性能",
        "",
        "| 规模 | 冷查询 ms | 热 p99 ms | Python 峰值 MB | SQLite MB |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in verification["benchmark"]["results"]:
        lines.append(f"| {row['records']} | {row['cold_query_ms']} | {row['hot_query_p99_ms']} | {row['peak_python_memory_mb']} | {row['sqlite_disk_mb']} |")
    lines += [
        "",
        "上表是 Windows + HashEmbedding 检索规模基准；新增实际服务负载另计生命周期、冲突、SQLite 和 HTTP：",
        "",
        "| 初始知识 | 批量接入 ms | 单条追加 ms | 重启加载 ms | 混合查询 p99 ms | HTTP p99 ms |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in workload["results"]:
        lines.append(f"| {row['records']} | {row['service_ingest_ms']} | {row['single_add_ms']} | {row['restart_load_ms']} | {row['mixed_query_p99_ms']} | {row['http_query_p99_ms']} |")
    lines += [
        "",
        "实际服务负载使用 4 线程混合读写，检查重启后记录数与查询非空；非空不等于检索准确。",
        "p99 为少量采样经验值，不是生产 SLA。当前事务为单进程串行写，增量落盘仍需比较当前状态，",
        "回滚快照有内存成本；多个进程同时写同一数据库尚不支持。",
        "",
        "## 复现与证据",
        "",
        chr(96) * 3 + "powershell",
        "python -S -m unittest discover -s tests -v",
        "python scripts/check_source.py",
        "node scripts/check_dashboard.cjs",
        "python scripts/evaluate_v3.py --embedding-config config/embedding.hash.json",
        "python scripts/benchmark_service.py --sizes 100,1000 --rounds 30",
        "python scripts/verify_release.py --artifact-dir artifacts/runtime/verification --sizes 100,1000,5000,10000 --rounds 30",
        chr(96) * 3,
        "",
        "固定证据：artifacts/verification/round2/；服务基准：round2_service_after.json。",
        "CI 配置覆盖 Windows/Linux 与 Python 3.10/3.14；配置存在不等于所有远端任务已通过，以 GitHub Actions 实际结果为准。",
        "Python 3.10 语法检查及本机完整测试、wheel 构建独立记录。",
        "",
        "## 功能与证据对应",
        "",
        "| 设计 | 证据 | 适用边界 |",
        "| --- | --- | --- |",
        "| 晋升、有效期、删除、回滚 | test_round2.py | 合成回归 |",
        "| 增量与重启幂等 | test_incremental.py | 单进程写入 |",
        "| 检索候选与条件冲突 | test_retrieval_hard_cases.py、ablations.json | 规则与近似候选 |",
        "| SDK 配置/缓存/超时 | test_provider_config.py | 模拟适配器，无真实 SDK |",
        "| 演示与作用域 | test_web_server.py | localhost 可信上层，无登录认证 |",
        "| 可交付性 | test_packaging.py、test_archive_submission.py | INCOMPLETE 草案 |",
        "",
    ]
    report = "\n".join(lines)
    for path in (ROOT / "docs/18_第二轮验收报告.md", ROOT / "docs/测试报告.md"):
        path.write_text(report, encoding="utf-8")
    return summary


if __name__ == "__main__":
    summary = generate()
    print({"tests": summary["tests"], "quality_targets": summary["quality_targets"]})

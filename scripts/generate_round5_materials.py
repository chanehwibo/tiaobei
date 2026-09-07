"""Generate current materials from measured evidence, preserving older rounds."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("artifacts/verification/round5")
BEGIN = "<!-- BEGIN ROUND5 EVIDENCE -->"
END = "<!-- END ROUND5 EVIDENCE -->"
METRICS = (
    ("preference_accuracy", "偏好逐请求准确率", ">=85%"),
    ("knowledge_recall", "知识 Recall@3", ">=85%"),
    ("conflict_accuracy", "冲突正确率", ">=88%"),
    ("retrieval_p95_ms", "检索 P95", "<=500ms"),
    ("sensitive_f1", "敏感实体 F1", ">=90%"),
)


def build_summary(root=ROOT):
    sources = {}

    def read(relative):
        payload = (root / relative).read_bytes()
        sources[relative.as_posix()] = hashlib.sha256(payload).hexdigest()
        return json.loads(payload)

    windows_dir = BASE / "windows"
    windows_path = windows_dir / "requests.json"
    if not (root / windows_path).is_file():
        windows_path = BASE / "requests_windows.json"
    guest_dir = BASE / ("kylin_final" if (root / BASE / "kylin_final/kylin_vm.json").is_file() else "kylin")
    windows, guest = read(windows_path), read(guest_dir / "requests.json")
    if windows["dataset"]["sha256"] != guest["dataset"]["sha256"]:
        raise ValueError("Windows and Kylin evidence use different datasets")
    for report, system in ((windows, "Windows"), (guest, "Linux")):
        if (report["environment"]["system"] != system
                or report["all_targets_met"] is not True
                or not all(value is True for value in report["safety_checks"].values())
                or report["retrieval"]["records"] != 10000
                or report["retrieval"]["threshold"] != 0.265):
            raise ValueError("request evidence is not the validated dual-environment configuration")
    vm = read(guest_dir / "kylin_vm.json")
    native = read(BASE / "native/legacy_runtime_started.json")
    final_path = windows_dir / "final_verification.json"
    final = read(final_path) if (root / final_path).is_file() else None
    tests_path = BASE / "materials_tests.json"
    if final is None:
        if not (root / tests_path).is_file():
            tests_path = BASE / "native/unit_tests.json"
        tests = read(tests_path)
    else:
        tests, tests_path = final["unit_tests"], final_path
    count = tests.get("tests_run")
    if count is None:
        match = re.search(r"Ran (\d+) tests?", tests.get("output_tail", ""))
        count = int(match.group(1)) if match else None
    if not count or tests.get("passed") is not True:
        raise ValueError("test evidence has no verified count/status")

    def request_summary(report, source):
        return {key: report[key] for key in (
            "metrics", "observation_counts", "safety_checks", "all_targets_met", "dataset", "environment"
        )} | {"source": source.as_posix(), "records": report["retrieval"]["records"],
             "threshold": report["retrieval"]["threshold"], "provider": report["retrieval"]["provider"],
             "sensitive_counts": {key: report["sensitive"][key] for key in ("tp", "fp", "fn")}}

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "public_synthetic_regression_not_independent_blind_or_official_certification",
        "tests": count,
        "test_results": {
            "windows": {"tests_run": count, "passed": tests["passed"], "source": tests_path.as_posix()},
            "kylin": {"tests_run": vm["tests_run"], "passed": vm["tests_passed"],
                      "source": (guest_dir / "kylin_vm.json").as_posix()},
        },
        "requests": {"windows": request_summary(windows, windows_path),
                     "kylin": request_summary(guest, guest_dir / "requests.json")},
        "vm": {key: vm[key] for key in (
            "installed", "required_v11_verified", "guest_verification_passed", "virtualization",
            "root_filesystem", "machine", "python"
        )},
        "native": {key: native[key] for key in (
            "real_embedding_executed", "dimensions", "single_probe_ms", "model_identity_verified",
            "model_version_verified", "vector_database_connected", "agent_executed",
            "container_sample_executed", "independent_judge_executed"
        )},
        "local_checks_passed": final["local_release_checks_passed"] if final else None,
        "competition_ready": False,
        "source_sha256": sources,
    }


def format_metric(key, value):
    return f"{value:.3f}ms" if key == "retrieval_p95_ms" else f"{value:.2%}"


def evidence_block(summary):
    windows, guest = summary["requests"]["windows"], summary["requests"]["kylin"]
    lines = [
        BEGIN,
        "公开合成冻结回归，不是第三方盲测或官方认证；两个环境均为 HashEmbedding 256 维、"
        "10,000 条记录、top_k=3、阈值 0.265，实际调用 MemoryService.search。",
        "",
        "| 指标 | 门槛 | Windows | 麒麟 V11 虚拟机 | 请求数 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for key, label, target in METRICS:
        lines.append(f"| {label} | {target} | {format_metric(key, windows['metrics'][key])} | "
                     f"{format_metric(key, guest['metrics'][key])} | {windows['observation_counts'][key]} |")
    tests = summary["test_results"]
    native = summary["native"]
    lines += [
        "",
        f"自动化测试：Windows {tests['windows']['tests_run']} 项"
        f"（{'通过' if tests['windows']['passed'] else '失败'}）；"
        f"V11 {tests['kylin']['tests_run']} 项（{'通过' if tests['kylin']['passed'] else '失败'}）。"
        "两个报告各自绑定被测版本，最终交付需核对源码摘要。",
        f"五项及附加安全门槛：Windows {windows['all_targets_met']}；V11 {guest['all_targets_met']}。"
        f"敏感识别为实体级微平均，Windows TP/FP/FN="
        f"{windows['sensitive_counts']['tp']}/{windows['sensitive_counts']['fp']}/{windows['sensitive_counts']['fn']}。",
        f"旧 ABI 原生单探针返回 {native['dimensions']} 维向量，耗时 {native['single_probe_ms']:.3f}ms；"
        "模型身份未验证，不是原生 P95 或质量达标证据。向量数据库往返、真实 Agent/容器和独立 Judge 尚未验证。",
        "",
        f"数据原始 SHA256：`{windows['dataset']['sha256']}`。",
        f"原始报告：`{windows['source']}`、`{guest['source']}`；"
        "完整来源摘要见 `artifacts/verification/round5/evidence_summary.json`。",
        END,
    ]
    return "\n".join(lines)


def replace_block(text, block):
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError("exactly one evidence block is required")
    before, rest = text.split(BEGIN, 1)
    _, after = rest.split(END, 1)
    return before + block + after


def render_report(summary):
    return "\n".join([
        "# 第五轮逐请求与双环境验收", "",
        "生成时间（UTC）：" + summary["generated_at_utc"], "",
        evidence_block(summary), "",
        "## 评分口径", "",
        "- 偏好按每个请求的完整键值集合评分，多报或漏报都算错；提取和长期持久化授权分开。",
        "- 召回为60个不同正例请求的 Recall@3；另有12个无答案、8个跨作用域请求，不能通过乱答提高召回。",
        "- 冲突为60组独立存储上的检测与最终状态联合评分，包含应冲突及不应冲突的反例。",
        "- P95取80个不同查询的 nearest-rank，不预热、不调整单条阈值；含服务锁及结果序列化，"
        "不含HTTP传输或Agent推理。填充语料为合成干扰项，不代表真实业务分布。",
        "- 敏感识别为50请求上的实体类型及精确值多重集；重复检测计FP，漏检计FN，另查脱敏泄漏。",
        "- 持久化、入库、无答案、作用域和脱敏泄漏分别作为硬门槛；不降低授权或生命周期要求。",
        "",
        "## 迭代与证据", "",
        "冻结基线见 `docs/30_逐请求评测与冻结基线.md`。首轮偏好70.59%、敏感F1 70.59%的失败、"
        "偏好迭代和后续全量质量迭代均保留在 round5；没有改标签、复制请求或更换分母。",
        "V11磁盘安装、根文件系统、虚拟化和首轮临时目录失败详见 `docs/31_麒麟V11客户机实测.md`；"
        "SDK新旧ABI和真实探针详见 `docs/27_真实SDK接入与证据边界.md`。",
        "v1/v2旧标签诊断及v3历史检索数据继续保留，不沿用旧满分宣称，也不为绿灯削弱晋升门槛。",
        "",
        "## 复现", "", "```bash",
        "python -S -m unittest discover -s tests -v",
        "python -S scripts/evaluate_requests.py --size 10000 --require-targets --output artifacts/runtime/requests.json",
        "python -S scripts/verify_release.py --artifact-dir artifacts/runtime/release --sizes 100,1000,5000,10000 --rounds 30",
        "```", "",
        "实际V11客户机使用 `env TMPDIR=/var/tmp python3 -S scripts/verify_kylin_guest.py --output <新目录>`。"
        "不能在Windows执行后把报告名改成麒麟结果。",
        "",
        "## 外部未完成", "",
        "官方强制银河麒麟V11，SDK为推荐项；V11虚拟机实测不等于出题方认可部署形式。"
        "第三方盲测、正式Agent/Judge、匹配原生模型/向量资源、授权案例、"
        "不超过7分钟的最终视频复核、平台审核、盖章报名表和提交回执仍需完成。",
        f"本地发布总验收：{summary['local_checks_passed']}（null表示尚未运行最终验收）。"
        "正式提交保持 INCOMPLETE，`competition_ready=false`，不自动发送邮件。", "",
    ])


def generate(root=ROOT):
    summary = build_summary(root)
    report = render_report(summary)
    outputs = {root / BASE / "evidence_summary.json": json.dumps(summary, ensure_ascii=False, indent=2) + "\n"}
    outputs.update({root / "docs" / name: report for name in ("测试报告.md", "32_第五轮验收报告.md")})
    for relative in (
        "README.md", "docs/09_技术方案正文.md", "docs/10_PPT逐页讲稿与答辩问答.md",
        "docs/11_演示视频分镜与录制检查表.md",
    ):
        path = root / relative
        outputs[path] = replace_block(path.read_text(encoding="utf-8"), evidence_block(summary))
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")
    print(json.dumps({"tests": summary["tests"], "local_checks_passed": summary["local_checks_passed"],
                      "competition_ready": False}))
    return summary


if __name__ == "__main__":
    generate()

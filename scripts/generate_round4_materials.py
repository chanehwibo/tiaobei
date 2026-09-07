"""Generate the current report from raw evidence without changing old archives."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/verification/round4"


def generate():
    old = json.loads((ROOT / "artifacts/verification/round3/evidence_summary.json").read_text(encoding="utf-8"))
    official = json.loads((EVIDENCE / "official_diagnostics.json").read_text(encoding="utf-8"))
    verification_path = EVIDENCE / "final_verification.json"
    verification = json.loads(verification_path.read_text(encoding="utf-8")) if verification_path.exists() else {}
    vm_path = EVIDENCE / "kylin_vm.json"
    vm = json.loads(vm_path.read_text(encoding="utf-8")) if vm_path.exists() else {"installed": False, "tests_passed": False}
    tests = verification.get("unit_tests", {})
    summary = {**old, "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tests": tests.get("tests_run", "待最终复核"), "local_checks_passed": verification.get("local_release_checks_passed", False),
        "competition_ready": False, "official": official, "vm": vm,
        "historical_metrics_source": "round3/evidence_summary.json",
        "historical_metrics_note": "evaluation/performance/service/comparisons are third-round internal regression evidence",
        "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (EVIDENCE / "official_diagnostics.json", verification_path, vm_path) if path.exists()}}
    (EVIDENCE / "evidence_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    lines = ["# 第四轮：官方口径与隔离环境验收", "", "更新时间："+summary["generated_at_utc"], "",
        "官方强制部署环境为银河麒麟 V11；SDK 为推荐项。下表是开发者持有公开合成标签的内部诊断，不能当作独立盲测或官方认证。", "",
        "| 官方指标 | 目标 | 当前内部值 | 分母 | 限制 |", "| --- | ---: | ---: | ---: | --- |"]
    descriptions = [
        ("preference_accuracy", "偏好提取准确率", "≥85%", "旧v2持久偏好槽位；非独立请求，未达目标"),
        ("knowledge_recall", "知识检索召回率", "≥85%", "v3正例Recall@3，少于50请求"),
        ("conflict_accuracy", "知识冲突处理正确率", "≥88%", "仅2个旧集案例，少于50请求"),
        ("retrieval_p95_ms", "检索响应延迟P95", "≤500ms", "HashEmbedding，进程内，合成主题模板"),
        ("sensitive_f1", "敏感信息识别F1", "≥90%", "50公开合成请求；请求级分类，非实体级F1")]
    for key, label, target, limit in descriptions:
        value = official["metrics"][key]
        formatted = f"{value:.3f}ms" if key == "retrieval_p95_ms" else f"{value:.2%}"
        lines.append(f"| {label} | {target} | {formatted} | {official['observation_counts'][key]} | {limit} |")
    lines += ["", "每项官方测试至少50次独立请求；当前偏好、召回、冲突的分母不足，不使用重复执行来凑数。偏好旧评测通过真实生命周期门槛，未降低授权或晋升要求来提高分数。", "",
        f"Windows完整工程检查通过：{summary['local_checks_passed']}；测试数：{summary['tests']}。原始记录见 round4/final_verification.json。",
        f"V11专用虚拟机已安装：{vm.get('installed', False)}；客户机回归通过：{vm.get('tests_passed', False)}。详情见 round4/kylin_vm.json（存在时）。",
        "虚拟机实测不能自行证明赛事认可；架构与虚拟化信息随报告保存。真实SDK/模型/向量服务连接仍以独立诊断为准。", "",
        "## 本轮实现", "",
        "- 官方五项指标、50请求门槛、V11严格识别；内部结果和正式就绪分离。",
        "- 独立实验目录、venv与虚拟磁盘；镜像校验；赛后先核查、再可恢复撤除。",
        "- Markdown/YAML四类记忆、显式授权、版本更新、索引预算和失败回滚。",
        "- 按需召回最多5条、超时及失败关闭、正文读取预算、歧义删除逐项确认。",
        "- 否定与多字段偏好修正；5会话50轮行动评测，检查15个实际文件。",
        "- 真实Embedding C ABI子进程适配；无库或错误输出时失败，不回退冒充接通。", "",
        "行动替身15/15仅是框架自检；真实KylinBot/模型、单样本容器与独立LLM Judge尚未完成。向量数据库C++服务接入也仍待完成。", "",
        "## 复现", "", "```bash", "python -S -m unittest discover -s tests -v",
        "python -S scripts/evaluate_official.py --output artifacts/runtime/official.json --size 10000",
        "python -S scripts/evaluate_official.py --output artifacts/runtime/official-required.json --require-official",
        "python -S scripts/check_kylin_native.py --output artifacts/runtime/native-sdk.json", "```", "",
        "第二条只生成内部诊断；带 --require-official 的命令在证据不足时退出2；SDK诊断未实际连接时退出2。", "",
        "当前材料为INCOMPLETE草案。独立盲测、授权案例、视频、赛事审核、报名与邮件回执仍需补齐。正式邮件不得由脚本自动发送。",
        "历史第三轮归档和原始报告保留；91.67%召回与100%无答案正确率是历史内部检索指标，不是官方两个85%均达成。", ""]
    report = "\n".join(lines)
    for name in ("测试报告.md", "28_第四轮验收报告.md"):
        (ROOT / "docs" / name).write_text(report, encoding="utf-8")
    print(json.dumps({"tests": summary["tests"], "local_checks_passed": summary["local_checks_passed"], "competition_ready": False}))


if __name__ == "__main__":
    generate()

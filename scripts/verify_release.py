"""Run reproducible local release checks without overstating external readiness."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from os_agent_memory.benchmark import run_scale_benchmark, write_benchmark_report
from os_agent_memory.compatibility import collect_compatibility_report, write_compatibility_report
from os_agent_memory.diagnostics import run_preflight
from os_agent_memory.evaluation import run_evaluation_suite
from os_agent_memory.experiments import evaluate_frozen, run_ablations


TEXT_SUFFIXES = {
    ".html", ".js", ".cjs",
    "",
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".jsonl",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SENSITIVE_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "service_token": re.compile(r"(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{12,})"),
    "email": re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    "cn_phone": re.compile(r"(?<![A-Za-z0-9])1[3-9]\d{9}(?![A-Za-z0-9])"),
    "cn_id": re.compile(r"(?<![A-Za-z0-9])\d{17}[0-9Xx](?![A-Za-z0-9])"),
}
SYNTHETIC_ALLOWLIST_PREFIXES = (
    "data/eval/",
    "data/samples/",
    "tests/",
)
SYNTHETIC_ALLOWLIST_FILES = {
    "artifacts/verification/evaluation_v1_final.json",
    "artifacts/verification/evaluation_v2_test_final.json",
    "docs/11_演示视频分镜与录制检查表.md",
    "docs/演示操作手册.md",
    "scripts/generate_eval_v2.py",
    "src/os_agent_memory/security.py",
    "scripts/verify_release.py",
}
SYNTHETIC_VALUES = {
    "13912345678", "demo@example.com", "person@example.com",
    "real.person@example.org", "sk-secret-value-123456789",
}
REQUIRED_LOCAL_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "deliverables/ppt/OS_Agent_记忆优化_答辩稿.pptx",
    "deliverables/doc/OS_Agent_记忆优化_技术方案与测试报告.docx",
    "docs/09_技术方案正文.md",
    "docs/10_PPT逐页讲稿与答辩问答.md",
    "docs/11_演示视频分镜与录制检查表.md",
    "docs/12_部署手册.md",
    "docs/13_API文档.md",
    "docs/14_可复现指南.md",
    "docs/15_源代码模块说明.md",
    "docs/16_原创性与隐私发布边界.md",
    "docs/测试报告.md",
    "scripts/build_submission.py",
    "scripts/archive_submission.py",
    "scripts/run_demo.ps1",
    "submission/submission_manifest.json",
)
EXTERNAL_BLOCKERS = (
    {"task": "I03", "item": "取得发榜单位真实 SDK、测试数据和指定系统版本"},
    {"task": "I04", "item": "真实银河麒麟系统上的 SDK、功能、性能和安装测试"},
    {"task": "H06", "item": "由独立评测者保管标签并执行盲测"},
    {"task": "J02", "item": "经授权、匿名化的真实应用案例"},
    {"task": "J07", "item": "人工录制并复核的最终演示视频"},
    {"task": "K05", "item": "发榜单位审核通过状态"},
    {"task": "K06", "item": "盖章报名表与系统信息一致性"},
    {"task": "K07", "item": "最终邮件和发送回执"},
)


def _run_command(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    start = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    duration_ms = (time.perf_counter() - start) * 1000
    combined = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    return {
        "command": command,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "duration_ms": round(duration_ms, 3),
        "output_tail": combined[-4000:],
    }


def discover_public_files(project_root: Path) -> list[Path]:
    command = [shutil.which("git") or "git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    try:
        completed = subprocess.run(command, cwd=project_root, capture_output=True, check=False)
    except OSError:
        completed = None
    if completed is not None and completed.returncode == 0:
        values = [value for value in completed.stdout.decode("utf-8", errors="replace").split("\0") if value]
        if values:
            return sorted(project_root / Path(value) for value in values)
    ignored_parts = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "venv",
    }
    ignored_prefixes = ("artifacts/runtime/", "case_studies/collected/", "case_studies/private/")
    return sorted(
        path
        for path in project_root.rglob("*")
        if path.is_file()
        and not ignored_parts.intersection(path.relative_to(project_root).parts)
        and not path.relative_to(project_root).as_posix().startswith(ignored_prefixes)
    )


def _is_approved_fixture(relative: str) -> bool:
    return relative in SYNTHETIC_ALLOWLIST_FILES or relative.startswith(SYNTHETIC_ALLOWLIST_PREFIXES)


def scan_sensitive_text(project_root: Path, files: Iterable[Path] | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    candidates = list(files) if files is not None else discover_public_files(project_root)
    unexpected: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = []
    scanned = 0
    skipped_binary = 0
    for path in candidates:
        try:
            relative = path.resolve().relative_to(project_root).as_posix()
        except ValueError:
            unexpected.append({"path": str(path), "line": None, "kind": "outside_project"})
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 2 * 1024 * 1024:
            skipped_binary += 1
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped_binary += 1
            continue
        scanned += 1
        approved = _is_approved_fixture(relative)
        for line_number, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in SENSITIVE_PATTERNS.items():
                matches = list(pattern.finditer(line))
                if not matches:
                    continue
                finding = {"path": relative, "line": line_number, "kind": kind}
                known_fixture = approved and all(match.group() in SYNTHETIC_VALUES for match in matches)
                (fixtures if known_fixture else unexpected).append(finding)
    return {
        "passed": not unexpected,
        "scanned_text_files": scanned,
        "skipped_binary_or_large_files": skipped_binary,
        "unexpected_findings": unexpected,
        "approved_synthetic_fixture_findings": fixtures,
        "policy": "报告只保存类型、路径和行号，不保存匹配到的敏感原文。",
    }


def check_materials(project_root: Path, required: Iterable[str] = REQUIRED_LOCAL_FILES) -> dict[str, Any]:
    rows = [{"path": item, "present": (project_root / item).is_file()} for item in required]
    missing = [item["path"] for item in rows if not item["present"]]
    return {"passed": not missing, "required": rows, "missing": missing}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _target_passed(result: dict[str, Any]) -> bool:
    targets = result.get("targets", {})
    return bool(targets) and all(bool(value) for value in targets.values())


def run_release_verification(
    *,
    project_root: Path,
    artifact_dir: Path,
    benchmark_sizes: Iterable[int] = (100, 1000, 5000, 10000),
    benchmark_rounds: int = 30,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    artifact_dir = artifact_dir.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    prior_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(project_root / "src") + (os.pathsep + prior_pythonpath if prior_pythonpath else "")

    compile_result = _run_command(
        [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"],
        cwd=project_root,
        env=environment,
    )
    test_result = _run_command(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=project_root,
        env=environment,
    )
    match = re.search(r"Ran (\d+) tests?", test_result["output_tail"])
    test_result["tests_run"] = int(match.group(1)) if match else None

    evaluation_v1 = run_evaluation_suite(project_root / "data/eval/office_memory_eval.json", top_k=3)
    evaluation_v2_test = run_evaluation_suite(
        project_root / "data/eval/office_memory_eval_v2.json",
        top_k=3,
        split="test",
    )
    _write_json(artifact_dir / "evaluation_v1_final.json", evaluation_v1)
    _write_json(artifact_dir / "evaluation_v2_test_final.json", evaluation_v2_test)
    suite_v3 = json.loads((project_root / "data/eval/office_memory_eval_v3.json").read_text(encoding="utf-8"))
    evaluation_v3 = evaluate_frozen(suite_v3)
    ablations = run_ablations(suite_v3)
    _write_json(artifact_dir / "evaluation_v3.json", evaluation_v3)
    _write_json(artifact_dir / "ablations.json", ablations)

    benchmark = run_scale_benchmark(benchmark_sizes, rounds=benchmark_rounds, top_k=5)
    write_benchmark_report(
        benchmark,
        json_path=artifact_dir / "performance_windows_dev.json",
        markdown_path=artifact_dir / "performance_windows_dev.md",
    )

    compatibility = collect_compatibility_report(artifact_dir)
    write_compatibility_report(
        compatibility,
        json_path=artifact_dir / "compatibility_windows_dev.json",
        markdown_path=artifact_dir / "compatibility_windows_dev.md",
    )
    preflight = run_preflight(
        workspace=artifact_dir,
        input_path=project_root / "data/samples/events.jsonl",
        suite_path=project_root / "data/eval/office_memory_eval_v2.json",
        host="127.0.0.1",
        port=0,
    )
    materials = check_materials(project_root)
    privacy = scan_sensitive_text(project_root)

    checks = {
        "compile": compile_result["passed"],
        "unit_tests": test_result["passed"],
        "evaluation_protocol": (
            evaluation_v3["configuration"]["selected_on"] == "dev"
            and evaluation_v3["configuration"]["threshold"] == evaluation_v3["test"]["threshold"]
            and all(not any(row.values()) for row in suite_v3["split_audit"].values())
        ),
        "benchmark_500ms": benchmark["all_meet_500ms"],
        "local_preflight": preflight["ready_for_local_demo"],
        "materials": materials["passed"],
        "privacy_scan": privacy["passed"],
    }
    local_passed = all(bool(value) for value in checks.values())
    competition_ready = bool(
        local_passed
        and compatibility["verdict"]["competition_environment_ready"]
        and len(EXTERNAL_BLOCKERS) == 0
    )
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "local_development_release_verification",
        "local_release_checks_passed": local_passed,
        "competition_submission_ready": competition_ready,
        "internal_quality_targets": {
            "positive_recall_at_3_ge_085": evaluation_v3["test"]["positive_recall_at_3"] >= .85,
            "no_answer_accuracy_ge_085": evaluation_v3["test"]["no_answer_accuracy"] >= .85,
        },
        "checks": checks,
        "compile": compile_result,
        "unit_tests": test_result,
        "evaluations": {
            "v3": evaluation_v3,
            "v1": {
                "suite": evaluation_v1["suite"],
                "split": evaluation_v1["split"],
                "metrics": evaluation_v1["metrics"],
                "targets": evaluation_v1["targets"],
            },
            "v2_test": {
                "suite": evaluation_v2_test["suite"],
                "split": evaluation_v2_test["split"],
                "metrics": evaluation_v2_test["metrics"],
                "targets": evaluation_v2_test["targets"],
            },
        },
        "benchmark": benchmark,
        "compatibility_verdict": compatibility["verdict"],
        "preflight": preflight,
        "materials": materials,
        "privacy_scan": privacy,
        "external_blockers": list(EXTERNAL_BLOCKERS),
        "interpretation": (
            "本地代码、合成评测和开发机性能检查通过，不等于真实银河麒麟、真实SDK、真实案例或赛事流程通过。"
        ),
    }


def write_verification_report(result: dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    _write_json(json_path, result)
    metrics = result["evaluations"]["v3"]["test"]
    largest = result["benchmark"]["results"][-1]
    lines = [
        "# 最终本地验收报告",
        "",
        f"生成时间（UTC）：{result['generated_at_utc']}",
        "",
        f"- 本地发布检查：{'通过' if result['local_release_checks_passed'] else '不通过'}",
        f"- 赛事完整提交就绪：{'是' if result['competition_submission_ready'] else '否'}",
        f"- 自动化测试：{result['unit_tests']['tests_run']} 项，{'通过' if result['unit_tests']['passed'] else '失败'}",
        f"- v3 test 正例 Recall@3：{metrics['positive_recall_at_3']:.4f}",
        f"- v3 test 无答案正确率：{metrics['no_answer_accuracy']:.4f}",
        f"- v3 test 平衡得分：{metrics['balanced_score']:.4f}",
        f"- 内部质量目标全部满足：{all(result['internal_quality_targets'].values())}",
        "- v1/v2 旧标签含单条低证据事件，门控后有目标未满足；保留原始结果，不能沿用旧版满分宣称。",
        f"- {largest['records']} 条开发机热查询 p99：{largest['hot_query_p99_ms']} ms",
        f"- 隐私扫描异常：{len(result['privacy_scan']['unexpected_findings'])} 项",
        "",
        "## 本地检查项",
        "",
        "| 检查 | 结果 |",
        "| --- | :---: |",
    ]
    for name, passed in result["checks"].items():
        lines.append(f"| `{name}` | {'通过' if passed else '失败'} |")
    lines.extend(["", "## 仍需人工/外部完成", ""])
    lines.extend(f"- {item['task']}：{item['item']}" for item in result["external_blockers"])
    lines.extend(
        [
            "",
            "> 本报告只证明当前开发机、本地 HashEmbedding 与仓库合成数据的检查结果。它不能作为真实麒麟环境、真实 SDK、独立盲测、真实用户案例或赛事流程回执。",
            "",
        ]
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, default=PROJECT_ROOT / "artifacts" / "verification")
    parser.add_argument("--sizes", default="100,1000,5000,10000")
    parser.add_argument("--rounds", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sizes = [int(value.strip()) for value in args.sizes.split(",") if value.strip()]
    result = run_release_verification(
        project_root=PROJECT_ROOT,
        artifact_dir=args.artifact_dir,
        benchmark_sizes=sizes,
        benchmark_rounds=args.rounds,
    )
    write_verification_report(
        result,
        json_path=args.artifact_dir / "final_verification.json",
        markdown_path=args.artifact_dir / "final_verification.md",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["local_release_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

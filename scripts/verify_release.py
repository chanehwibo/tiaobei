"""Run reproducible local release checks without overstating external readiness."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from zipfile import BadZipFile, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from os_agent_memory.benchmark import run_scale_benchmark, write_benchmark_report
from os_agent_memory.compatibility import collect_compatibility_report, write_compatibility_report
from os_agent_memory.diagnostics import run_preflight
from os_agent_memory.evaluation import run_evaluation_suite
from os_agent_memory.experiments import assess_decay_diagnostics, evaluate_frozen, run_ablations
from os_agent_memory.official_diagnostics import run_official_diagnostics
from os_agent_memory.request_contract import FROZEN_DATASET_SHA256, assess_frozen_requests
from os_agent_memory.request_evaluation import run_request_evaluation
from os_agent_memory.workload import run_service_workload
from scripts.check_deliverables import check_deliverables
from scripts.verify_kylin_guest import file_hashes


TEXT_SUFFIXES = {
    ".html", ".js", ".cjs", ".css", ".log", ".xml", ".rels", ".sh", ".sql", ".sha256",
    "",
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".jsonl",
    ".md",
    ".ps1",
    ".psm1",
    ".psd1",
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
    "01_项目报告与PPT/11_演示视频分镜与录制检查表.md",
    "artifacts/verification/evaluation_v1_final.json",
    "artifacts/verification/evaluation_v2_test_final.json",
    "docs/11_演示视频分镜与录制检查表.md",
    "docs/演示操作手册.md",
    "scripts/generate_eval_v2.py",
    "scripts/generate_request_suite.py",
    "src/os_agent_memory/security.py",
    "scripts/verify_release.py",
}
SYNTHETIC_VALUES = {
    "13912345678", "demo@example.com", "person@example.com",
    "real.person@example.org", "sk-secret-value-123456789",
    # Public synthetic checksum example used by request_regression_v1, not participant data.
    "11010519491231002X",
}
# These immutable older archives contain only the libraries' default author fields.
LEGACY_TEMPLATE_ARCHIVES = {
    "e109ef0d9f501cdd9e203c48821cf1e8c17a413304a14cf13677964b3a240227",
    "3eedda8e6416fa29be160fd1bacb9f3adc4c68ea955c5c8bcdf2e9ffb0ce0716",
    "631ecbf2045d1bd3a42d5205a564be72007b649cd8cdd4a106b0b16bfeba7e35",
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
    ".gitattributes",
    "data/eval/request_regression_v1.json",
    "docs/29_续作任务清单.md",
    "docs/30_逐请求评测与冻结基线.md",
    "docs/31_麒麟V11客户机实测.md",
    "docs/32_第五轮验收报告.md",
    "docs/33_第五轮交付复核.md",
    "scripts/check_deliverables.py",
    "scripts/generate_round5_materials.py",
)
EXTERNAL_BLOCKERS = (
    {"task": "X01", "item": "第三方保管标签的独立盲测、正式Agent/容器与独立Judge"},
    {"task": "X02", "item": "主办方认可已由参赛者确认；原始凭证、适用配置、运行资源及评分版本待归档核验"},
    {"task": "X03", "item": "经授权且匿名化的真实应用案例"},
    {"task": "X04", "item": "不超过7分钟的最终视频复核、平台审核及盖章报名表；既有DOCX分页已验收"},
    {"task": "X05", "item": "用户确认后的正式提交和邮件回执"},
)


def _run_command(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    start = time.perf_counter()
    failure = None
    try:
        completed = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, timeout=1200,
        )
        returncode = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        failure = type(exc).__name__
        returncode = None
        stdout, stderr = getattr(exc, "stdout", "") or "", getattr(exc, "stderr", "") or ""
    def as_text(value):
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    duration_ms = (time.perf_counter() - start) * 1000
    combined = "\n".join(part for part in (as_text(stdout).strip(), as_text(stderr).strip()) if part)
    return {
        "command": ["python" if value == sys.executable else value for value in command],
        "returncode": returncode,
        "passed": returncode == 0,
        "error_type": failure,
        "duration_ms": round(duration_ms, 3),
        "output_tail": combined.replace(str(cwd), "<project>").replace(sys.executable, "python")[-10000:],
    }


def discover_public_files(project_root: Path) -> list[Path]:
    git = [shutil.which("git") or "git", "-c", f"safe.directory={project_root.resolve().as_posix()}"]
    try:
        top = subprocess.run(git + ["rev-parse", "--show-toplevel"], cwd=project_root,
                             capture_output=True, check=False)
        own_repository = top.returncode == 0 and Path(top.stdout.decode("utf-8").strip()).resolve() == project_root.resolve()
        completed = subprocess.run(git + ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                                   cwd=project_root, capture_output=True, check=False) if own_repository else None
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
    relative = relative.rsplit("!", 1)[-1]
    if "/project/" in relative:
        relative = relative.split("/project/", 1)[-1]
    return relative in SYNTHETIC_ALLOWLIST_FILES or relative.startswith(SYNTHETIC_ALLOWLIST_PREFIXES)


def scan_sensitive_text(project_root: Path, files: Iterable[Path] | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    candidates = list(files) if files is not None else discover_public_files(project_root)
    unexpected: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = []
    scanned = 0
    office_scanned = 0
    archives_scanned = 0
    legacy_templates = []
    manual_review = []
    archive_budget = [128 * 1024 * 1024]

    def scan_lines(lines, relative, *, approved):
        for line_number, line in enumerate(lines, start=1):
            for kind, pattern in SENSITIVE_PATTERNS.items():
                matches = list(pattern.finditer(line))
                if matches:
                    finding = {"path": relative, "line": line_number, "kind": kind}
                    known = approved and all(match.group() in SYNTHETIC_VALUES for match in matches)
                    (fixtures if known else unexpected).append(finding)

    def xml_lines(payload):
        if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
            raise ValueError("XML declarations are not permitted")
        root = ET.fromstring(payload)
        text_tags = {
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t",
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}delText",
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}instrText",
            "{http://schemas.openxmlformats.org/drawingml/2006/main}t",
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t",
        }
        paragraph_tags = {tag.rsplit("}", 1)[0] + "}p" for tag in text_tags}
        paragraph_tags.add("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si")
        lines = []
        for node in root.iter():
            if node.tag in paragraph_tags:
                # Office may split one credential across differently formatted text runs.
                lines.append("".join(child.text or "" for child in node.iter() if child.tag in text_tags))
            if node.text:
                lines.append(node.text)
            lines.extend(node.attrib.values())
        return root, lines

    def scan_stream(handle, relative):
        nonlocal scanned
        header = handle.read(4)
        handle.seek(0)
        encoding = ("utf-32" if header.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"))
                    else "utf-16" if header.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        with io.TextIOWrapper(handle, encoding=encoding) as stream:
            scan_lines(stream, relative, approved=_is_approved_fixture(relative))
        scanned += 1

    def scan_archive(source, relative, *, office, depth=0, legacy_metadata=False):
        nonlocal office_scanned, archives_scanned
        try:
            with ZipFile(source) as archive:
                members = archive.infolist()
                total = sum(item.file_size for item in members)
                archive_budget[0] -= total
                if depth > 3 or len(members) > 10000 or archive_budget[0] < 0:
                    raise ValueError("archive exceeds scan limits")
                if len({item.filename for item in members}) != len(members):
                    raise ValueError("duplicate archive member")
                for member in members:
                    name = relative + "!" + member.filename
                    member_path = PurePosixPath(member.filename)
                    if (member_path.is_absolute() or ".." in member_path.parts or ":" in member.filename
                            or "\\" in member.filename or stat.S_ISLNK(member.external_attr >> 16)):
                        raise ValueError("unsafe archive member")
                    if member.is_dir():
                        continue
                    suffix = member_path.suffix.lower()
                    if office and member.filename.lower().endswith((".xml", ".rels")):
                        root, lines = xml_lines(archive.read(member))
                        scan_lines(lines, name, approved=False)
                        if member.filename == "docProps/core.xml":
                            for node in root:
                                if node.tag.rsplit("}", 1)[-1] in {"creator", "lastModifiedBy"} and (node.text or "").strip():
                                    finding = {"path": name, "line": None, "kind": "author_metadata"}
                                    known = legacy_metadata and node.text in {"python-docx", "Steve Canny"}
                                    (legacy_templates if known else unexpected).append(finding)
                        if member.filename.lower().endswith(".rels") and any(node.get("TargetMode") == "External" for node in root):
                            unexpected.append({"path": name, "line": None, "kind": "external_document_reference"})
                    elif office and ("/embeddings/" in member.filename or member.filename.lower().endswith("vbaproject.bin")):
                        unexpected.append({"path": name, "line": None, "kind": "embedded_document_or_macro"})
                    elif not office and suffix in {".zip", ".docx", ".pptx", ".xlsx", ".docm", ".pptm", ".xlsm"}:
                        scan_archive(io.BytesIO(archive.read(member)), name, office=suffix != ".zip",
                                     depth=depth + 1, legacy_metadata=legacy_metadata)
                    elif not office and suffix in TEXT_SUFFIXES:
                        try:
                            with archive.open(member) as handle:
                                scan_stream(handle, name)
                        except UnicodeDecodeError:
                            unexpected.append({"path": name, "line": None, "kind": "unreadable_text"})
                    else:
                        manual_review.append({"path": name, "reason": "non_text_office_member" if office else "binary_media_not_ocr_scanned"})
                    if not office and (suffix in {".key", ".pem", ".sqlite", ".db"}
                                       or member_path.name.lower().startswith(".env")
                                       or {"private", "collected"} & set(member_path.parts)):
                        unexpected.append({"path": name, "line": None, "kind": "forbidden_public_artifact"})
            if office:
                office_scanned += 1
            else:
                archives_scanned += 1
        except (OSError, BadZipFile, ET.ParseError, RuntimeError, ValueError):
            unexpected.append({"path": relative, "line": None,
                               "kind": "unscannable_office_document" if office else "unscannable_archive"})

    for path in candidates:
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            unexpected.append({"path": path.name, "line": None, "kind": "linked_public_artifact"})
            continue
        try:
            relative = path.resolve().relative_to(project_root).as_posix()
        except ValueError:
            unexpected.append({"path": path.name, "line": None, "kind": "outside_project"})
            continue
        suffix = path.suffix.lower()
        if (suffix in {".key", ".pem", ".sqlite", ".db"} or path.name.lower().startswith(".env")
                or relative.startswith(("case_studies/private/", "case_studies/collected/"))):
            unexpected.append({"path": relative, "line": None, "kind": "forbidden_public_artifact"})
        if suffix in {".zip", ".docx", ".pptx", ".xlsx", ".docm", ".pptm", ".xlsm"}:
            legacy = False
            if suffix == ".zip":
                try:
                    digest = hashlib.sha256()
                    with path.open("rb") as handle:
                        for block in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(block)
                    legacy = digest.hexdigest() in LEGACY_TEMPLATE_ARCHIVES
                except OSError:
                    pass
            scan_archive(path, relative, office=suffix != ".zip", legacy_metadata=legacy)
            continue
        if suffix not in TEXT_SUFFIXES:
            manual_review.append({"path": relative, "reason": "binary_media_not_ocr_scanned"})
            continue
        try:
            with path.open("rb") as handle:
                scan_stream(handle, relative)
        except (OSError, UnicodeDecodeError):
            unexpected.append({"path": relative, "line": None, "kind": "unreadable_text"})
    return {
        "passed": not unexpected,
        "scanned_text_files": scanned,
        "scanned_office_documents": office_scanned,
        "scanned_zip_archives": archives_scanned,
        "skipped_binary_or_large_files": len(manual_review),
        "manual_review_required": manual_review,
        "unexpected_findings": unexpected,
        "approved_synthetic_fixture_findings": fixtures,
        "approved_legacy_template_metadata": legacy_templates,
        "policy": "文本逐行扫描，无2MiB跳过；ZIP递归扫描有128MiB及层数上限，超限失败；Office扫描XML/元数据/拆分文本。只记录位置和类型，不记录敏感原文。媒体无OCR，须单独人工复核。",
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
    benchmark_sizes = tuple(benchmark_sizes)
    if not benchmark_sizes or min(benchmark_sizes) < 1 or benchmark_rounds < 1:
        raise ValueError("benchmark sizes and rounds must be positive")
    if artifact_dir.exists() and any(artifact_dir.iterdir()):
        raise ValueError("refusing to overwrite an existing verification run; use a fresh artifact directory")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    source_snapshot = file_hashes(project_root)
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    prior_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(project_root / "src") + (os.pathsep + prior_pythonpath if prior_pythonpath else "")

    compile_result = _run_command(
        [sys.executable, "-X", "utf8", "-S", "-m", "compileall", "-q", "src", "scripts", "tests"],
        cwd=project_root,
        env=environment,
    )
    test_result = _run_command(
        [sys.executable, "-X", "utf8", "-S", "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=project_root,
        env=environment,
    )
    match = re.search(r"Ran (\d+) tests?", test_result["output_tail"])
    test_result["tests_run"] = int(match.group(1)) if match else None
    source_check = _run_command(
        [sys.executable, "-X", "utf8", "-S", "scripts/check_source.py"], cwd=project_root, env=environment,
    )
    requests = run_request_evaluation(project_root, size=10000)
    request_gate = assess_frozen_requests(requests)
    requests["release_gate"] = request_gate
    _write_json(artifact_dir / "requests.json", requests)

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
    ablations["diagnostic_gate"] = assess_decay_diagnostics(ablations)
    _write_json(artifact_dir / "evaluation_v3.json", evaluation_v3)
    _write_json(artifact_dir / "ablations.json", ablations)
    official = run_official_diagnostics(project_root, size=max(1000, max(benchmark_sizes)))
    _write_json(artifact_dir / "official_diagnostics.json", official)

    benchmark = run_scale_benchmark(benchmark_sizes, rounds=benchmark_rounds, top_k=5)
    write_benchmark_report(
        benchmark,
        json_path=artifact_dir / "performance_windows_dev.json",
        markdown_path=artifact_dir / "performance_windows_dev.md",
    )
    service_workload = run_service_workload((100, 1000), rounds=max(3, benchmark_rounds))
    _write_json(artifact_dir / "service_workload.json", service_workload)
    with tempfile.TemporaryDirectory(prefix=".action-workspace-", dir=artifact_dir) as workspace:
        action_framework = _run_command(
            [sys.executable, "-X", "utf8", "-S", "scripts/evaluate_actions.py",
             "--workspace", workspace, "--output", str(artifact_dir / "actions.json")],
            cwd=project_root, env=environment,
        )
    action_readiness = _run_command(
        [sys.executable, "-X", "utf8", "-S", "scripts/check_action_readiness.py",
         "--output", str(artifact_dir / "action-readiness.json")],
        cwd=project_root, env=environment,
    )

    compatibility = collect_compatibility_report(artifact_dir)
    compatibility["resources"]["filesystem"]["path"] = "<artifact_dir>"
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
    editable_materials = check_deliverables(project_root)
    privacy = scan_sensitive_text(project_root)

    checks = {
        "compile": compile_result["passed"],
        "unit_tests": test_result["passed"],
        "source_syntax_and_privacy": source_check["passed"],
        "frozen_request_gate": request_gate["passed"],
        "frozen_dataset_bytes": hashlib.sha256(
            (project_root / "data/eval/request_regression_v1.json").read_bytes()
        ).hexdigest() == FROZEN_DATASET_SHA256,
        "source_unchanged_during_checks": source_snapshot == file_hashes(project_root),
        "request_source_snapshot": requests["source_sha256"] == {
            key: value for key, value in source_snapshot["raw_sha256"].items()
            if key.startswith("src/") and key.endswith(".py")
        },
        "evaluation_protocol": (
            evaluation_v3["configuration"]["selected_on"] == "dev"
            and evaluation_v3["configuration"]["threshold"] == evaluation_v3["test"]["threshold"]
            and all(not any(row.values()) for row in suite_v3["split_audit"].values())
        ),
        "internal_quality_85": all(evaluation_v3["quality_targets"].values()),
        "benchmark_500ms": benchmark["all_meet_500ms"],
        "service_workload_integrity": service_workload["integrity_passed"],
        "decay_diagnostics": ablations["diagnostic_gate"]["passed"],
        "action_framework": action_framework["passed"],
        "local_preflight": preflight["ready_for_local_demo"],
        "materials": materials["passed"],
        "editable_materials": editable_materials["passed"],
        "privacy_scan": privacy["passed"],
    }
    local_passed = all(bool(value) for value in checks.values())
    competition_ready = bool(
        local_passed
        and compatibility["verdict"]["competition_environment_ready"]
        and official["official_validation_ready"]
        and len(EXTERNAL_BLOCKERS) == 0
    )
    result = {
        "schema_version": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "local_development_release_verification",
        "local_release_checks_passed": local_passed,
        "competition_submission_ready": competition_ready,
        "internal_quality_targets": evaluation_v3["quality_targets"],
        "official_diagnostics": official,
        "checks": checks,
        "compile": compile_result,
        "source_check": source_check,
        "file_hashes": source_snapshot,
        "unit_tests": test_result,
        "request_gate": request_gate,
        "request_metrics": requests["metrics"],
        "request_counts": requests["observation_counts"],
        "request_report": "requests.json",
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
        "service_workload": service_workload,
        "decay_diagnostic_gate": ablations["diagnostic_gate"],
        "action_framework": action_framework,
        "action_readiness": action_readiness,
        "action_readiness_is_external_diagnostic": True,
        "compatibility_verdict": compatibility["verdict"],
        "preflight": preflight,
        "materials": materials,
        "editable_materials": editable_materials,
        "privacy_scan": privacy,
        "external_blockers": list(EXTERNAL_BLOCKERS),
        "interpretation": (
            "本报告执行冻结逐请求五项硬门槛；当前运行环境见requests.json。V11客户机另有独立报告，"
            "内部回归不等于原生模型、第三方盲测、真实Agent/案例或赛事流程通过。"
        ),
    }
    # Environment paths are not part of the measured data or source identity.
    def public_paths(value):
        if isinstance(value, dict):
            return {key: public_paths(item) for key, item in value.items()}
        if isinstance(value, list):
            return [public_paths(item) for item in value]
        if isinstance(value, str):
            return value.replace(str(project_root), "<project>").replace(sys.executable, "python")
        return value
    return public_paths(result)


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
        f"- 冻结逐请求五项发布门槛：{result['request_gate']['passed']}",
        f"- 五项实测数值：{result['request_metrics']}",
        f"- 请求分母：{result['request_counts']}；原始逐条记录见 requests.json",
        "- 五项数值、冻结字节、固定配置、分母一致性和附加安全检查均参与退出码，不能仅凭报告布尔值通过。",
        f"- v3 test 正例 Recall@3：{metrics['positive_recall_at_3']:.4f}",
        f"- v3 test 无答案正确率：{metrics['no_answer_accuracy']:.4f}",
        f"- v3 test 平衡得分：{metrics['balanced_score']:.4f}",
        f"- 历史内部检索门槛满足：{all(result['internal_quality_targets'].values())}（不是官方两个85%指标）",
        f"- 官方五项指标证据就绪：{result['official_diagnostics']['official_validation_ready']}",
        f"- 官方口径内部诊断：{result['official_diagnostics']['metrics']}",
        f"- 分母及单位：{result['official_diagnostics']['observation_counts']}；详见 official_diagnostics.json",
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
    parser.add_argument("--artifact-dir", type=Path, default=PROJECT_ROOT / "artifacts" / "runtime" / "release")
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

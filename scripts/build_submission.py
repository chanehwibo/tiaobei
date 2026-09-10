"""Build a privacy-bounded competition submission staging directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.material_status import INITIAL_STATUS
except ModuleNotFoundError:
    from material_status import INITIAL_STATUS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "submission" / "submission_manifest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "dist" / "competition_submission_draft"
BLOCKED_SUFFIXES = {".db", ".key", ".pem", ".pyc", ".pyo", ".sqlite"}
BLOCKED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "collected",
    "private",
    "runtime",
    "venv",
}


class PackagingError(RuntimeError):
    """Raised when a package would be unsafe, ambiguous, or incomplete."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute() or path.drive or not path.parts or ".." in path.parts or ":" in path_text:
        raise PackagingError(f"清单路径必须是项目内相对路径: {path_text}")
    return path


def _is_blocked_public_file(path: Path) -> bool:
    lowered = {part.lower() for part in path.parts}
    generated_metadata = any(part.endswith(".egg-info") for part in lowered)
    generated_report = path.name.lower().endswith("_report.json")
    return bool(
        lowered & BLOCKED_PARTS
        or path.suffix.lower() in BLOCKED_SUFFIXES
        or generated_metadata
        or generated_report
        or path.name.lower().startswith(".env")
        or ".sqlite-" in path.name.lower()
    )


def _assert_safe_public_file(path: Path) -> None:
    if _is_blocked_public_file(path):
        raise PackagingError(f"公开打包清单包含禁止路径或后缀: {path}")


def _assert_local_source(project_root: Path, source: Path) -> None:
    if not source.resolve().is_relative_to(project_root):
        raise PackagingError(f"公开来源越出项目目录: {source.name}")
    for node in (source, *source.parents):
        if node == project_root:
            break
        if node.is_symlink() or (hasattr(node, "is_junction") and node.is_junction()):
            raise PackagingError(f"公开来源包含链接: {source.name}")


def _copy_public_file(
    project_root: Path, source_text: str, target_root: Path, *, preserve_path: bool = False
) -> Path:
    relative = _safe_relative(source_text)
    _assert_safe_public_file(relative)
    source = project_root / relative
    _assert_local_source(project_root, source)
    if not source.is_file():
        raise PackagingError(f"清单中的公开文件不存在: {relative.as_posix()}")
    target = target_root / (relative if preserve_path else relative.name)
    if target.exists():
        raise PackagingError(f"清单目标重复: {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _copy_public_tree(project_root: Path, source_text: str, target_root: Path) -> list[Path]:
    relative = _safe_relative(source_text)
    _assert_safe_public_file(relative)
    source_root = project_root / relative
    _assert_local_source(project_root, source_root)
    if not source_root.is_dir():
        raise PackagingError(f"清单中的公开目录不存在: {relative.as_posix()}")
    copied: list[Path] = []
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        inner = source.relative_to(source_root)
        if _is_blocked_public_file(inner):
            continue
        _assert_local_source(project_root, source)
        target = target_root / relative / inner
        if target.exists():
            raise PackagingError(f"清单目标重复: {target.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagingError(f"无法读取打包清单 {path}: {exc}") from exc
    if manifest.get("schema_version") != 1:
        raise PackagingError("仅支持 schema_version=1 的打包清单")
    return manifest


def _validate_output(project_root: Path, output: Path) -> None:
    resolved_root = project_root.resolve()
    resolved_output = output.resolve()
    if resolved_output in {resolved_root, resolved_root.parent, Path(resolved_output.anchor)}:
        raise PackagingError("输出目录不能是项目目录、其父目录或磁盘根目录")
    if output.exists():
        raise PackagingError(f"输出目录已存在，拒绝覆盖: {output}")


def build_submission(
    *,
    project_root: Path,
    output: Path,
    manifest_path: Path,
    external_files: dict[str, Path | None],
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    """Build one immutable-by-convention staging directory from an allowlist."""

    project_root = project_root.resolve()
    output = output.resolve()
    _validate_output(project_root, output)
    manifest = _load_manifest(manifest_path)
    source_section = manifest["source_section"]
    sections = [*manifest["public_sections"], source_section, *manifest["external_inputs"]]
    for section in sections:
        _safe_relative(section["target"])
    for source_text in source_section["trees"]:
        source_tree = (project_root / _safe_relative(source_text)).resolve()
        if output.is_relative_to(source_tree):
            raise PackagingError("输出目录不能位于被打包的源码目录内")

    missing: list[dict[str, str]] = []
    supplied: dict[str, Path] = {}
    for item in manifest["external_inputs"]:
        value = external_files.get(item["key"])
        if value is None:
            missing.append({"key": item["key"], "label": item["label"]})
            continue
        resolved = value.expanduser().resolve()
        if not resolved.is_file():
            raise PackagingError(f"外部材料不存在或不是文件: {resolved}")
        supplied[item["key"]] = resolved

    if missing and not allow_incomplete:
        labels = "、".join(item["label"] for item in missing)
        raise PackagingError(f"缺少正式提交所需外部材料: {labels}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.building-", dir=output.parent)).resolve()

    copied: list[Path] = []
    try:
        for section in manifest["public_sections"]:
            target_root = temporary / section["target"]
            for source_text in section["files"]:
                copied.append(_copy_public_file(project_root, source_text, target_root))

        source_root = temporary / source_section["target"]
        mirrored_files = source_section["files"] + source_section.get("docs", [])
        mirrored_files += [source for section in manifest["public_sections"] for source in section["files"]]
        for source_text in sorted(set(mirrored_files)):
            copied.append(_copy_public_file(project_root, source_text, source_root, preserve_path=True))
        for source_text in source_section["trees"]:
            copied.extend(_copy_public_tree(project_root, source_text, source_root))

        for item in manifest["external_inputs"]:
            source = supplied.get(item["key"])
            if source is None:
                continue
            target = temporary / item["target"] / source.name
            if target.exists():
                raise PackagingError(f"外部材料文件名重复，请分别命名: {source.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target)

        status = "incomplete_draft" if missing else "ready_for_manual_review"
        status_lines = [
            "# 提交包状态",
            "",
            f"- 状态：**{INITIAL_STATUS}**",
            "- 说明：该状态由本地清单校验产生，不代表平台审核通过或邮件发送成功。",
        ]
        if missing:
            status_lines.extend(["", "## 缺失的外部材料", ""])
            status_lines.extend(f"- {item['label']} (`{item['key']}`)" for item in missing)
            status_lines.extend(["", "本目录供初版技术审阅，禁止改名或宣称为完整正式包。"])
        status_path = temporary / "PACKAGE_STATUS.md"
        status_path.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
        copied.append(status_path)

        report_path = temporary / "build_report.json"
        report = {
            "schema_version": 1,
            "package_name": manifest["package_name"],
            "status": status,
            "display_status": INITIAL_STATUS,
            "competition_ready": False,
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "missing_external": missing,
            "files": [],
        }
        for path in sorted(copied):
            report["files"].append(
                {
                    "path": path.relative_to(temporary).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.rename(output)
        return report
    except Exception:
        if temporary.exists() and temporary.parent == output.parent and temporary != output:
            shutil.rmtree(temporary)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path,
                        help="Explicit manifest for historical rebuilds; defaults to the current review manifest")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--registration-form", type=Path)
    parser.add_argument("--real-case", type=Path)
    parser.add_argument("--kylin-report", type=Path)
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="生成标明已完成初版、待赛事验收的技术审阅包；保留外部缺项",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    external = {
        "video": args.video,
        "registration_form": args.registration_form,
        "real_case": args.real_case,
        "kylin_report": args.kylin_report,
    }
    try:
        if args.manifest is None:
            sys.path.insert(0, str(PROJECT_ROOT))
            from scripts.build_review_submission import MANIFEST
            from scripts.generate_review_materials import OUTPUT, verify_outputs
            if not verify_outputs(PROJECT_ROOT, PROJECT_ROOT / OUTPUT)["passed"]:
                raise PackagingError("当前材料与源码校验失败，请先重生成审阅材料")
            args.manifest = PROJECT_ROOT / MANIFEST
        report = build_submission(
            project_root=PROJECT_ROOT,
            output=args.output,
            manifest_path=args.manifest,
            external_files=external,
            allow_incomplete=args.allow_incomplete,
        )
    except PackagingError as exc:
        print(f"打包失败: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

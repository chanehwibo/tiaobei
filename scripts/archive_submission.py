"""Create and verify a SHA-256-indexed read-only submission archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.material_status import ARCHIVE_REVIEW_MARKER, INITIAL_STATUS
except ModuleNotFoundError:
    from material_status import ARCHIVE_REVIEW_MARKER, INITIAL_STATUS


FIXED_ZIP_TIME = (2026, 9, 5, 0, 0, 0)


class ArchiveError(RuntimeError):
    """Raised when an archive cannot be created without ambiguity."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_status(staging: Path) -> dict[str, Any]:
    report_path = staging / "build_report.json"
    status_path = staging / "PACKAGE_STATUS.md"
    if not report_path.is_file() or not status_path.is_file():
        raise ArchiveError("暂存目录缺少 build_report.json 或 PACKAGE_STATUS.md")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"无法读取暂存构建报告: {exc}") from exc
    if report.get("status") not in {"incomplete_draft", "ready_for_manual_review"}:
        raise ArchiveError(f"未知暂存状态: {report.get('status')}")
    return report


def _collect_files(staging: Path) -> list[Path]:
    files: list[Path] = []
    for path in staging.rglob("*"):
        if path.is_symlink():
            raise ArchiveError(f"归档拒绝符号链接: {path}")
        if path.is_file():
            resolved = path.resolve()
            try:
                resolved.relative_to(staging)
            except ValueError as exc:
                raise ArchiveError(f"文件越出暂存目录: {path}") from exc
            files.append(path)
    if not files:
        raise ArchiveError("暂存目录中没有可归档文件")
    return sorted(files, key=lambda item: item.relative_to(staging).as_posix())


def _content_manifest(staging: Path, files: list[Path]) -> tuple[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    lines: list[str] = []
    for path in files:
        relative = path.relative_to(staging).as_posix()
        digest = _sha256_file(path)
        size = path.stat().st_size
        rows.append({"path": relative, "bytes": size, "sha256": digest})
        lines.append(f"{digest}  {relative}")
    return "\n".join(lines) + "\n", rows


def _write_zip(archive: Path, staging: Path, files: list[Path], manifest_text: str) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            relative = path.relative_to(staging).as_posix()
            info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("SHA256SUMS.txt", date_time=FIXED_ZIP_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        bundle.writestr(info, manifest_text.encode("utf-8"))


def _verify_zip(archive: Path, expected: list[dict[str, Any]], manifest_text: str) -> None:
    with zipfile.ZipFile(archive, "r") as bundle:
        names = set(bundle.namelist())
        expected_names = {row["path"] for row in expected} | {"SHA256SUMS.txt"}
        if names != expected_names or len(bundle.namelist()) != len(expected_names):
            raise ArchiveError("ZIP 文件列表与暂存清单不一致")
        for row in expected:
            if _sha256_bytes(bundle.read(row["path"])) != row["sha256"]:
                raise ArchiveError(f"ZIP 内文件哈希不一致: {row['path']}")
        if bundle.read("SHA256SUMS.txt").decode("utf-8") != manifest_text:
            raise ArchiveError("ZIP 内 SHA256SUMS.txt 与外部清单不一致")
        bad_member = bundle.testzip()
        if bad_member is not None:
            raise ArchiveError(f"ZIP CRC 校验失败: {bad_member}")


def _verify_staging_report(rows: list[dict[str, Any]], report: dict[str, Any]) -> None:
    actual = {row["path"]: row for row in rows if row["path"] != "build_report.json"}
    declared_rows = report.get("files", [])
    if not isinstance(declared_rows, list) or not declared_rows:
        raise ArchiveError("构建报告中没有逐文件清单")
    declared: dict[str, dict[str, Any]] = {}
    for row in declared_rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ArchiveError("构建清单条目格式无效")
        if row["path"] in declared:
            raise ArchiveError("构建清单包含重复文件")
        declared[row["path"]] = row
    if set(actual) != set(declared):
        raise ArchiveError("暂存文件列表与构建清单不一致，请重新打包")
    for name, row in actual.items():
        expected = declared[name]
        if row["sha256"] != expected.get("sha256") or row["bytes"] != expected.get("bytes"):
            raise ArchiveError(f"暂存文件已改变，请重新打包: {name}")


def create_archive(*, staging: Path, archive: Path, allow_incomplete: bool = False) -> dict[str, Any]:
    staging = staging.resolve()
    archive = archive.resolve()
    if not staging.is_dir():
        raise ArchiveError(f"暂存目录不存在: {staging}")
    if archive.exists():
        raise ArchiveError(f"归档已存在，拒绝覆盖: {archive}")
    if archive.is_relative_to(staging):
        raise ArchiveError("归档输出必须位于暂存目录之外")
    report = _load_status(staging)
    incomplete = report["status"] == "incomplete_draft"
    if incomplete and not allow_incomplete:
        raise ArchiveError("暂存包不完整；如仅归档开发机草案，必须显式传入 --allow-incomplete")
    if incomplete and ARCHIVE_REVIEW_MARKER not in archive.name and "INCOMPLETE" not in archive.name.upper():
        raise ArchiveError("初版技术审阅包的归档文件名必须包含 待赛事验收")

    files = _collect_files(staging)
    manifest_text, rows = _content_manifest(staging, files)
    _verify_staging_report(rows, report)
    content_manifest = archive.with_name(f"{archive.stem}_CONTENTS_SHA256.txt")
    archive_digest_file = archive.with_name(f"{archive.name}.sha256")
    archive_report = archive.with_name(f"{archive.stem}_archive_report.json")
    for output in (content_manifest, archive_digest_file, archive_report):
        if output.exists():
            raise ArchiveError(f"归档伴随文件已存在，拒绝覆盖: {output}")

    _write_zip(archive, staging, files, manifest_text)
    _verify_zip(archive, rows, manifest_text)
    archive_sha256 = _sha256_file(archive)
    content_manifest.write_text(manifest_text, encoding="utf-8")
    archive_digest_file.write_text(f"{archive_sha256}  {archive.name}\n", encoding="utf-8")

    os.chmod(archive, stat.S_IREAD)
    read_only = not bool(archive.stat().st_mode & stat.S_IWRITE)
    result = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package_status": report["status"],
        "display_status": INITIAL_STATUS,
        "competition_ready": False,
        "archive": archive.name,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_sha256,
        "archive_read_only": read_only,
        "content_file_count": len(rows),
        "content_bytes": sum(row["bytes"] for row in rows),
        "content_manifest": content_manifest.name,
        "archive_digest_file": archive_digest_file.name,
        "zip_integrity_verified": True,
        "build_manifest_verified": True,
        "missing_external": report.get("missing_external", []),
        "warning": (
            "已完成初版，待赛事验收；外部缺项另列，不得作为赛事验收通过证明。"
            if incomplete
            else "已通过本地归档检查，仍需负责人核对赛事文件名、格式、大小和平台/邮件状态。"
        ),
    }
    archive_report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = create_archive(
            staging=args.staging,
            archive=args.archive,
            allow_incomplete=args.allow_incomplete,
        )
    except ArchiveError as exc:
        print(f"归档失败: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

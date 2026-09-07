from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .embeddings import KylinEmbeddingConfig, check_kylin_embedding
from .official_contract import environment_identity


def _os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def _memory_bytes() -> int | None:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical)
        return None
    page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else None
    page_count = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else None
    return int(page_size * page_count) if page_size and page_count else None


def _sqlite_capabilities() -> dict[str, Any]:
    result: dict[str, Any] = {
        "version": sqlite3.sqlite_version,
        "threadsafety": sqlite3.threadsafety,
        "fts5": False,
        "json1": False,
        "errors": [],
    }
    connection = sqlite3.connect(":memory:")
    try:
        try:
            connection.execute("CREATE VIRTUAL TABLE fts_probe USING fts5(content)")
            result["fts5"] = True
        except sqlite3.Error as exc:
            result["errors"].append(f"fts5: {exc}")
        try:
            result["json1"] = connection.execute("SELECT json_valid('{\"ok\":true}')").fetchone()[0] == 1
        except sqlite3.Error as exc:
            result["errors"].append(f"json1: {exc}")
    finally:
        connection.close()
    return result


def _workspace_capabilities(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    writable = False
    error: str | None = None
    try:
        resolved.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="memory-probe-", dir=resolved, delete=True):
            writable = True
    except OSError as exc:
        error = str(exc)
    usage = shutil.disk_usage(resolved if resolved.exists() else resolved.parent)
    return {
        "path": str(resolved),
        "writable": writable,
        "free_disk_gb": round(usage.free / 1024**3, 3),
        "error": error,
    }


def collect_compatibility_report(
    workspace: str | Path,
    *,
    sdk_config: KylinEmbeddingConfig | dict[str, Any] | None = None,
) -> dict[str, Any]:
    release = _os_release()
    identity = " ".join(
        [
            platform.system(),
            platform.platform(),
            release.get("ID", ""),
            release.get("NAME", ""),
            release.get("PRETTY_NAME", ""),
        ]
    ).lower()
    verified_identity = environment_identity(platform.system(), release)
    is_kylin = verified_identity["is_galaxy_kylin"]
    machine = platform.machine()
    architecture_supported = machine.lower() in {
        "amd64",
        "x86_64",
        "arm64",
        "aarch64",
        "loongarch64",
    }
    sqlite = _sqlite_capabilities()
    filesystem = _workspace_capabilities(Path(workspace))
    python_supported = sys.version_info >= (3, 10)
    sdk = check_kylin_embedding(sdk_config) if sdk_config is not None else {
        "status": "not_checked",
        "compatible": False,
        "reason": "No real SDK configuration supplied.",
    }
    local_ready = bool(
        python_supported
        and architecture_supported
        and filesystem["writable"]
        and sqlite["fts5"]
    )
    competition_ready = bool(local_ready and verified_identity["is_required_v11"])
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "operating_system": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "platform": platform.platform(),
            "os_release": release,
            "is_galaxy_kylin": is_kylin,
            "is_required_v11": verified_identity["is_required_v11"],
        },
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "python_supported": python_supported,
            "machine": machine,
            "architecture_supported": architecture_supported,
        },
        "resources": {
            "logical_cpu_count": os.cpu_count(),
            "physical_memory_gb": round(_memory_bytes() / 1024**3, 3) if _memory_bytes() else None,
            "filesystem": filesystem,
        },
        "sqlite": sqlite,
        "embedding_sdk": sdk,
        "verdict": {
            "local_runtime_ready": local_ready,
            "real_galaxy_kylin_verified": is_kylin,
            "required_v11_verified": verified_identity["is_required_v11"],
            "real_embedding_sdk_verified": bool(sdk.get("compatible")),
            "sdk_is_recommended_not_mandatory": True,
            "competition_environment_ready": competition_ready,
        },
    }


def write_compatibility_report(
    report: dict[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    os_info = report["operating_system"]
    runtime = report["runtime"]
    resources = report["resources"]
    sqlite = report["sqlite"]
    sdk = report["embedding_sdk"]
    verdict = report["verdict"]
    lines = [
        "# 运行环境兼容性自检报告",
        "",
        f"生成时间（UTC）：{report['generated_at_utc']}",
        "",
        "| 检查项 | 结果 |",
        "| --- | --- |",
        f"| 操作系统 | {os_info['platform']} |",
        f"| 银河麒麟识别 | {'是' if os_info['is_galaxy_kylin'] else '否'} |",
        f"| 强制 V11 版本 | {os_info.get('is_required_v11', False)} |",
        f"| CPU 架构 | {runtime['machine']} |",
        f"| Python | {runtime['python']} |",
        f"| SQLite | {sqlite['version']} |",
        f"| FTS5 / JSON1 | {sqlite['fts5']} / {sqlite['json1']} |",
        f"| 逻辑 CPU | {resources['logical_cpu_count']} |",
        f"| 物理内存 GB | {resources['physical_memory_gb']} |",
        f"| 可用磁盘 GB | {resources['filesystem']['free_disk_gb']} |",
        f"| 工作目录可写 | {resources['filesystem']['writable']} |",
        f"| SDK 状态 | {sdk['status']} |",
        "",
        "## 分层判定",
        "",
        f"- 开发运行条件：{'通过' if verdict['local_runtime_ready'] else '不通过'}",
        f"- 真实银河麒麟环境：{'已验证' if verdict['real_galaxy_kylin_verified'] else '未验证'}",
        f"- 真实 embedding SDK：{'已验证' if verdict['real_embedding_sdk_verified'] else '未验证'}",
        f"- 赛题指定环境整体就绪：{'是' if verdict['competition_environment_ready'] else '否'}",
        "",
        "> V11 是硬性要求，SDK 是推荐项；环境就绪不等于赛事提交或虚拟机获得认可。",
        "",
    ]
    markdown_target.write_text("\n".join(lines), encoding="utf-8")

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

from .compatibility import collect_compatibility_report
from .embeddings import KylinEmbeddingConfig


def _port_available(host: str, port: int) -> tuple[bool, str | None]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
        return True, None
    except OSError as exc:
        return False, str(exc)


def run_preflight(
    *,
    workspace: str | Path,
    input_path: str | Path,
    suite_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    sdk_config: KylinEmbeddingConfig | dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace_path = Path(workspace)
    input_file = Path(input_path)
    suite_file = Path(suite_path)
    compatibility = collect_compatibility_report(workspace_path, sdk_config=sdk_config)
    port_ok, port_error = _port_available(host, port)
    checks = [
        {
            "name": "python_3_10_or_newer",
            "passed": sys.version_info >= (3, 10),
            "blocking": True,
            "detail": compatibility["runtime"]["python"],
        },
        {
            "name": "sample_input_exists",
            "passed": input_file.is_file(),
            "blocking": True,
            "detail": str(input_file),
        },
        {
            "name": "evaluation_suite_exists",
            "passed": suite_file.is_file(),
            "blocking": True,
            "detail": str(suite_file),
        },
        {
            "name": "workspace_writable",
            "passed": compatibility["resources"]["filesystem"]["writable"],
            "blocking": True,
            "detail": compatibility["resources"]["filesystem"]["path"],
        },
        {
            "name": "sqlite_fts5_available",
            "passed": compatibility["sqlite"]["fts5"],
            "blocking": True,
            "detail": compatibility["sqlite"]["version"],
        },
        {
            "name": "dashboard_port_available",
            "passed": port_ok,
            "blocking": True,
            "detail": f"{host}:{port}" if port_ok else str(port_error),
        },
        {
            "name": "real_kylin_sdk_ready",
            "passed": compatibility["embedding_sdk"].get("compatible", False),
            "blocking": False,
            "detail": compatibility["embedding_sdk"]["status"],
        },
        {
            "name": "real_galaxy_kylin_environment",
            "passed": compatibility["operating_system"]["is_galaxy_kylin"],
            "blocking": False,
            "detail": compatibility["operating_system"]["platform"],
        },
    ]
    blocking_failures = [item["name"] for item in checks if item["blocking"] and not item["passed"]]
    warnings = [item["name"] for item in checks if not item["blocking"] and not item["passed"]]
    return {
        "ready_for_local_demo": not blocking_failures,
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "checks": checks,
    }

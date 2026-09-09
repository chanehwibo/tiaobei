"""Read-only prerequisites for the isolated Agent/Judge workflow, not acceptance."""
from __future__ import annotations

from datetime import datetime, timezone
import platform
import re
import shutil

from .action_evaluation import load_json
from .action_judging import controller_source_identity, validate_manifest
from .bounded_command import CommandFailure, run_bounded
from .compatibility import _os_release
from .official_contract import environment_identity

ENGINE_FORMATS = {
    "docker": (
        '{"version":{{json .ServerVersion}},"os":{{json .OSType}},'
        '"architecture":{{json .Architecture}},"cpus":{{json .NCPU}},'
        '"memory_bytes":{{json .MemTotal}}}'
    ),
    "podman": (
        '{"version":{{json .Version.Version}},"os":{{json .Host.OS}},'
        '"architecture":{{json .Host.Arch}},"cpus":{{json .Host.CPUs}},'
        '"memory_bytes":{{json .Host.MemTotal}}}'
    ),
}
IMAGE_FORMAT = (
    '{"id":{{json .Id}},"os":{{json .Os}},"architecture":{{json .Architecture}},'
    '"size_bytes":{{json .Size}}}'
)
MEMORY_LIMIT_BYTES = 2 * 1024**3


def _architecture(value):
    return {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64",
            "arm64": "arm64"}.get(value.lower()) if isinstance(value, str) else None


def _inventory(argv, runner, *, image=False):
    fields = {"id", "os", "architecture", "size_bytes"} if image else {
        "version", "os", "architecture", "cpus", "memory_bytes"}
    try:
        completed = runner(argv, timeout=15, max_stdout=16 * 1024, max_stderr=4096)
        if completed.returncode != 0:
            return {"valid": False, "error_code": "engine_nonzero_exit"}
        row = load_json(completed.stdout)
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("invalid inventory fields")
        if (row["os"] not in {"linux", "windows"} or _architecture(row["architecture"]) is None
                or not isinstance(row["architecture"], str)):
            raise ValueError("invalid platform fields")
        numeric = ("size_bytes",) if image else ("cpus", "memory_bytes")
        if any(type(row[key]) is not int or row[key] < (0 if image else 1) for key in numeric):
            raise ValueError("invalid resource fields")
        identity_key = "id" if image else "version"
        pattern = r"sha256:[a-f0-9]{64}" if image else r"[0-9][0-9A-Za-z.+-]{0,63}"
        if not isinstance(row[identity_key], str) or not re.fullmatch(pattern, row[identity_key]):
            raise ValueError("invalid identity field")
        return {"valid": True, **row}
    except CommandFailure as exc:
        known = {"command_output_limit", "command_timeout", "command_pipe_not_closed",
                 "command_nonzero_exit", "command_invalid_utf8"}
        return {"valid": False, "error_code": str(exc) if str(exc) in known else "engine_command_failed"}
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # Engine output can contain local paths or credentials; never echo it.
        return {"valid": False, "error_code": "engine_inventory_unavailable_or_invalid"}


def inspect_readiness(root, *, sample=None, manifest=None, engine="docker", runner=run_bounded):
    if engine not in ENGINE_FORMATS:
        raise ValueError("unsupported local engine")
    if (sample is None) != (manifest is None):
        raise ValueError("sample and manifest must be supplied together")
    source = controller_source_identity(root)["sha256"]
    manifest_valid = False
    manifest_error = "frozen_run_inputs_missing"
    manifest_digest = None
    if manifest is not None:
        try:
            validated = validate_manifest(manifest, sample)
            frozen = datetime.fromisoformat(manifest["frozen_at_utc"].replace("Z", "+00:00"))
            if frozen > datetime.now(timezone.utc):
                raise ValueError("future freeze time")
            manifest_valid, manifest_error = True, None
            manifest_digest = validated["manifest_sha256"]
        except (ValueError, TypeError, KeyError, RecursionError):
            manifest_error = "frozen_manifest_invalid"
    identity = environment_identity(platform.system(), _os_release())
    host_arch = _architecture(platform.machine())
    executable = shutil.which(engine)
    server = (_inventory([executable, "info", "--format", ENGINE_FORMATS[engine]], runner)
              if executable else {"valid": False, "error_code": "engine_not_on_path"})
    server_arch = _architecture(server.get("architecture"))
    images = {}
    for role in ("agent", "judge"):
        observed = {"valid": False, "error_code": "frozen_manifest_or_engine_unavailable"}
        if manifest_valid and server["valid"]:
            observed = _inventory(
                [executable, "image", "inspect", "--format", IMAGE_FORMAT, manifest[role]["image"]],
                runner, image=True)
        observed["matches_pinned_linux_image"] = bool(
            observed["valid"] and observed["id"] == manifest[role]["image"]
            and observed["os"] == "linux"
            and host_arch is not None and _architecture(observed["architecture"]) == host_arch == server_arch)
        images[role] = observed
    checks = {
        "frozen_manifest_valid": manifest_valid,
        "controller_source_matches_freeze": bool(
            manifest_valid and manifest["controller_source_sha256"] == source),
        "required_v11_identity": identity["is_required_v11"],
        "local_engine_reachable": server["valid"],
        "linux_engine_matches_host_architecture": bool(
            server["valid"] and server["os"] == "linux"
            and host_arch is not None and server_arch == host_arch),
        "engine_has_minimum_container_capacity": bool(
            server["valid"] and server["cpus"] >= 2 and server["memory_bytes"] >= MEMORY_LIMIT_BYTES),
        "agent_image_matches_pin": images["agent"]["matches_pinned_linux_image"],
        "judge_image_matches_pin": images["judge"]["matches_pinned_linux_image"],
        "source_unchanged_during_inspection": source == controller_source_identity(root)["sha256"],
    }
    return {
        "schema": "action_readiness_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "read_only_local_prerequisites_not_model_execution_or_official_acceptance",
        "controller_source_sha256": source, "manifest_sha256": manifest_digest,
        "manifest_error": manifest_error, "environment_identity": identity,
        "host_architecture": host_arch, "engine": {"name": engine, **server}, "images": images,
        "checks": checks, "static_prerequisites_passed": all(checks.values()),
        "missing_static_prerequisites": [key for key, passed in checks.items() if not passed],
        "runtime_requirements_not_verified": {
            "per_container_cpu_limit": 2, "per_container_memory_limit_bytes": MEMORY_LIMIT_BYTES,
            "judge_context_tokens": 32768, "judge_max_output_tokens": 12288,
            "maximum_adapter_wall_seconds": 600,
            "model_bytes_and_digest_inside_image": False,
            "adapter_entrypoints_and_permissions": False,
            "model_peak_rss_and_context_fit": False,
            "host_overhead_and_available_memory_fit": False,
            "independent_labels_and_human_review": False,
            "organizer_original_and_applicable_configuration": False,
        },
        "images_started_or_pulled": False, "model_endpoints_contacted": False,
        "agent_executed": False, "independent_judge_executed": False,
        "competition_submission_ready": False,
        "limitations": [
            "Image size is storage, not process RSS, model memory or a context-window fit measurement.",
            "Engine totals are not currently available resources; no workload was launched.",
            "Pinned declarations and local metadata do not authenticate external roles or organizer documents.",
        ],
    }

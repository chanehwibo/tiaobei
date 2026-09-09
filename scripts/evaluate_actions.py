"""Cross-session self-check or isolated V11 container evidence collection.

Exit 0: fixture/protocol check passed. Exit 2: failure. Exit 3: container
evidence collected, but independent judging and external acceptance are pending.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.action_evaluation import (
    DockerSample, load_json, make_cross_session_sample, make_sample, run_sample, validate_sample,
)
from os_agent_memory.compatibility import _os_release
from os_agent_memory.action_judging import controller_source_identity, digest_json, validate_manifest
from os_agent_memory.file_memory import FileMemory
from os_agent_memory.official_contract import environment_identity


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="fresh per-sample directory")
    parser.add_argument("--output", type=Path, required=True, help="new private controller report, outside workspace")
    parser.add_argument("--mode", choices=("fixture", "container"), default="fixture")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--sample", type=Path, help="private controller JSON, never mounted in the container")
    source.add_argument("--legacy-fixture", action="store_true", help="old same-session diagnostic, not protocol compliant")
    parser.add_argument("--validate-only", action="store_true", help="validate the sample without creating a workspace")
    parser.add_argument("--image", help="reviewed, preinstalled sha256 image ID")
    parser.add_argument("--manifest", type=Path, help="private pre-execution identity/freeze manifest")
    parser.add_argument("--adapter-argv", help="JSON array of the absolute adapter executable and its arguments")
    parser.add_argument("--engine", choices=("docker", "podman"), default="docker")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--confirm-isolated-guest", action="store_true")
    args = parser.parse_args(argv)
    for path in (args.output.absolute(), args.workspace.absolute()):
        FileMemory._check_path(path)
    if args.output.resolve().is_relative_to(args.workspace.resolve()):
        parser.error("controller output must remain outside the agent workspace")
    if args.output.exists():
        parser.error("refusing to overwrite a controller report")
    if args.sample:
        FileMemory._check_path(args.sample.absolute())
        if args.sample.resolve().is_relative_to(args.workspace.resolve()):
            parser.error("private sample must remain outside the agent workspace")
        sample = load_json(FileMemory._bounded_read(args.sample, 1024 * 1024))
    else:
        sample = make_sample() if args.legacy_fixture else make_cross_session_sample()
    protocol = validate_sample(sample, require_cross_session=args.mode == "container")
    manifest, identity_before = None, None
    if args.manifest:
        FileMemory._check_path(args.manifest.absolute())
        if args.manifest.resolve().is_relative_to(args.workspace.resolve()):
            parser.error("private manifest must remain outside the agent workspace")
        manifest = load_json(FileMemory._bounded_read(args.manifest, 64 * 1024))
        validate_manifest(manifest, sample)
        identity_before = controller_source_identity(Path(__file__).resolve().parents[1])["sha256"]
        if (manifest["controller_source_sha256"] != identity_before
                or (args.image is not None and manifest["agent"]["image"] != args.image)
                or datetime.fromisoformat(manifest["frozen_at_utc"].replace("Z", "+00:00"))
                > datetime.now(timezone.utc)):
            parser.error("manifest does not match the current source, image or freeze time")
    if args.validate_only:
        result = {"protocol": protocol, "execution_completed": False, "official_accuracy_verified": False}
        code = 0
    elif args.mode == "fixture":
        if args.sample or args.image or args.adapter_argv or args.manifest:
            parser.error("external samples and images require container mode (or --validate-only)")
        result = run_sample(sample, args.workspace)
        code = 0 if result["posthoc"]["passed"] else 2
    else:
        identity = environment_identity(platform.system(), _os_release())
        if not args.confirm_isolated_guest or not identity["is_required_v11"]:
            parser.error("container mode requires the isolated V11 guest; never start a host engine")
        if not args.sample or not args.image or not args.adapter_argv:
            parser.error("container mode requires --sample, --image and --adapter-argv")
        adapter_argv = load_json(args.adapter_argv)
        if args.workspace.exists() and any(args.workspace.iterdir()):
            parser.error("container workspace must be empty")
        args.workspace.mkdir(parents=True, exist_ok=True)
        result = {"protocol": protocol, "official_accuracy_verified": False, "execution_completed": False}
        try:
            with DockerSample(args.workspace, args.image, adapter_argv,
                              engine=args.engine, timeout=args.timeout) as container:
                result = run_sample(sample, args.workspace, adapter_factory=container.adapter_factory,
                                    posthoc_mode="evidence_only", before_posthoc=container.freeze)
            result["container"] = {"engine": args.engine, "image": args.image,
                "removed": True, "guest_identity": identity, "isolation_acknowledged_by_operator": True}
            evidence = result["posthoc"]
            code = 3 if (result["execution_completed"] and evidence["all_expected_files_captured"]
                         and evidence["inventory_error"] is None) else 2
        except Exception as exc:
            result["container_error"] = {"type": type(exc).__name__}
            code = 2
        result["acceptance_complete"] = False
        result["next_required"] = "independent judge, blind labels, and acceptance-record archival"
    if manifest is not None:
        identity_after = controller_source_identity(Path(__file__).resolve().parents[1])["sha256"]
        result["run_manifest_sha256"] = digest_json(manifest)
        result["controller_source_sha256"] = identity_before
        result["controller_source_unchanged"] = identity_before == identity_after
        result["agent_model_declared"] = manifest["agent"]["model"]
        if identity_before != identity_after:
            result["execution_completed"] = False
            result["execution_error"] = {"type": "ControllerSourceChanged"}
            code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"sample_id": result.get("sample_id"), "protocol": protocol,
        "execution_completed": result["execution_completed"], "exit_code": code,
        "official_accuracy_verified": False}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

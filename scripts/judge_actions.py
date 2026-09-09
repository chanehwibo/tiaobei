"""Prepare, run or import a private independent-judge exchange.

Exit 0: preparation/validation only. Exit 2: failed checks, invalid input or
runtime failure. Exit 3: validated scores still awaiting independent attestation
and human review. No command in this script certifies competition readiness.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.action_evaluation import load_json, validate_sample
from os_agent_memory.action_judging import (
    DockerJudge, assess_human_review, assess_judge_response, controller_source_identity,
    digest_json, prepare_human_review, prepare_judge_request, validate_judge_request, validate_manifest,
)
from os_agent_memory.compatibility import _os_release
from os_agent_memory.bounded_command import CommandFailure
from os_agent_memory.file_memory import FileMemory
from os_agent_memory.official_contract import environment_identity


def read_private(path, maximum=4 * 1024 * 1024):
    path = path.absolute()
    FileMemory._check_path(path)
    if not path.is_file():
        raise ValueError("input must be a regular file")
    return load_json(FileMemory._bounded_read(path, maximum))


def reserve_output(path, inputs):
    path = path.absolute()
    FileMemory._check_path(path)
    if path.exists() or any(path.resolve() == p.resolve() for p in inputs):
        raise ValueError("refusing to overwrite an input or earlier report")


def write_new(path, value):
    FileMemory._check_path(path.absolute())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze", help="bind one sample, source and declared runtime identities")
    freeze.add_argument("--sample", type=Path, required=True)
    freeze.add_argument("--identities", type=Path, required=True,
                        help="JSON: run_id, purpose, roles, agent, judge; declarations only")
    freeze.add_argument("--output", type=Path, required=True)
    prepare = commands.add_parser("prepare", help="private judge request after container execution")
    prepare.add_argument("--sample", type=Path, required=True)
    prepare.add_argument("--evidence", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", help="validate a frozen request without invoking a model")
    validate.add_argument("--request", type=Path, required=True)
    score = commands.add_parser("score", help="validate an external model response and compute all checks")
    score.add_argument("--request", type=Path, required=True)
    score.add_argument("--response", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    for name, help_text in (
            ("review-template", "generate mandatory blank human review rows"),
            ("review", "validate a separate human review; preserve model scores")):
        review = commands.add_parser(name, help=help_text)
        review.add_argument("--request", type=Path, required=True)
        review.add_argument("--response", type=Path, required=True)
        review.add_argument("--output", type=Path, required=True)
        if name == "review":
            review.add_argument("--review", type=Path, required=True)
    run = commands.add_parser("run", help="invoke a reviewed judge adapter only in the isolated V11 guest")
    run.add_argument("--request", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--raw-output", type=Path, required=True, help="new private raw stdout, retained on failure")
    run.add_argument("--judge-argv", required=True, help="JSON argv, first element absolute inside image")
    run.add_argument("--service-argv", help="optional JSON argv started only inside this judge container")
    run.add_argument("--engine", choices=("docker", "podman"), default="docker")
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--confirm-isolated-guest", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    inputs = [getattr(args, key) for key in ("sample", "identities", "manifest", "evidence", "request", "response", "review")
              if getattr(args, key, None) is not None]
    output = getattr(args, "output", None)
    try:
        if output is not None:
            reserve_output(output, inputs)
        if args.command == "freeze":
            sample, declared = read_private(args.sample, 1024 * 1024), read_private(args.identities, 64 * 1024)
            validate_sample(sample, require_cross_session=True)
            if not isinstance(declared, dict) or set(declared) != {"run_id", "purpose", "roles", "agent", "judge"}:
                raise ValueError("identity declaration fields do not match the contract")
            result = {**declared, "schema": "action_run_manifest_v1",
                "sample_sha256": digest_json(sample),
                "controller_source_sha256": controller_source_identity(ROOT)["sha256"],
                "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            validate_manifest(result, sample)
            code = 0
        elif args.command == "prepare":
            result = prepare_judge_request(read_private(args.sample, 1024 * 1024),
                read_private(args.evidence), read_private(args.manifest, 64 * 1024))
            code = 0
        else:
            request = validate_judge_request(read_private(args.request))
            if args.command == "validate":
                print(json.dumps({"request_valid": True, "request_sha256": request["request_sha256"],
                                  "judge_executed": False, "exit_code": 0}))
                return 0
            if args.command == "score":
                result = assess_judge_response(request, read_private(args.response, 1024 * 1024))
                code = 3 if result["all_checks_passed"] else 2
            elif args.command == "review-template":
                result = prepare_human_review(request, read_private(args.response, 1024 * 1024))
                code = 0
            elif args.command == "review":
                result = assess_human_review(request, read_private(args.response, 1024 * 1024),
                                             read_private(args.review, 1024 * 1024))
                code = 3 if result["all_checks_passed"] and result["human_review"]["completed"] else 2
            else:
                identity = environment_identity(platform.system(), _os_release())
                if not args.confirm_isolated_guest or not identity["is_required_v11"]:
                    raise ValueError("judge execution requires the explicitly confirmed isolated V11 guest")
                reserve_output(args.raw_output, [*inputs, output])
                if args.raw_output.resolve() == output.resolve():
                    raise ValueError("raw response and assessment must be separate")
                judge_argv = load_json(args.judge_argv)
                service_argv = load_json(args.service_argv) if args.service_argv is not None else None
                result = {"schema": "action_judge_run_failure_v1", "request_sha256": request["request_sha256"],
                          "judge_response_validated": False, "all_checks_passed": False,
                          "competition_submission_ready": False}
                raw, completed, judge = None, None, None
                try:
                    with DockerJudge(request["payload"]["manifest"]["judge"]["image"], judge_argv,
                                     engine=args.engine, timeout=args.timeout, service_command=service_argv) as judge:
                        completed = judge.send(request)
                        raw = completed.stdout
                        FileMemory._check_path(args.raw_output.absolute())
                        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
                        with args.raw_output.open("x", encoding="utf-8", newline="\n") as stream:
                            stream.write(raw)
                        if completed.returncode != 0:
                            raise CommandFailure("judge_adapter_nonzero_exit")
                        assessment = assess_judge_response(request, load_json(raw))
                    result = assessment
                    result["independent_llm_judge"]["adapter_executed"] = True
                    result["judge_runtime"] = {"engine": args.engine, "image": judge.image, "removed": True,
                        "guest_identity": identity, "adapter_argv_sha256": digest_json(judge_argv),
                        "service_argv_sha256": digest_json(service_argv) if service_argv is not None else None,
                        "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                        "scope": "observed_container_adapter_not_independently_attested_model"}
                    code = 3 if result["all_checks_passed"] else 2
                except Exception as exc:
                    result["runtime_error"] = {"type": type(exc).__name__}
                    result["adapter_returncode"] = completed.returncode if completed is not None else None
                    result["container_removed"] = bool(judge is not None and judge.removed)
                    result["raw_response_saved"] = raw is not None and args.raw_output.exists()
                    result["judge_response_validated"] = False
                    result["competition_submission_ready"] = False
                    code = 2
        write_new(output, result)
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"exit_code": 2, "error_type": type(exc).__name__,
                          "competition_submission_ready": False}))
        return 2
    print(json.dumps({"exit_code": code, "command": args.command,
                      "judge_response_validated": result.get("judge_response_validated", False),
                      "all_checks_passed": result.get("all_checks_passed"),
                      "competition_submission_ready": False}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

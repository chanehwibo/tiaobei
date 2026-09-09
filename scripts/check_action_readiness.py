"""Inspect frozen identities and local images without installing or executing them.

Exit 2 means missing/invalid static prerequisites. Exit 3 means static checks
passed but model execution, resource fit and external acceptance remain unverified.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.action_readiness import inspect_readiness
from scripts.judge_actions import read_private, reserve_output, write_new


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--engine", choices=("docker", "podman"), default="docker")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if (args.sample is None) != (args.manifest is None):
        parser.error("--sample and --manifest must be supplied together")
    try:
        reserve_output(args.output, [path for path in (args.sample, args.manifest) if path])
        result = inspect_readiness(
            ROOT, engine=args.engine,
            sample=read_private(args.sample, 1024 * 1024) if args.sample else None,
            manifest=read_private(args.manifest, 64 * 1024) if args.manifest else None)
        write_new(args.output, result)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"error_type": type(exc).__name__, "competition_submission_ready": False}))
        return 2
    code = 3 if result["static_prerequisites_passed"] else 2
    print(json.dumps({"exit_code": code, "static_prerequisites_passed": result["static_prerequisites_passed"],
                      "missing_static_prerequisites": result["missing_static_prerequisites"],
                      "competition_submission_ready": False}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

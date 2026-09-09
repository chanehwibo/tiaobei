"""Measure a frozen complex corpus without overwriting earlier evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.complex_retrieval import run_complex_evaluation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", default="1000,10000")
    parser.add_argument("--hard-fractions", default="0,0.75")
    parser.add_argument("--modes", default="hybrid")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--require-targets", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("refusing to overwrite a previous run")
    report = run_complex_evaluation(
        ROOT, sizes=tuple(int(value) for value in args.sizes.split(",")),
        hard_fractions=tuple(float(value) for value in args.hard_fractions.split(",")),
        modes=tuple(args.modes.split(",")), rounds=args.rounds,
        progress=lambda text: print(text, file=sys.stderr, flush=True),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in
                      ("dataset", "quality_targets_met", "safety_passed", "latency_target_met", "all_targets_met")},
                     ensure_ascii=False, indent=2))
    valid = report["source_unchanged_during_run"] and report["safety_passed"]
    return 0 if valid and (not args.require_targets or report["all_targets_met"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())

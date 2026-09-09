import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.workload import run_service_workload
from os_agent_memory.experiments import write_json


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="100,1000")
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--embedding-config", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/runtime/service_workload.json")
    parser.add_argument("--require-integrity", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("refusing to overwrite service workload evidence")
    result = run_service_workload(tuple(map(int, args.sizes.split(","))), rounds=args.rounds, embedding_config=args.embedding_config)
    write_json(args.output, result)
    print(result["results"])
    return 2 if args.require_integrity and not result["integrity_passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

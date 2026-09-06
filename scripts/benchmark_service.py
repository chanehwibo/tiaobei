import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.workload import run_service_workload
from os_agent_memory.experiments import write_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="100,1000")
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/runtime/service_workload.json")
    args = parser.parse_args()
    result = run_service_workload(tuple(map(int, args.sizes.split(","))), rounds=args.rounds)
    write_json(args.output, result)
    print(result["results"])

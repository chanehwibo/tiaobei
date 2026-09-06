import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.experiments import evaluate_frozen, write_json


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/runtime/evaluation_v3.json")
    parser.add_argument("--embedding-config", type=Path)
    args = parser.parse_args()
    suite = json.loads((ROOT / "data/eval/office_memory_eval_v3.json").read_text(encoding="utf-8"))
    report = evaluate_frozen(suite, embedding_config=args.embedding_config)
    write_json(args.output, report)
    print(json.dumps({k: v for k, v in report["test"].items() if k != "rows"}))

"""Run frozen request regression and fail closed when required metrics miss."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.request_evaluation import run_request_evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=10000)
    parser.add_argument("--suite", type=Path)
    parser.add_argument("--embedding-config", type=Path)
    parser.add_argument("--require-targets", action="store_true")
    args = parser.parse_args()
    result = run_request_evaluation(ROOT, size=args.size, suite_path=args.suite, embedding_config=args.embedding_config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("metrics", "observation_counts", "safety_checks", "all_targets_met",
                                           "official_validation_ready")}, ensure_ascii=False, indent=2))
    return 2 if args.require_targets and not result["all_targets_met"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

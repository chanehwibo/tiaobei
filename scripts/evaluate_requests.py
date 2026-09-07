"""Run frozen request regression and fail closed when required metrics miss."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.request_evaluation import run_request_evaluation
from os_agent_memory.request_contract import assess_frozen_requests, assess_request_targets


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=10000)
    parser.add_argument("--suite", type=Path)
    parser.add_argument("--embedding-config", type=Path)
    parser.add_argument("--require-targets", action="store_true")
    parser.add_argument("--require-frozen", action="store_true",
                        help="also enforce the frozen bytes, counts and HashEmbedding configuration")
    args = parser.parse_args(argv)
    result = run_request_evaluation(ROOT, size=args.size, suite_path=args.suite, embedding_config=args.embedding_config)
    result["release_gate"] = assess_frozen_requests(result) if args.require_frozen else assess_request_targets(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("metrics", "observation_counts", "safety_checks", "all_targets_met",
                                           "official_validation_ready", "release_gate")}, ensure_ascii=False, indent=2))
    return 2 if (args.require_targets or args.require_frozen) and not result["release_gate"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

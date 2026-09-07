"""Run the synthetic 50-turn action evaluator self-check (not real Agent scoring)."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.action_evaluation import make_sample, run_sample

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="fresh per-sample directory")
    parser.add_argument("--output", type=Path, required=True, help="controller report, outside workspace")
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.workspace.resolve()):
        parser.error("controller output must remain outside the agent workspace")
    result = run_sample(make_sample(), args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "trace"}, ensure_ascii=False))
    raise SystemExit(0 if result["posthoc"]["passed"] else 2)

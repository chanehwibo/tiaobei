import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.experiments import assess_decay_diagnostics, run_ablations, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write fresh developer-only ablation evidence.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-diagnostics", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("refusing to overwrite ablation evidence")
    suite = json.loads((ROOT / "data/eval/office_memory_eval_v3.json").read_text(encoding="utf-8"))
    result = run_ablations(suite)
    result["diagnostic_gate"] = assess_decay_diagnostics(result)
    write_json(args.output, result)
    print(json.dumps({"retrieval": [{
        k: v for k, v in row["result"].items() if k != "rows"
    } for row in result["retrieval_comparisons"]],
        "decay": result["decay_diagnostics"]["comparison"]}))
    return 2 if args.require_diagnostics and not result["diagnostic_gate"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

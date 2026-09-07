"""Produce honest five-metric internal evidence; formal readiness remains false."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.official_diagnostics import run_official_diagnostics

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument("--require-official", action="store_true", help="fail until genuine official evidence exists")
    args = parser.parse_args()
    result = run_official_diagnostics(ROOT, size=args.size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"metrics": result["metrics"], "counts": result["observation_counts"],
        "official_validation_ready": result["official_validation_ready"]}, ensure_ascii=False))
    raise SystemExit(2 if args.require_official and not result["official_validation_ready"] else 0)

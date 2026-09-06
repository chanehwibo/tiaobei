import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.experiments import run_ablations, write_json

if __name__ == "__main__":
    suite = json.loads((ROOT / "data/eval/office_memory_eval_v3.json").read_text(encoding="utf-8"))
    result = run_ablations(suite)
    write_json(ROOT / "artifacts/verification/round2_ablations.json", result)
    print(json.dumps([{
        k: v for k, v in row["result"].items() if k != "rows"
    } for row in result["retrieval_comparisons"]]))

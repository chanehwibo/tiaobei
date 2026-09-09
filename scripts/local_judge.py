"""JSON stdin/stdout adapter for a preinstalled, local Ollama judge service."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.action_evaluation import load_json
from os_agent_memory.local_judge import LocalModelFailure, OllamaJudge


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=110)
    parser.add_argument("--wait-ready", type=float, default=0, help="inventory-only startup wait, at most 60s")
    parser.add_argument("--confirm-local-model", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_local_model:
        parser.error("explicit permission to send this private request to the local model is required")
    try:
        raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("input limit")
        response = OllamaJudge(args.endpoint, timeout=args.timeout).judge(
            load_json(raw.decode("utf-8")), wait_ready=args.wait_ready)
        sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
        return 0
    except Exception as exc:
        if isinstance(exc, LocalModelFailure):
            # Stdout is the private controller pipe; public stderr never includes model text.
            sys.stdout.buffer.write((json.dumps(exc.private_record(), allow_nan=False) + "\n").encode("utf-8"))
        print(json.dumps({"error_type": type(exc).__name__, "judge_response_validated": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

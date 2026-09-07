"""JSONL adapter for a trusted runtime; never exposes general filesystem tools."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.file_memory import WriteContext
from os_agent_memory.memory_tools import MemoryTools, LocalIndexSelector
from os_agent_memory.schemas import utc_now


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--session-id", default="unknown")
    parser.add_argument("--authorize-write", action="store_true", help="trusted runtime only, after explicit user consent")
    parser.add_argument("--selector", choices=("none", "local-diagnostic"), default="none")
    args = parser.parse_args()
    tools = MemoryTools(args.workspace, selector=LocalIndexSelector() if args.selector == "local-diagnostic" else None)
    for line in sys.stdin:
        try:
            if len(line.encode()) > 65536:
                raise ValueError("request too large")
            request = json.loads(line)
            context = WriteContext(args.authorize_write, args.session_id, utc_now())
            result = tools.dispatch(request["tool"], request["arguments"], context=context)
            print(json.dumps({"result": result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"error": type(exc).__name__}), flush=True)

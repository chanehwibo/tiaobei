"""Read-only runtime inventory; never installs, pulls, starts engines or calls models."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import os
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.compatibility import _os_release
from os_agent_memory.official_contract import environment_identity

MODEL_VARIABLES = (
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
    "DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_HOST", "KYLINBOT_API_URL",
    "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AGENT_MODEL", "JUDGE_MODEL",
)
COMMANDS = ("docker", "podman", "kylinbot", "kylin-bot", "ollama", "llama-server")


def inventory():
    installed = {name: shutil.which(name) for name in COMMANDS}
    engines = {}
    for name, template in (("docker", "{{.ServerVersion}}"), ("podman", "{{.Version.Version}}")):
        row = {"installed": bool(installed[name]), "reachable": False, "server_version": None}
        if installed[name]:
            try:
                completed = subprocess.run([installed[name], "info", "--format", template],
                    capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
                version = completed.stdout.strip()
                row.update(returncode=completed.returncode, reachable=completed.returncode == 0 and bool(version))
                if row["reachable"] and len(version) <= 128:
                    row["server_version"] = version
            except (OSError, subprocess.TimeoutExpired) as exc:
                row["error_type"] = type(exc).__name__
        engines[name] = row
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "read_only_resource_inventory_not_agent_or_deployment_acceptance",
        "system": platform.system(), "python": platform.python_version(),
        "environment_identity": environment_identity(platform.system(), _os_release()),
        "commands_on_path": {name: bool(path) for name, path in installed.items()},
        "engines": engines,
        "model_environment_present": {name: bool(os.environ.get(name)) for name in MODEL_VARIABLES},
        "model_endpoints_contacted": False, "images_started_or_pulled": False,
        "agent_executed": False, "independent_judge_executed": False,
        "organizer_acceptance_verified": False,
        "limits": "PATH and selected process environment only; absence is not a full disk/model inventory",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite a resource inventory")
    result = inventory()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))

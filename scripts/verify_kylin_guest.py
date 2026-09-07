"""Run project checks inside an installed, isolated Galaxy Kylin V11 guest."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from os_agent_memory.compatibility import collect_compatibility_report


def verify(output):
    if platform.system() != "Linux":
        raise ValueError("run this script inside the Linux guest")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "system": platform.system(), "machine": platform.machine(), "python": platform.python_version(),
        "compatibility": collect_compatibility_report(output), "checks": {},
        "official_validation_ready": False, "scope": "installed_v11_virtual_machine_with_hash_embedding"}
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"}
    commands = {
        "unit_tests": [sys.executable, "-S", "-m", "unittest", "discover", "-s", "tests", "-v"],
        "source_check": [sys.executable, "-S", "scripts/check_source.py"],
        "retrieval_v3": [sys.executable, "-S", "scripts/evaluate_v3.py", "--require-quality"],
        "official_diagnostics": [sys.executable, "-S", "scripts/evaluate_official.py", "--size", "10000", "--output", str(output / "official.json")],
        "action_framework": [sys.executable, "-S", "scripts/evaluate_actions.py", "--workspace", str(output / "action-workspace"), "--output", str(output / "actions.json")],
        "native_sdk": [sys.executable, "-S", "scripts/check_kylin_native.py", "--output", str(output / "native-sdk.json")],
        "root_filesystem": ["findmnt", "-n", "-o", "SOURCE,FSTYPE", "/"],
        "virtualization": ["systemd-detect-virt"],
        "installed_sdk_packages": ["dpkg-query", "-W", "-f=${binary:Package} ${Version}\n", "*embedding*", "*vector-engine*", "*coreai*", "open-vm-tools*"],
    }
    for name, command in commands.items():
        print("Running " + name, flush=True)
        log = output / (name + ".log")
        try:
            with log.open("w", encoding="utf-8") as stream:
                result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=900, check=False)
            report["checks"][name] = {"returncode": result.returncode, "log": log.name}
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["checks"][name] = {"returncode": None, "error_type": type(exc).__name__, "log": log.name}
        (output / "kylin_vm.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    tests = (output / "unit_tests.log").read_text(encoding="utf-8")
    match = re.search(r"Ran (\d+) tests?", tests)
    report["tests_run"] = int(match.group(1)) if match else None
    report["tests_passed"] = report["checks"]["unit_tests"]["returncode"] == 0
    root_fs = (output / "root_filesystem.log").read_text(encoding="utf-8").strip()
    report["root_filesystem"] = root_fs
    report["installed"] = root_fs.startswith("/dev/") and "overlay" not in root_fs
    report["virtualization"] = (output / "virtualization.log").read_text(encoding="utf-8").strip()
    report["core_checks_passed"] = all(report["checks"][name]["returncode"] == 0
        for name in ("unit_tests", "source_check", "retrieval_v3", "official_diagnostics", "action_framework"))
    report["source_sha256"] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "src").rglob("*.py"))}
    (output / "kylin_vm.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("installed", "tests_run", "tests_passed", "core_checks_passed", "official_validation_ready")}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.output)
    raise SystemExit(0 if report["installed"] and report["core_checks_passed"] else 2)

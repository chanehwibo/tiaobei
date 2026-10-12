"""Export a committed repository snapshot, without Git history or working files."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "SOURCE_MANIFEST.json"
FORBIDDEN_PARTS = {".git", ".venv", "venv", "__pycache__", "node_modules", "private"}


def git_executable() -> str:
    executable = shutil.which("git.exe") or shutil.which("git")
    if executable is None:
        raise RuntimeError("Git must be installed")
    if Path(executable).suffix.lower() in {".cmd", ".bat"}:
        # Resolve a simple Windows launcher without passing repository paths
        # through cmd.exe, where metacharacters could become shell syntax.
        match = re.search(r'^"([^"\r\n]+git\.exe)" %\*\s*$',
                          Path(executable).read_text(encoding="utf-8"), re.MULTILINE | re.IGNORECASE)
        if not match or not Path(match[1]).is_file():
            raise RuntimeError("put git.exe on PATH; unsupported Git shell wrapper")
        executable = match[1]
    return executable


def export_source(root: Path, output: Path) -> dict:
    root, output = root.resolve(), output.absolute()
    if output.exists():
        raise ValueError("refusing to overwrite a source archive")
    executable = git_executable()
    commit = subprocess.check_output(
        [executable, "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"], text=True).strip()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="source-export-") as temporary:
        archive = Path(temporary) / "source.zip"
        subprocess.run([executable, "-C", str(root), "archive", "--format=zip",
                        "--output=" + str(archive), commit], check=True, capture_output=True)
        files = {}
        with ZipFile(archive) as source:
            for info in source.infolist():
                path = PurePosixPath(info.filename)
                if (path.is_absolute() or ".." in path.parts or "\\" in info.filename
                        or FORBIDDEN_PARTS.intersection(path.parts)
                        or info.filename.startswith(("artifacts/runtime/", "case_studies/collected/"))
                        or path.suffix.lower() in {".sqlite", ".pyc", ".pem", ".key"}
                        or path.name == ".env" or info.filename == MANIFEST
                        or stat.S_ISLNK(info.external_attr >> 16)):
                    raise ValueError("unsafe tracked source member: " + info.filename)
                if not info.is_dir():
                    files[info.filename] = hashlib.sha256(source.read(info)).hexdigest()
        report = {"source_commit": commit, "files_sha256": files,
                  "scope": "committed_repository_snapshot_including_labeled_historical_evidence",
                  "uncommitted_work_included": False, "competition_ready": False}
        with ZipFile(archive, "a") as source:
            source.writestr(MANIFEST, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        # Exclusive creation keeps another export from silently replacing evidence.
        with archive.open("rb") as source, output.open("xb") as destination:
            shutil.copyfileobj(source, destination)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {"source_commit": commit, "files": len(files), "bytes": output.stat().st_size,
            "sha256": digest, "competition_ready": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(export_source(ROOT, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

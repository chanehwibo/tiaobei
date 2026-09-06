"""Check advertised Python syntax and public release privacy without dependencies."""
import ast
from pathlib import Path

from verify_release import scan_sensitive_text

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    files = sorted(path for directory in ("src", "scripts", "tests")
                   for path in (ROOT / directory).rglob("*.py"))
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 10))
    scan = scan_sensitive_text(ROOT)
    print({"python_310_syntax_files": len(files), "privacy_findings": len(scan["unexpected_findings"])})
    if not scan["passed"]:
        raise SystemExit(1)

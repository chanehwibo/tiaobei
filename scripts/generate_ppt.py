"""Generate current source-bound review slides and the companion technical report."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_review_materials import main as generate_review


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--office" not in arguments:
        arguments.append("--office")
    return generate_review(arguments)


if __name__ == "__main__":
    raise SystemExit(main())

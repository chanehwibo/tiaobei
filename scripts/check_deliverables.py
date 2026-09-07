"""Check editable deliverables without mistaking XML checks for visual review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "dc": "http://purl.org/dc/elements/1.1/",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
}


def inspect_ooxml(path: Path) -> dict:
    issues = []
    texts = []
    slide_count = 0
    try:
        with ZipFile(path) as archive:
            roots = {
                name: ET.fromstring(archive.read(name))
                for name in archive.namelist()
                if name.endswith((".xml", ".rels"))
            }
        core = roots.get("docProps/core.xml")
        if core is None:
            issues.append("missing_core_metadata")
        else:
            for tag in ("dc:creator", "cp:lastModifiedBy"):
                if (core.findtext(tag, default="", namespaces=NS) or "").strip():
                    issues.append(f"nonempty_metadata:{tag}")
        for name, root in roots.items():
            if name.endswith(".rels"):
                if any(node.get("TargetMode") == "External" for node in root):
                    issues.append(f"external_relationship:{name}")
            if name.startswith(("ppt/slides/", "word/")):
                texts.extend(node.text or "" for node in root.iter()
                             if node.tag in (f"{{{NS['a']}}}t", f"{{{NS['w']}}}t"))
        if path.suffix == ".pptx":
            size = roots["ppt/presentation.xml"].find("p:sldSz", NS)
            width, height = int(size.get("cx")), int(size.get("cy"))
            for name, root in roots.items():
                if not re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                    continue
                slide_count += 1
                for transform in root.findall(".//p:spPr/a:xfrm", NS):
                    offset, extent = transform.find("a:off", NS), transform.find("a:ext", NS)
                    if offset is None or extent is None:
                        continue
                    x, y = int(offset.get("x")), int(offset.get("y"))
                    w, h = int(extent.get("cx")), int(extent.get("cy"))
                    if min(x, y, w, h) < 0 or x + w > width or y + h > height:
                        issues.append(f"shape_outside_canvas:{name}")
            if slide_count != 15:
                issues.append(f"slide_count:{slide_count}")
        if any("ROUND5 EVIDENCE" in text for text in texts):
            issues.append("unrendered_evidence_marker")
    except (OSError, BadZipFile, ET.ParseError, KeyError, TypeError, ValueError) as exc:
        issues.append(f"invalid_ooxml:{type(exc).__name__}")
    return {"passed": not issues, "issues": issues, "slide_count": slide_count, "texts": texts}


def check_deliverables(project_root: Path = ROOT) -> dict:
    root = project_root.resolve()
    summary_path = root / "artifacts/verification/round5/evidence_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    issues = []
    if summary["competition_ready"] is not False:
        issues.append("unsupported_official_readiness")
    for relative, expected in summary["source_sha256"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            issues.append(f"missing_or_unsafe_evidence:{relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            issues.append(f"evidence_hash_mismatch:{relative}")
    expected_text = ["INCOMPLETE", "V11", "HashEmbedding", "P95"]
    for platform in ("windows", "kylin"):
        request = summary["requests"][platform]
        expected_text.append(f"{request['metrics']['retrieval_p95_ms']:.3f}")
        expected_text.append(str(summary["test_results"][platform]["tests_run"]))
        expected_text.extend(str(value) for value in request["observation_counts"].values())
        for key, value in request["metrics"].items():
            if key != "retrieval_p95_ms":
                expected_text.append(f"{value:.2%}")
    reports = {}
    for suffix, directory in (("pptx", "ppt"), ("docx", "doc")):
        candidates = sorted((root / "deliverables" / directory).glob(f"*.{suffix}"))
        if len(candidates) != 1:
            issues.append(f"expected_one_deliverable:{suffix}")
            continue
        path = candidates[0]
        report = inspect_ooxml(path)
        content = "\n".join(report.pop("texts"))
        report["missing_evidence_values"] = sorted({item for item in expected_text if item not in content})
        report["passed"] = report["passed"] and not report["missing_evidence_values"]
        report["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        reports[path.relative_to(root).as_posix()] = report
    return {
        "schema_version": 1,
        "scope": "ooxml_structure_and_evidence_consistency_not_visual_render",
        "passed": not issues and len(reports) == 2 and all(item["passed"] for item in reports.values()),
        "issues": issues,
        "deliverables": reports,
        "visual_render_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = check_deliverables()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

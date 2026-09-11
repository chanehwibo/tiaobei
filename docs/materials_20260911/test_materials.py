"""Focused regression tests for document generation, not new performance evidence."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from docs.materials_20260911 import evidence, generate, qa
from docs.materials_20260911.content import CHAPTERS, STATUS, build_topics
from docs.materials_20260911.diagrams import DIAGRAMS, HEIGHT, WIDTH


class MaterialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence, cls.provenance = evidence.load_evidence()
        cls.topics = build_topics(cls.evidence)
        runtime = ROOT / "artifacts/runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="office-tests-", dir=runtime)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.materials = cls.root / "generated"
        with patch.object(generate, "load_evidence", return_value=(cls.evidence, cls.provenance)):
            cls.manifest = generate.generate(cls.materials)

    def fixture(self, name):
        return shutil.copytree(self.materials, self.root / name)

    def check(self, directory):
        with patch.object(qa, "load_evidence", return_value=(self.evidence, self.provenance)):
            return qa.check_pair(directory)

    def test_actual_evidence_and_all_comparison_gates(self):
        self.assertEqual(self.provenance["runtime_file_count"], 149)
        self.assertTrue(all(self.provenance["checks"].values()))
        self.assertEqual(len(self.provenance["comparisons"]), 3)
        for result in self.provenance["comparisons"]:
            self.assertEqual(len(result["checks"]), 7)
            self.assertTrue(result["optimization_gates_passed"])
            self.assertFalse(result["all_controls_meet_targets"])
        self.assertFalse(self.provenance["new_performance_run"])
        self.assertFalse(self.provenance["competition_ready"])

    def test_changed_runtime_snapshot_is_rejected(self):
        changed = evidence.file_hashes(ROOT)
        key = next(iter(changed["lf_sha256"]))
        changed["lf_sha256"][key] = "0" * 64
        with patch.object(evidence, "file_hashes", return_value=changed):
            with self.assertRaises(ValueError):
                evidence.load_evidence()

    def test_changed_raw_measurement_is_rejected(self):
        read = evidence.load_json

        def modified(path):
            value = read(path)
            if Path(path).name == "requests.json":
                value["metrics"]["knowledge_recall"] = .5
            return value

        with patch.object(evidence, "load_json", side_effect=modified):
            with self.assertRaises(ValueError):
                evidence.load_evidence()

    def test_duplicate_json_keys_are_rejected(self):
        source = self.root / "duplicate.json"
        source.write_text('{"metric": 1, "metric": 2}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            evidence.load_json(source)

    def test_sections_tables_and_diagrams_are_consistent(self):
        numbers = [topic["number"] for topic in self.topics]
        self.assertEqual(len(numbers), 67)
        self.assertEqual(len(set(numbers)), 67)
        self.assertEqual({number.split(".")[0] for number in numbers}, set(CHAPTERS))
        self.assertEqual(len(CHAPTERS), 18)
        self.assertEqual({topic["diagram"] for topic in self.topics if topic["diagram"]},
                         set(DIAGRAMS))
        self.assertEqual(len(DIAGRAMS), 25)
        self.assertEqual(len(generate.presentation_topics(self.topics)) + 2, 53)
        for topic in self.topics:
            self.assertTrue(topic["source"])
            if topic["slide"]:
                self.assertEqual(len(topic["points"]), 3)
            if topic["table"]:
                headers, rows = topic["table"]
                self.assertTrue(all(len(row) == len(headers) for row in rows))

    def test_diagram_labels_fit_and_boxes_stay_inside_canvas(self):
        for diagram in DIAGRAMS.values():
            for node in diagram["nodes"]:
                self.assertGreaterEqual(min(node["x"], node["y"]), 0)
                self.assertLessEqual(node["x"] + node["w"], WIDTH)
                self.assertLessEqual(node["y"] + node["h"], HEIGHT)
                title_size, body_size = generate.diagram_fonts(node)
                self.assertGreaterEqual(min(title_size, body_size), 23)
            for a, b in diagram["edges"]:
                self.assertIn(a, range(len(diagram["nodes"])))
                self.assertIn(b, range(len(diagram["nodes"])))

    def test_existing_directory_and_outside_project_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "overwrite"):
            generate.generate(self.materials)
        outside = ROOT.parent / "must-not-create-office-tests"
        with self.assertRaisesRegex(ValueError, "remain in this project"):
            generate.generate(outside)
        self.assertFalse(outside.exists())
        self.assertEqual(evidence.load_json(self.materials / "materials_manifest.json"),
                         self.manifest)

    def layout(self):
        return {
            "scope": "word_directory_fallbacks_from_measured_render",
            "layout_source_lf_sha256": generate.layout_source_hashes(),
            "page_count": 70,
            "section_pages": {topic["number"]: i + 4 for i, topic in enumerate(self.topics)},
        }

    def test_page_map_requires_matching_source(self):
        layout = self.layout()
        generate.validate_word_layout(layout, self.topics)
        layout["layout_source_lf_sha256"]["content.py"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "page map"):
            generate.validate_word_layout(layout, self.topics)

    def test_page_map_rejects_missing_or_invalid_pages(self):
        original = self.layout()
        for bad in (True, 0, 71, "4"):
            layout = deepcopy(original)
            layout["section_pages"]["1.1"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                generate.validate_word_layout(layout, self.topics)
        layout = deepcopy(original)
        del layout["section_pages"]["1.1"]
        with self.assertRaises(ValueError):
            generate.validate_word_layout(layout, self.topics)
        layout = deepcopy(original)
        layout["section_pages"]["1.1"] = 6
        with self.assertRaises(ValueError):
            generate.validate_word_layout(layout, self.topics)

    def test_generated_pair_passes_strict_structural_checks(self):
        result = self.check(self.materials)
        self.assertTrue(result["passed"])
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["word"]["figures"], 25)
        self.assertEqual(result["presentation"]["editable_diagrams"], 25)
        self.assertEqual(result["presentation"]["slides"], 53)
        self.assertFalse(result["competition_ready"])
        self.assertTrue(result["visual_review_required"])

    def test_changed_office_bytes_are_rejected(self):
        directory = self.fixture("modified-office")
        with (directory / generate.DOCX_NAME).open("ab") as stream:
            stream.write(b"unexpected appended bytes")
        with self.assertRaisesRegex(ValueError, "material output changed"):
            self.check(directory)

    def test_missing_hash_entry_is_rejected(self):
        directory = self.fixture("missing-hash")
        path = directory / "materials_manifest.json"
        manifest = evidence.load_json(path)
        del manifest["output_raw_sha256"][generate.DOCX_NAME]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.check(directory)

    def test_unsupported_acceptance_claim_is_rejected(self):
        directory = self.fixture("false-acceptance")
        path = directory / "materials_manifest.json"
        manifest = evidence.load_json(path)
        manifest["native_latency_passed"] = True
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.check(directory)

    def test_changed_provenance_is_rejected(self):
        directory = self.fixture("changed-provenance")
        path = directory / "evidence_provenance.json"
        value = evidence.load_json(path)
        value["runtime_file_count"] = 1
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "provenance changed"):
            self.check(directory)

    def test_changed_document_tool_snapshot_is_rejected(self):
        directory = self.fixture("changed-tool")
        path = directory / "materials_manifest.json"
        value = evidence.load_json(path)
        key = next(iter(value["document_tool_lf_sha256"]))
        value["document_tool_lf_sha256"][key] = "0" * 64
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "tool snapshot"):
            self.check(directory)

    def test_pdf_is_not_a_deliverable(self):
        directory = self.fixture("extra-pdf")
        (directory / "unexpected.pdf").write_bytes(b"%PDF")
        with self.assertRaisesRegex(ValueError, "PDF or ZIP"):
            self.check(directory)

    def test_identity_and_external_relationships_are_rejected(self):
        for index, (filename, raw) in enumerate((
            ("word/document.xml", "<text>" + qa.FORBIDDEN[3] + "</text>"),
            ("word/_rels/document.xml.rels",
             '<Relationships><Relationship TargetMode="External"/></Relationships>'),
        )):
            source = self.root / f"bad-package-{index}.docx"
            with ZipFile(source, "w") as archive:
                archive.writestr(filename, raw)
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                qa.package_text(source)

    def test_render_reuse_requires_all_parts_to_match(self):
        old, new = self.root / "rendered.pptx", self.root / "same.pptx"
        parts = {"content.xml": "<text>" + STATUS + "</text>", "image.bin": b"pixels"}
        for path, compression, order in ((old, ZIP_STORED, parts.items()),
                                         (new, ZIP_DEFLATED, reversed(list(parts.items())))):
            with ZipFile(path, "w", compression=compression) as archive:
                for key, value in order:
                    archive.writestr(key, value)
        self.assertTrue(qa.verify_render_equivalent(new, old)["passed"])
        with ZipFile(new, "w") as archive:
            archive.writestr("content.xml", "<text>changed</text>")
            archive.writestr("image.bin", b"pixels")
        with self.assertRaisesRegex(ValueError, "content differs"):
            qa.verify_render_equivalent(new, old)


if __name__ == "__main__":
    unittest.main()

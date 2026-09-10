from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from scripts.check_deliverables import check_deliverables, inspect_ooxml


class DeliverableTest(unittest.TestCase):
    def test_current_editable_materials_match_measured_evidence(self):
        report = check_deliverables()
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["visual_render_verified"])

    def test_shared_docx_footer_is_written_once(self):
        root = Path(__file__).resolve().parents[1]
        path, = (root / "deliverables/doc").glob("*.docx")
        with ZipFile(path) as archive:
            footers = [name for name in archive.namelist()
                       if re.fullmatch(r"word/footer\d+\.xml", name)]
            self.assertTrue(footers)
            for name in footers:
                text = "".join(ET.fromstring(archive.read(name)).itertext())
                self.assertEqual(text.count("OS Agent"), 1, name)

    def test_docx_numbered_lists_preserve_markdown_numbers(self):
        root = Path(__file__).resolve().parents[1]
        sources = [next((root / "docs").glob("09_*.md")),
                   root / "docs" / "\u6d4b\u8bd5\u62a5\u544a.md"]
        expected = []
        for source in sources:
            in_code = False
            for line in source.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("```"):
                    in_code = not in_code
                match = re.match(r"^\s*(\d+)[.)]\s+", line)
                if match and not in_code:
                    expected.append(int(match.group(1)))
        self.assertTrue(expected)
        path, = (root / "deliverables/doc").glob("*.docx")
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        value = "{" + ns["w"] + "}val"
        with ZipFile(path) as archive:
            body = ET.fromstring(archive.read("word/document.xml"))
            numbering = ET.fromstring(archive.read("word/numbering.xml"))
        definitions = {item.get("{" + ns["w"] + "}numId"): item
                       for item in numbering.findall("w:num", ns)}
        counters = {}
        actual = []
        for paragraph in body.findall(".//w:p", ns):
            style = paragraph.find("w:pPr/w:pStyle", ns)
            if style is None or style.get(value) != "ListNumber":
                continue
            num_id = paragraph.find("w:pPr/w:numPr/w:numId", ns)
            self.assertIsNotNone(num_id, "list must use an explicit numbering instance")
            key = num_id.get(value)
            if key not in counters:
                start = definitions[key].find("w:lvlOverride/w:startOverride", ns)
                self.assertIsNotNone(start)
                counters[key] = int(start.get(value))
            actual.append(counters[key])
            counters[key] += 1
        self.assertEqual(actual, expected)

    def test_metadata_and_external_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.docx"
            with ZipFile(path, "w") as archive:
                archive.writestr("docProps/core.xml",
                                 '<core xmlns:dc="http://purl.org/dc/elements/1.1/">'
                                 "<dc:creator>personal author</dc:creator></core>")
                archive.writestr("word/_rels/document.xml.rels",
                                 '<Relationships><Relationship TargetMode="External" '
                                 'Target="https://example.invalid"/></Relationships>')
            report = inspect_ooxml(path)
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["issues"]), 2)

    def test_slide_outside_canvas_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.pptx"
            with ZipFile(path, "w") as archive:
                archive.writestr("docProps/core.xml", "<core/>")
                archive.writestr("ppt/presentation.xml",
                                 '<p:presentation xmlns:p="http://schemas.openxmlformats.org/'
                                 'presentationml/2006/main"><p:sldSz cx="100" cy="100"/></p:presentation>')
                archive.writestr("ppt/slides/slide1.xml",
                                 '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
                                 ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                                 '<p:spPr><a:xfrm><a:off x="80" y="0"/><a:ext cx="30" cy="10"/>'
                                 "</a:xfrm></p:spPr></p:sld>")
            report = inspect_ooxml(path)
            self.assertIn("shape_outside_canvas:ppt/slides/slide1.xml", report["issues"])
            self.assertIn("slide_count:1", report["issues"])

    def test_current_slide_count_is_explicit_without_relaxing_historical_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.pptx"
            with ZipFile(path, "w") as archive:
                archive.writestr("docProps/core.xml", "<core/>")
                archive.writestr("ppt/presentation.xml",
                                 '<p:presentation xmlns:p="http://schemas.openxmlformats.org/'
                                 'presentationml/2006/main"><p:sldSz cx="100" cy="100"/></p:presentation>')
                for index in range(1, 19):
                    archive.writestr(f"ppt/slides/slide{index}.xml", "<slide/>")
            self.assertIn("slide_count:18", inspect_ooxml(path)["issues"])
            self.assertTrue(inspect_ooxml(path, expected_slide_count=18)["passed"])
            self.assertIn("slide_count:18", inspect_ooxml(path, expected_slide_count=17)["issues"])

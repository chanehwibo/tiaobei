from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.check_deliverables import check_deliverables, inspect_ooxml


class DeliverableTest(unittest.TestCase):
    def test_current_editable_materials_match_measured_evidence(self):
        report = check_deliverables()
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["visual_render_verified"])

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

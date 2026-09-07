from __future__ import annotations

import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from scripts.verify_release import _run_command, check_materials, discover_public_files, run_release_verification, scan_sensitive_text


class ReleaseVerificationTest(unittest.TestCase):
    def test_privacy_scan_reports_location_without_secret_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            leak = root / "docs" / "leak.md"
            leak.parent.mkdir()
            leak.write_text("contact: real.person@example.org\n", encoding="utf-8")

            result = scan_sensitive_text(root, [leak])

            self.assertFalse(result["passed"])
            self.assertEqual(result["unexpected_findings"], [{"path": "docs/leak.md", "line": 1, "kind": "email"}])
            self.assertNotIn("real.person@example.org", str(result))

    def test_synthetic_test_fixture_is_classified_but_not_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "tests" / "fixture.py"
            fixture.parent.mkdir()
            fixture.write_text("PHONE = '13912345678'\n", encoding="utf-8")

            result = scan_sensitive_text(root, [fixture])

            self.assertTrue(result["passed"])
            self.assertEqual(result["unexpected_findings"], [])
            self.assertEqual(result["approved_synthetic_fixture_findings"][0]["kind"], "cn_phone")

    def test_material_check_lists_missing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("ok", encoding="utf-8")

            result = check_materials(root, ("README.md", "LICENSE"))

            self.assertFalse(result["passed"])
            self.assertEqual(result["missing"], ["LICENSE"])

    def test_fixture_directory_does_not_exempt_unknown_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "tests" / "unexpected.py"
            fixture.parent.mkdir()
            fixture.write_text("token='" + "ghp_" + "A" * 36 + "'", encoding="utf-8")
            result = scan_sensitive_text(root, [fixture])
            self.assertFalse(result["passed"])
            self.assertEqual(result["unexpected_findings"][0]["kind"], "service_token")

    def test_file_discovery_fallback_excludes_private_and_build_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            public = root / "docs" / "public.md"
            private = root / "case_studies" / "private" / "consent.md"
            generated = root / "dist" / "package.txt"
            for path in (public, private, generated):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")

            discovered = discover_public_files(root)

            self.assertEqual(discovered, [public])

    def test_large_logs_are_scanned_past_the_former_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "large.log"
            log.write_text("safe\n" * 450000 + "contact: real.person@example.org\n", encoding="utf-8")
            report = scan_sensitive_text(root, [log])
            self.assertFalse(report["passed"])
            self.assertEqual(report["scanned_text_files"], 1)
            self.assertEqual(report["unexpected_findings"][-1]["line"], 450001)
            self.assertNotIn("real.person@example.org", str(report))

    def test_office_split_run_credentials_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "fixture.docx"
            with ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml",
                                 '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                                 "<w:p><w:r><w:t>ghp_</w:t></w:r><w:r><w:t>" + "A" * 36
                                 + "</w:t></w:r></w:p></w:document>")
            result = scan_sensitive_text(root, [path])
            self.assertFalse(result["passed"])
            self.assertEqual(result["scanned_office_documents"], 1)
            self.assertTrue(any(row["kind"] == "service_token" for row in result["unexpected_findings"]))
            self.assertNotIn("A" * 36, str(result))

    def test_office_metadata_and_external_relationships_are_not_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "fixture.pptx"
            with ZipFile(path, "w") as archive:
                archive.writestr("docProps/core.xml",
                                 '<core xmlns:dc="http://purl.org/dc/elements/1.1/">'
                                 "<dc:creator>personal name</dc:creator></core>")
                archive.writestr("ppt/_rels/presentation.xml.rels",
                                 '<Relationships><Relationship TargetMode="External"/></Relationships>')
            result = scan_sensitive_text(root, [path])
            self.assertEqual({row["kind"] for row in result["unexpected_findings"]},
                             {"author_metadata", "external_document_reference"})

    def test_root_relationships_and_new_default_author_metadata_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "fixture.docx"
            with ZipFile(path, "w") as archive:
                archive.writestr("docProps/core.xml",
                                 '<core xmlns:dc="http://purl.org/dc/elements/1.1/">'
                                 "<dc:creator>python-docx</dc:creator></core>")
                archive.writestr("_rels/.rels", '<Relationships><Relationship TargetMode="External"/></Relationships>')
            result = scan_sensitive_text(root, [path])
            self.assertEqual({row["kind"] for row in result["unexpected_findings"]},
                             {"author_metadata", "external_document_reference"})
            self.assertEqual(result["approved_legacy_template_metadata"], [])

    def test_utf16_logs_and_unreadable_text_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "encoded.log"
            log.write_text("contact: real.person@example.org", encoding="utf-16")
            self.assertFalse(scan_sensitive_text(root, [log])["passed"])
            log.write_bytes(b"\xffbroken")
            result = scan_sensitive_text(root, [log])
            self.assertFalse(result["passed"])
            self.assertEqual(result["unexpected_findings"][0]["kind"], "unreadable_text")

    def test_unknown_binary_media_is_explicitly_left_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "image.png"
            image.write_bytes(b"not a real image")
            result = scan_sensitive_text(root, [image])
            self.assertEqual(result["manual_review_required"],
                             [{"path": "image.png", "reason": "binary_media_not_ocr_scanned"}])
            self.assertEqual(result["scanned_text_files"], 0)

    def test_archives_are_scanned_without_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "bundle.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("project/docs/contact.txt", "real.person@example.org")
                archive.writestr("03_source/project/tests/fixture.py", "PHONE='13912345678'")
            report = scan_sensitive_text(root, [path])
            self.assertFalse(report["passed"])
            self.assertEqual(report["scanned_zip_archives"], 1)
            self.assertEqual(report["scanned_text_files"], 2)
            self.assertEqual(report["unexpected_findings"][0]["kind"], "email")
            self.assertEqual(len(report["unexpected_findings"]), 1)
            self.assertEqual(len(list(root.iterdir())), 1)

    def test_unsafe_archive_entries_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "bundle.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("../outside.txt", "safe")
            report = scan_sensitive_text(root, [path])
            self.assertEqual(report["unexpected_findings"][0]["kind"], "unscannable_archive")

    def test_subprocess_failures_preserve_available_output(self) -> None:
        for error in (OSError("missing"), subprocess.TimeoutExpired(["python"], 1200, output=b"partial output")):
            with self.subTest(error=type(error).__name__), patch("scripts.verify_release.subprocess.run", side_effect=error):
                report = _run_command(["python"], cwd=Path.cwd())
                self.assertFalse(report["passed"])
                self.assertIsNone(report["returncode"])
                self.assertEqual(report["error_type"], type(error).__name__)
                if isinstance(error, subprocess.TimeoutExpired):
                    self.assertIn("partial output", report["output_tail"])

    def test_failed_or_completed_release_runs_cannot_be_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "original.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                run_release_verification(project_root=root, artifact_dir=evidence)

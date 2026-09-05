from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.verify_release import check_materials, discover_public_files, scan_sensitive_text


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

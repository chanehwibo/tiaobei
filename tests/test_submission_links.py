import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import unquote
from unittest.mock import patch

from scripts.build_submission import PackagingError, build_submission, preflight_submission
from scripts.submission_links import relocate_links


class SubmissionLinksTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "docs").mkdir()
        (self.root / "docs/first.md").write_text(
            '[second](second.md#metrics) and [protocol](protocol.md "details")\n', encoding="utf-8",
        )
        (self.root / "docs/second.md").write_text("# Metrics\n", encoding="utf-8")
        (self.root / "docs/protocol.md").write_text("# Protocol\n", encoding="utf-8")
        self.manifest = self.root / "manifest.json"
        self.value = {
            "schema_version": 1, "package_name": "fixture",
            "public_sections": [{"target": "00", "files": ["docs/first.md"]},
                                {"target": "01", "files": ["docs/second.md"]}],
            "source_section": {"target": "source/project", "files": ["docs/protocol.md"], "trees": []},
            "external_inputs": [],
        }
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.value), encoding="utf-8")

    def test_preflight_changes_no_files_and_resolves_public_and_mirrored_targets(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        report = preflight_submission(self.root, self.manifest)
        self.assertTrue(report["passed"])
        self.assertFalse(report["competition_ready"])
        self.assertEqual([row["rewritten"] for row in report["public_markdown_links"]],
                         ["../01/second.md#metrics", "../source/project/docs/protocol.md"])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes()
                                  for p in self.root.rglob("*") if p.is_file()})

    def test_copied_links_work_and_source_bytes_are_not_modified(self):
        original = (self.root / "docs/first.md").read_bytes()
        output = self.root / "result"
        report = build_submission(project_root=self.root, output=output,
                                  manifest_path=self.manifest, external_files={})
        text = (output / "00/first.md").read_text(encoding="utf-8")
        self.assertIn("(../01/second.md#metrics)", text)
        self.assertIn('(../source/project/docs/protocol.md "details")', text)
        self.assertEqual((output / "source/project/docs/first.md").read_bytes(), original)
        self.assertEqual((self.root / "docs/first.md").read_bytes(), original)
        self.assertEqual(len(report["public_markdown_links"]), 2)

    def test_missing_unlisted_external_and_colliding_local_paths_fail_closed(self):
        for link in ("missing.md", "../outside.md", "../../escape.md", "/absolute.md", "file:///private.md"):
            with self.subTest(link=link):
                (self.root / "docs/first.md").write_text(f"[bad]({link})", encoding="utf-8")
                with self.assertRaises(PackagingError):
                    preflight_submission(self.root, self.manifest)
        self.value["public_sections"].append({"target": "00", "files": ["elsewhere/first.md"]})
        (self.root / "elsewhere").mkdir()
        (self.root / "elsewhere/first.md").write_text("# Another", encoding="utf-8")
        self.write_manifest()
        with self.assertRaisesRegex(PackagingError, "\u91cd\u590d"):
            preflight_submission(self.root, self.manifest)

    def test_reference_image_encoded_paths_titles_and_code_examples(self):
        text = (
            '[guide][p]\n[p]: <a%20file.md#heading> "Title"\n![figure](image.png)\n'
            '[external](https://example.org/path) [anchor](#part)\n'
            '`[example](missing.md)`\n```md\n[example](missing.md)\n```\n'
        )
        result, rows = relocate_links(text, source="docs/current.md", target="00/current.md", destinations={
            "docs/a file.md": "01/a file.md", "docs/image.png": "source/docs/image.png",
        })
        self.assertEqual(len(rows), 2)
        self.assertIn('<../01/a%20file.md#heading> "Title"', result)
        self.assertIn("![figure](../source/docs/image.png)", result)
        self.assertIn("`[example](missing.md)`", result)
        self.assertIn("[external](https://example.org/path)", result)
        self.assertEqual(unquote(rows[0]["rewritten"]), "../01/a file.md#heading")

    def test_cli_preflight_never_invokes_builder(self):
        from scripts.build_submission import main
        with patch("scripts.build_submission.PROJECT_ROOT", self.root), \
                patch("scripts.build_submission.build_submission") as build:
            self.assertEqual(main(["--manifest", str(self.manifest), "--preflight-only"]), 0)
            build.assert_not_called()


if __name__ == "__main__":
    unittest.main()

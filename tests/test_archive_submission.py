from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.archive_submission import ArchiveError, create_archive


class SubmissionArchiveTest(unittest.TestCase):
    def make_staging(self, root: Path) -> Path:
        staging = root / "staging"
        staging.mkdir()
        contents = {"PACKAGE_STATUS.md": "incomplete_draft", "source.txt": "synthetic artifact"}
        rows = []
        for name, text in contents.items():
            data = text.encode("utf-8")
            (staging / name).write_bytes(data)
            rows.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        (staging / "build_report.json").write_text(
            json.dumps({"status": "incomplete_draft", "files": rows, "missing_external": ["video"]}),
            encoding="utf-8",
        )
        return staging

    def test_archive_roundtrip_matches_manifest_and_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.make_staging(root)
            archive = root / "release_INCOMPLETE.zip"
            try:
                report = create_archive(staging=staging, archive=archive, allow_incomplete=True)
                self.assertTrue(report["archive_read_only"])
                self.assertTrue(report["build_manifest_verified"])
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), report["archive_sha256"])
                with zipfile.ZipFile(archive) as bundle:
                    self.assertEqual(bundle.read("source.txt"), b"synthetic artifact")
                    self.assertIn("source.txt", bundle.read("SHA256SUMS.txt").decode())
                with self.assertRaisesRegex(ArchiveError, "拒绝覆盖"):
                    create_archive(staging=staging, archive=archive, allow_incomplete=True)
            finally:
                if archive.exists():
                    os.chmod(archive, stat.S_IREAD | stat.S_IWRITE)

    def test_incomplete_archive_requires_opt_in_label_and_external_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = self.make_staging(root)
            for destination, allow in (
                (root / "draft_INCOMPLETE.zip", False),
                (root / "final.zip", True),
                (staging / "draft_INCOMPLETE.zip", True),
            ):
                with self.subTest(destination=destination, allow=allow):
                    with self.assertRaises(ArchiveError):
                        create_archive(staging=staging, archive=destination, allow_incomplete=allow)
                    self.assertFalse(destination.exists())

    def test_changed_or_unlisted_files_prevent_archive_creation(self) -> None:
        for mutation in ("change", "extra"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                staging = self.make_staging(root)
                name = "source.txt" if mutation == "change" else "unlisted.txt"
                (staging / name).write_text("changed", encoding="utf-8")
                archive = root / "draft_INCOMPLETE.zip"
                with self.assertRaises(ArchiveError):
                    create_archive(staging=staging, archive=archive, allow_incomplete=True)
                self.assertFalse(archive.exists())

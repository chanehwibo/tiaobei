import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

from scripts.export_source import export_source, git_executable, MANIFEST


@unittest.skipUnless(shutil.which("git"), "Git is required to test committed exports")
class SourceExportTest(unittest.TestCase):
    def test_export_uses_commit_bytes_and_preserves_local_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.run([git_executable(), "-C", str(root), *args],
                                      check=True, capture_output=True)
            git("init")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "core.autocrlf", "false")
            (root / "app.py").write_bytes(b"print('committed')\n")
            git("add", "app.py")
            git("commit", "-m", "fixture")
            (root / "app.py").write_text("uncommitted", encoding="utf-8")
            (root / "private.txt").write_text("local only", encoding="utf-8")
            output = root / "source.zip"
            report = export_source(root, output)
            with ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {"app.py", MANIFEST})
                manifest = json.loads(archive.read(MANIFEST))
                self.assertEqual(archive.read("app.py"), b"print('committed')\n")
                self.assertEqual(manifest["files_sha256"]["app.py"],
                                 hashlib.sha256(archive.read("app.py")).hexdigest())
                self.assertEqual(manifest["source_commit"], report["source_commit"])
            self.assertEqual((root / "app.py").read_text(), "uncommitted")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                export_source(root, output)
            (root / "secret.key").write_text("synthetic", encoding="utf-8")
            git("add", "secret.key")
            git("commit", "-m", "unsafe fixture")
            with self.assertRaisesRegex(ValueError, "unsafe tracked"):
                export_source(root, root / "unsafe.zip")
            self.assertFalse((root / "unsafe.zip").exists())

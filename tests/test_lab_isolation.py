import tempfile
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.manage_lab import prepare, inventory, retire, checked_root
from scripts.manage_lab import attach_iso, ISO_NAME


class LabIsolationTest(unittest.TestCase):
    def test_iso_attachment_requires_checksum_and_powered_off_vm(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "TiaobeiLab"
            prepare(root, create_python=False)
            iso = root / "iso" / ISO_NAME
            iso.write_bytes(b"synthetic iso fixture")
            vmx = root / "vm/kylin-v11.vmx"
            before = vmx.read_bytes()
            with self.assertRaisesRegex(ValueError, "checksum"):
                attach_iso(root)
            self.assertEqual(vmx.read_bytes(), before)
            with patch("scripts.manage_lab.ISO_SHA256", hashlib.sha256(iso.read_bytes()).hexdigest()):
                lock = root / "vm/system.vmdk.lck"
                lock.mkdir()
                with self.assertRaisesRegex(ValueError, "lock"):
                    attach_iso(root)
                lock.rmdir()
                self.assertTrue(attach_iso(root)["attached"])
                self.assertIn('ethernet0.present = "FALSE"', vmx.read_text())
                with self.assertRaisesRegex(ValueError, "already exists"):
                    attach_iso(root)

    def test_owned_lab_is_offline_and_retirement_is_recoverable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "TiaobeiLab"
            prepare(root, create_python=False)
            vmx = (root / "vm/kylin-v11.vmx").read_text(encoding="utf-8")
            self.assertIn('ethernet0.present = "FALSE"', vmx)
            self.assertIn('isolation.tools.hgfs.disable = "TRUE"', vmx)
            with self.assertRaises(ValueError):
                retire(root, "wrong")
            state = inventory(root)
            moved = retire(root, state["inventory_sha256"])
            self.assertTrue(Path(moved["retired_to"]).is_dir())
            self.assertFalse(root.exists())

    def test_refuses_foreign_directory_unknown_files_and_running_vm(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                checked_root(folder, require_marker=False)
            root = Path(folder) / "TiaobeiLab"
            prepare(root, create_python=False)
            (root / "personal.txt").touch()
            with self.assertRaises(ValueError):
                inventory(root)
            (root / "personal.txt").unlink()
            (root / "vm/system.vmdk.lck").mkdir()
            with self.assertRaises(ValueError):
                inventory(root)

import tempfile
import unittest
from pathlib import Path
from scripts.manage_lab import prepare, inventory, retire, checked_root


class LabIsolationTest(unittest.TestCase):
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

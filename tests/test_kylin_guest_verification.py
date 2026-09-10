import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_kylin_guest", ROOT / "scripts/verify_kylin_guest.py")
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class KylinGuestVerificationTest(unittest.TestCase):
    def test_live_and_missing_roots_are_rejected(self):
        for value in ("", "overlay overlay", "/dev/loop0 squashfs",
                      "/dev/sr0 iso9660", "/dev/ram0 ext4", "/dev/sda2", "/dev/sda2 overlay"):
            with self.subTest(value=value):
                self.assertFalse(guest.installed_root(value))
        self.assertTrue(guest.installed_root("/dev/sda2 ext4\n"))
        self.assertTrue(guest.installed_root("/dev/mapper/root btrfs"))

    def test_success_requires_v11_disk_install_and_all_checks(self):
        report = {"installed": True, "required_v11_verified": True, "core_checks_passed": True}
        self.assertTrue(guest.guest_passed(report))
        for key in report:
            self.assertFalse(guest.guest_passed({**report, key: False}))
        self.assertFalse(guest.guest_passed({}))
        self.assertIn("request_metrics", guest.CORE_CHECKS)
        self.assertIn("service_workload", guest.CORE_CHECKS)
        self.assertIn("ablations", guest.CORE_CHECKS)
        self.assertNotIn("action_readiness", guest.CORE_CHECKS)

    def test_transfer_hashes_and_cross_platform_hashes_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            path = root / "src/example.py"
            path.write_bytes(b"answer = 42\r\n")
            windows = guest.file_hashes(root)
            path.write_bytes(b"answer = 42\n")
            linux = guest.file_hashes(root)
        self.assertNotEqual(windows["raw_sha256"], linux["raw_sha256"])
        self.assertEqual(windows["lf_sha256"], linux["lf_sha256"])

    def test_only_known_generated_report_is_excluded_from_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data/eval"
            data.mkdir(parents=True)
            (data / "latest_report.json").write_text("{}", encoding="utf-8")
            (data / "frozen_report.json").write_text("{}", encoding="utf-8")
            development = root / "data/dev"
            development.mkdir()
            (development / "suite.json").write_text("{}", encoding="utf-8")
            snapshot = guest.file_hashes(root)
        self.assertEqual(set(snapshot["raw_sha256"]), {"data/eval/frozen_report.json", "data/dev/suite.json"})
        self.assertEqual(snapshot["excluded_generated_outputs"], ["data/eval/latest_report.json"])


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.verify_release import _is_probability_metric, scan_sensitive_text

FRACTION = repr(1 / 24)
MEMBER = '"no_answer_accuracy": ' + FRACTION


class MetricPrivacyTest(unittest.TestCase):
    def test_only_typed_unit_interval_probability_members_are_recognized(self):
        self.assertTrue(_is_probability_metric(MEMBER + ",", "report.json"))
        for line, name in (
            ('"no_answer_accuracy": "' + FRACTION + '",', "report.json"),
            ('"no_answer_accuracy": 11010519491231002,', "report.json"),
            ('"no_answer_accuracy": ' + repr(1 + 1 / 24) + ',', "report.json"),
            ('"no_answer_accuracy": NaN,', "report.json"),
            ('"no_answer_accuracy": Infinity,', "report.json"),
            ('"private_value": ' + FRACTION + ',', "report.json"),
            (MEMBER + ",", "notes.md"),
            (MEMBER + ', "other": "secret"', "report.json"),
        ):
            with self.subTest(line=line, name=name):
                self.assertFalse(_is_probability_metric(line, name))

    def test_fraction_is_explained_but_same_digits_in_strings_still_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "report.json"
            path.write_text('{\n' + MEMBER + '\n}\n', encoding="utf-8")
            report = scan_sensitive_text(root, [path])
            self.assertTrue(report["passed"])
            self.assertEqual(len(report["approved_numeric_metric_findings"]), 1)
            path.write_text('{\n"no_answer_accuracy": "' + FRACTION + '"\n}\n', encoding="utf-8")
            report = scan_sensitive_text(root, [path])
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["unexpected_findings"]), 1)

    def test_nested_archive_member_receives_the_same_narrow_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("report.json", '{\n' + MEMBER + '\n}')
                archive.writestr("unsafe.json", '{\n"no_answer_accuracy": "' + FRACTION.partition(".")[2] + '"\n}')
            report = scan_sensitive_text(root, [path])
            self.assertEqual(len(report["approved_numeric_metric_findings"]), 1)
            self.assertEqual(len(report["unexpected_findings"]), 1)

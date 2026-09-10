from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.verify_release import _is_probability_metric, _is_submillisecond_metric, scan_sensitive_text

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
            ('"no_answer_accuracy": "' + FRACTION + '", ' + MEMBER, "report.json"),
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

    def test_render_ink_fraction_is_numeric_but_identifiers_remain_blocked(self):
        fraction = FRACTION
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "render.json"
            path.write_text('{\n"ink_fraction": ' + fraction + '\n}', encoding="utf-8")
            report = scan_sensitive_text(root, [path])
            self.assertTrue(report["passed"])
            self.assertEqual(len(report["approved_numeric_metric_findings"]), 1)
            for key, value in (("ink_fraction", '"' + fraction + '"'),
                               ("ink_fraction", "1" * 18),
                               ("ink_fraction", "1" + fraction[1:]),
                               ("ink_fraction", "-" + fraction),
                               ("identifier", fraction)):
                with self.subTest(key=key, value=value):
                    path.write_text('{\n"' + key + '": ' + value + '\n}', encoding="utf-8")
                    self.assertFalse(scan_sensitive_text(root, [path])["passed"])

    def test_submillisecond_duration_is_typed_and_bounded_not_an_identifier_exemption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "timing.json"
            path.write_text('{\n"elapsed_ms": ' + FRACTION + '\n}', encoding="utf-8")
            report = scan_sensitive_text(root, [path])
            self.assertTrue(report["passed"])
            self.assertEqual(len(report["approved_numeric_metric_findings"]), 1)
            for member in (
                '"elapsed_ms": "' + FRACTION + '"',
                '"elapsed_ms": ' + "1" * 18,
                '"elapsed_ms": -' + FRACTION,
                '"elapsed_ms": 1' + FRACTION[1:],
                '"identifier": ' + FRACTION,
                '"elapsed_ms": "' + FRACTION + '", "elapsed_ms": ' + FRACTION,
                '"elapsed_ms": ' + FRACTION + ', "identifier": "' + FRACTION + '"',
                '"elapsed_ms": NaN, "identifier": "' + FRACTION + '"',
                '"elapsed_ms": Infinity, "identifier": "' + FRACTION + '"',
                '"elapsed_ms": true, "identifier": "' + FRACTION + '"',
            ):
                with self.subTest(member=member):
                    path.write_text('{\n' + member + '\n}', encoding="utf-8")
                    self.assertFalse(scan_sensitive_text(root, [path])["passed"])
            path = root / "timing.md"
            path.write_text('"elapsed_ms": ' + FRACTION, encoding="utf-8")
            self.assertFalse(scan_sensitive_text(root, [path])["passed"])

    def test_duration_keys_and_invalid_numbers_cannot_widen_the_exception(self):
        for key in ("elapsed_ms", "first_query_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"):
            with self.subTest(key=key):
                self.assertTrue(_is_submillisecond_metric('"' + key + '": ' + FRACTION, "report.json"))
                for value in ("NaN", "Infinity", "true", "0", "1", "1" + FRACTION[1:], "-" + FRACTION):
                    self.assertFalse(_is_submillisecond_metric('"' + key + '": ' + value, "report.json"))
        self.assertFalse(_is_submillisecond_metric('"identifier_ms": ' + FRACTION, "report.json"))

    def test_duration_archive_member_keeps_strings_and_other_secret_types_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("timing.json", '{\n"elapsed_ms": ' + FRACTION + '\n}')
                archive.writestr("unsafe.json", '{\n"elapsed_ms": "' + FRACTION + '"\n}')
                archive.writestr("secret.json", '{\n"elapsed_ms": "ghp_' + "A" * 36 + '"\n}')
            report = scan_sensitive_text(root, [path])
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["approved_numeric_metric_findings"]), 1)
            self.assertEqual({row["kind"] for row in report["unexpected_findings"]},
                             {"cn_id", "service_token"})

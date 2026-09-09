from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.bounded_command import CommandFailure, run_bounded


class BoundedCommandTest(unittest.TestCase):
    def command(self, program, **kwargs):
        return run_bounded([sys.executable, "-X", "utf8", "-S", "-c", program], **kwargs)

    def test_exact_limit_and_utf8_are_preserved(self):
        result = self.command("import sys; sys.stdout.buffer.write(b'x' * 65536)")
        self.assertEqual(len(result.stdout), 65536)
        self.assertEqual(self.command("print('\\u4e2d\\u6587')").stdout.strip(), "\u4e2d\u6587")

    def test_large_stdin_and_stdout_do_not_deadlock(self):
        value = "y" * (128 * 1024)
        result = self.command("import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data)",
                              input=value, max_stdout=128 * 1024)
        self.assertEqual(result.stdout, value)

    def test_both_output_streams_are_bounded(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream), self.assertRaisesRegex(CommandFailure, "command_output_limit"):
                self.command(f"import sys; sys.{stream}.buffer.write(b'x' * (1024 * 1024))")

    def test_timeout_reaps_process_and_unblocks_stdin_writer(self):
        start = time.monotonic()
        with self.assertRaisesRegex(CommandFailure, "command_timeout"):
            self.command("import time; time.sleep(30)", input="x" * (2 * 1024 * 1024), timeout=.2)
        self.assertLess(time.monotonic() - start, 4)

    def test_failed_output_is_not_in_exception(self):
        with self.assertRaises(CommandFailure) as caught:
            self.command("import sys; print('private-prompt'); sys.exit(2)")
        self.assertEqual(str(caught.exception), "command_nonzero_exit")
        self.assertNotIn("private-prompt", repr(caught.exception))

    def test_explicit_nonzero_capture_preserves_private_diagnostic_without_weakening_limits(self):
        result = self.command("import sys; print('private-result'); sys.exit(2)", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "private-result")
        with self.assertRaisesRegex(CommandFailure, "command_output_limit"):
            self.command("print('x' * 100000)", check=False)
        with self.assertRaises(ValueError):
            self.command("pass", check=0)

    def test_invalid_utf8_and_command_budgets_are_rejected(self):
        with self.assertRaisesRegex(CommandFailure, "command_invalid_utf8"):
            self.command("import sys; sys.stdout.buffer.write(b'\\xff')")
        for timeout in (True, float("nan"), float("inf"), 0, 601):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.command("pass", timeout=timeout)
        for argv in ("shell command", [], ["bad\x00argument"]):
            with self.assertRaises(ValueError):
                run_bounded(argv)
        with self.assertRaises(ValueError):
            self.command("pass", input="x" * (4 * 1024 * 1024 + 1))


if __name__ == "__main__":
    unittest.main()

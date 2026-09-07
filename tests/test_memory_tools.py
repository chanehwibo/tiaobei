import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.file_memory import WriteContext
from os_agent_memory.memory_tools import MemoryTools, LocalIndexSelector

CONTEXT = WriteContext(True, "session", "2026-09-07T08:00:00+00:00")


class MemoryToolsTest(unittest.TestCase):
    def seed(self, tools, slug="style"):
        return tools.store.write(kind="user", slug=slug, name="表达"+slug, description="中文简洁输出", body="采用简洁中文输出。", context=CONTEXT)

    def test_missing_invalid_or_timeout_selector_reads_no_body(self):
        with tempfile.TemporaryDirectory() as folder:
            tools = MemoryTools(folder)
            self.seed(tools)
            for selector in (None, lambda q, h: ["../../private"], lambda q,h: "bad"):
                tools.selector = selector
                with patch.object(tools.store, "read", side_effect=AssertionError("body read")) as read:
                    self.assertIn("returned=0", tools.memory_recall("中文"))
                    read.assert_not_called()
            done = Event()
            tools.selector = lambda q,h: done.wait(2)
            tools.timeout_seconds = .01
            try:
                self.assertIn("returned=0", tools.memory_recall("中文"))
                self.assertIn("returned=0", tools.memory_recall("中文"))
            finally:
                done.set()

    def test_max_five_budget_and_exact_tool_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            tools = MemoryTools(folder, selector=lambda q,h: [r["key"] for r in h])
            for i in range(7):
                self.seed(tools, f"style-{i}")
            self.assertIn("returned=5", tools.memory_recall("中文"))
            tools.max_bytes = 256
            self.assertLessEqual(len(tools.memory_recall("中文").encode()), 256)
            with self.assertRaises(ValueError):
                tools.dispatch("memory_recall", {"query": "中文", "workspace": "other"}, context=CONTEXT)

    def test_ambiguous_forget_never_bulk_deletes_or_accepts_stale_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            tools = MemoryTools(folder, selector=LocalIndexSelector())
            first = self.seed(tools, "one")
            self.seed(tools, "two")
            plan = tools.forget_preview("中文")
            self.assertEqual(len(plan["candidates"]), 2)
            tools.forget_confirm(plan["confirmation_token"], first["key"], context=CONTEXT)
            self.assertEqual(len(tools.store.headers()), 1)
            with self.assertRaises(ValueError):
                tools.forget_confirm(plan["confirmation_token"], first["key"], context=CONTEXT)

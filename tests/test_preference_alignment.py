import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.ingestion import DataIngestionPipeline
from os_agent_memory.preference import PreferenceExtractor
from os_agent_memory.service import MemoryService


class PreferenceAlignmentTest(unittest.TestCase):
    def extract(self, text):
        records = DataIngestionPipeline().ingest([{"id": "explicit", "source_type": "manual_config", "content": text,
            "metadata": {"title": "显式偏好"}, "timestamp": "2026-09-07T08:00:00+00:00"}])
        return {p.key: p.value for p in PreferenceExtractor().extract(records)}

    def test_negation_verbs_and_last_explicit_correction(self):
        self.assertEqual(self.extract("不要用表格，请采用纯文本输出。"), {"output.format": "plain_text"})
        self.assertEqual(self.extract("不需要提供表格，请输出JSON。"), {"output.format": "json"})
        self.assertEqual(self.extract("原来用英文，现在使用中文输出。"), {"output.language": "zh-CN"})
        self.assertEqual(self.extract("请用中文，现在改为英文输出。"), {"output.language": "en"})
        self.assertEqual(self.extract("不要详细展开说明，直接给结论。"), {"output.verbosity": "brief"})

    def test_multiple_attributes_and_existing_lifecycle_gate(self):
        result = self.extract("请使用中文，分步骤解释，并用Markdown格式输出。")
        self.assertEqual(result, {"output.language": "zh-CN", "output.structure": "step_by_step", "output.format": "markdown"})
        service = MemoryService()
        service.ingest([{"id": "weak", "source_type": "session_context", "content": "这次临时用表格对比即可。", "metadata": {"topic": "temporary"}}])
        self.assertEqual(service.store.preferences, {})

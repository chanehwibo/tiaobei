import sys
import unittest
import json
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

    def test_mentions_quotation_and_negation_scope(self):
        for text in ("我不希望回答里出现英文。", "不要把回复做成JSON。",
                     "不要英文或JSON格式。", "请解释JSON与Markdown的区别。",
                     "这里引用一句话：请用英文回答。不要将引文作为我的偏好。",
                     "日志包含离线安装这几个字。", "他喜欢纯文本，但这不是我的偏好。"):
            with self.subTest(text=text):
                self.assertEqual(self.extract(text), {})
        self.assertEqual(self.extract("请用英文解释JSON与Markdown的区别。"), {"output.language": "en"})
        self.assertEqual(self.extract("Don't use English or JSON. Please use Chinese."),
                         {"output.language": "zh-CN"})
        self.assertEqual(self.extract("请不要用表格而是改用纯文本输出。"), {"output.format": "plain_text"})

    def test_explicit_setting_survives_later_repeated_behavior_and_restart(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "memory.db"
            service = MemoryService(database_path=database)
            common = {"tenant_id": "t", "user_id": "u", "metadata": {"topic": "format"}}
            service.ingest([{**common, "id": "manual", "source_type": "manual_config",
                             "content": "今后的回复请使用纯文本格式。", "timestamp": "2026-09-01T00:00:00Z"}])
            for i in range(3):
                service.ingest([{**common, "id": f"behavior-{i}", "source_type": "user_behavior",
                                 "scene": "office", "content": "用户多次选择表格查看财务明细。",
                                 "timestamp": f"2026-09-0{i + 2}T00:00:00Z"}])
            service = MemoryService(database_path=database)
            self.assertEqual(service.preferences(tenant_id="t", user_id="u")[0]["value"], "plain_text")
            service.ingest([{**common, "id": "revision", "source_type": "manual_config",
                             "content": "现在明确改用JSON输出格式。", "timestamp": "2026-09-06T00:00:00Z"}])
            self.assertEqual(service.preferences(tenant_id="t", user_id="u")[0]["value"], "json")
            self.assertEqual(service.preferences(tenant_id="t", user_id="another"), [])

    def test_reaffirmed_explicit_setting_rejects_out_of_order_change(self):
        from os_agent_memory.memory_store import MemoryStore
        store = MemoryStore()
        for index, (day, value) in enumerate(((1, "JSON"), (5, "JSON"), (3, "Markdown"))):
            records = DataIngestionPipeline().ingest([{
                "id": str(index), "source_type": "manual_config",
                "content": f"请将后续所有回复设置为{value}格式输出。",
                "timestamp": f"2026-09-0{day}T00:00:00Z", "metadata": {"topic": str(index)},
            }])
            for preference in PreferenceExtractor().extract(records):
                store.upsert_preference(preference)
        self.assertEqual(store.get_preference("default", "default_user", "output.format").value, "json")

    def test_frozen_request_preferences_and_durable_safety(self):
        from os_agent_memory.request_evaluation import evaluate_preferences
        suite = json.loads((Path(__file__).resolve().parents[1] / "data/eval/request_regression_v1.json")
                           .read_text(encoding="utf-8"))
        result = evaluate_preferences(suite["preferences"])
        self.assertGreaterEqual(result["accuracy"], .85)
        self.assertTrue(result["durable_checks_passed"])

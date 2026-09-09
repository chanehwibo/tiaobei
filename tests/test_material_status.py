from pathlib import Path
import unittest

from scripts.material_status import INITIAL_STATUS


ROOT = Path(__file__).resolve().parents[1]
CURRENT_DOCUMENTS = (
    "README.md",
    "docs/03_评测方案.md",
    "docs/04_提交材料清单.md",
    "docs/06_测试矩阵.md",
    "docs/08_演示快跑指南.md",
    "docs/09_技术方案正文.md",
    "docs/10_PPT逐页讲稿与答辩问答.md",
    "docs/11_演示视频分镜与录制检查表.md",
    "docs/14_可复现指南.md",
    "docs/演示操作手册.md",
    "docs/测试报告.md",
    "docs/37_出题方反馈落实.md",
    "submission/README.md",
)


class MaterialStatusTest(unittest.TestCase):
    def test_current_documents_use_initial_status_without_legacy_headlines(self):
        for relative in CURRENT_DOCUMENTS:
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(INITIAL_STATUS, text)
                for obsolete in ("INCOMPLETE", "第五轮", "未完成"):
                    self.assertNotIn(obsolete, text)

    def test_initial_wording_does_not_claim_competition_acceptance(self):
        for relative in ("README.md", "docs/37_出题方反馈落实.md", "submission/README.md"):
            with self.subTest(path=relative):
                self.assertIn("待赛事验收", (ROOT / relative).read_text(encoding="utf-8"))

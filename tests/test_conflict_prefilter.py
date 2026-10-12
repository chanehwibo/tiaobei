import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from os_agent_memory.memory_store import MemoryStore
from os_agent_memory.schemas import MemoryStatus
from tests.test_evidence_constraints import document


class ConflictPrefilterTest(unittest.TestCase):
    def test_nonconflicting_bulk_ingestion_skips_pairwise_rule_checks(self):
        store = MemoryStore()
        with patch.object(store, "_has_contradiction", wraps=store._has_contradiction) as check:
            for index in range(100):
                store.upsert_knowledge(document(str(index), f"任务{index}流程：登记材料并保留记录。"))
            self.assertEqual(check.call_count, 0)
        self.assertEqual(len(store.knowledge), 100)

    def test_all_polarity_pairs_match_the_original_exhaustive_decision(self):
        for positive, negative in MemoryStore.CONTRADICTION_PAIRS:
            for left, right in ((positive, negative), (negative, positive)):
                with self.subTest(left=left, right=right):
                    store = MemoryStore()
                    old = document("old", f"资料归档流程{left}文件并记录审核。")
                    new = document("new", f"资料归档流程{right}文件并记录审核。")
                    store.upsert_knowledge(old)
                    expected = store._has_contradiction(new.content, old.content)
                    result = store.upsert_knowledge(new)
                    self.assertEqual(result.conflict_with, ["old"] if expected else [])

    def test_numeric_conditions_still_use_complete_conflict_checks(self):
        store = MemoryStore()
        store.upsert_knowledge(document("old", "审批时限为3天。"))
        self.assertEqual(store.upsert_knowledge(document("new", "审批时限为5天。" )).conflict_with, ["old"])

    def test_replacement_rebuild_and_forgetting_keep_candidate_index_consistent(self):
        store = MemoryStore()
        store.upsert_knowledge(document("old", "归档流程允许读取文件并保留记录。"))
        store.upsert_knowledge(document("old", "归档流程禁止读取文件并保留记录。"))
        store.rebuild_index()
        candidate = document("new", "归档流程允许读取文件并保留记录。")
        self.assertEqual(store._find_conflicts(candidate), ["old"])
        store.knowledge["old"].status = MemoryStatus.FORGOTTEN
        store.rebuild_index()
        self.assertEqual(store._find_conflicts(candidate), [])


if __name__ == "__main__":
    unittest.main()

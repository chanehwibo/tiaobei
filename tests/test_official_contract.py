import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.official_contract import TARGETS, assess_official_metrics, environment_identity


class OfficialContractTest(unittest.TestCase):
    def test_requires_galaxy_v11_not_name_similarity(self):
        for system, release in (
            ("Windows", {"ID": "kylin", "VERSION_ID": "11"}),
            ("Linux", {"ID": "openkylin", "VERSION_ID": "11"}),
            ("Linux", {"ID": "neokylin", "VERSION_ID": "11"}),
            ("Linux", {"ID": "kylin", "VERSION_ID": "10"}),
            ("Linux", {"ID": "kylin", "VERSION_ID": "110"}),
        ):
            self.assertFalse(environment_identity(system, release)["is_required_v11"])
        self.assertTrue(environment_identity("Linux", {"ID": "kylin", "VERSION_ID": "V11"})["is_required_v11"])

    def test_both_85_are_preference_and_recall_and_all_five_are_required(self):
        metrics = {key: target for key, (_, target) in TARGETS.items()}
        counts = {key: 50 for key in TARGETS}
        self.assertTrue(assess_official_metrics(metrics, counts)["all_targets_met"])
        for name in TARGETS:
            self.assertFalse(assess_official_metrics(metrics, {**counts, name: 49})["all_targets_met"])
            self.assertFalse(assess_official_metrics({**metrics, name: None}, counts)["all_targets_met"])
        self.assertFalse(assess_official_metrics({"knowledge_recall": 1, "no_answer_accuracy": 1}, counts)["all_targets_met"])
        self.assertFalse(assess_official_metrics({**metrics, "preference_accuracy": float("nan")}, counts)["all_targets_met"])

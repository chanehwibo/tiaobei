import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.provider_config import CheckedProvider
from os_agent_memory.service import MemoryService
from os_agent_memory.workload import workload_event


class ProviderConfigTest(unittest.TestCase):
    def test_dimension_change_invalidates_persisted_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.sqlite"
            service = MemoryService(database_path=path, embedding_config={"dimensions": 16})
            service.ingest([workload_event(0)])
            reloaded = MemoryService(database_path=path, embedding_config={"dimensions": 32})
            self.assertTrue(all(len(m.embedding) == 32 for m in reloaded.store.knowledge.values()))
            self.assertTrue(reloaded.search("task00000", tenant_id="load", user_id="operator"))

    def test_invalid_vector_fails_and_timeout_does_not_spawn_unbounded_workers(self):
        class Invalid:
            def encode(self, text):
                return [float("nan"), 1]
        with self.assertRaises(ValueError):
            CheckedProvider(Invalid(), dimensions=2, identity={}).encode("probe")
        released = Event()
        class Slow:
            def encode(self, text):
                released.wait(2)
                return [1., 0.]
        provider = CheckedProvider(Slow(), dimensions=2, identity={}, timeout_seconds=.01)
        try:
            with self.assertRaises(TimeoutError):
                provider.encode("probe")
            with self.assertRaises(RuntimeError):
                provider.encode("probe")
        finally:
            released.set()

import sys
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from threading import Event
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from os_agent_memory.provider_config import CheckedProvider
from os_agent_memory.service import MemoryService
from os_agent_memory.workload import workload_event
from os_agent_memory.memory_store import MemoryStore
from os_agent_memory.persistence import SQLiteMemoryPersistence
from os_agent_memory.schemas import KnowledgeMemory


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

    def test_old_text_normalization_invalidates_vectors_without_changing_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.sqlite"
            store = MemoryStore()
            item = KnowledgeMemory(
                id="wide", title="PDF", content="ＩＮＶＯＩＣＥ　ＰＤＦ　ｅｘｐｏｒｔ",
                tags=[], source_ids=["source"], version=1,
                created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z")
            store.upsert_knowledge(item)
            persistence = SQLiteMemoryPersistence(path)
            persistence.save(store)
            with closing(sqlite3.connect(path)) as connection:
                with connection:
                    connection.execute("DELETE FROM runtime_state WHERE key='search_text_normalization'")
                    connection.execute("UPDATE knowledge SET embedding='[0.0]'")
            loaded = persistence.load()
            self.assertEqual(loaded.knowledge["wide"].content, item.content)
            self.assertEqual(loaded.knowledge["wide"].embedding, item.embedding)
            self.assertEqual(loaded.search_knowledge("invoice pdf export")[0].memory_id, "wide")
            persistence.save(loaded)
            reloaded = persistence.load()
            self.assertEqual(reloaded.runtime_state["search_text_normalization"], MemoryStore.SEARCH_TEXT_NORMALIZATION)

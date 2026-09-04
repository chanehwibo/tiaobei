from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .embeddings import HashEmbedding
from .memory_store import MemoryStore
from .schemas import KnowledgeMemory, MemoryStatus, PreferenceMemory


class SQLiteMemoryPersistence:
    """Persist prototype memories to a local SQLite database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, store: MemoryStore) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            self._initialize(connection)
            with connection:
                connection.execute("DELETE FROM preferences")
                connection.execute("DELETE FROM preference_history")
                connection.execute("DELETE FROM knowledge")
                connection.executemany(
                    """
                    INSERT INTO preferences
                    (user_id, key, id, value, confidence, version, scenes, evidence_ids, updated_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [_preference_row(memory) for memory in store.preferences.values()],
                )
                connection.executemany(
                    """
                    INSERT INTO preference_history
                    (row_order, user_id, key, id, value, confidence, version, scenes, evidence_ids, updated_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (index, *_preference_row(memory))
                        for index, memory in enumerate(store.preference_history, start=1)
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO knowledge
                    (id, title, content, tags, source_ids, version, created_at, updated_at, status, conflict_with)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [_knowledge_row(memory) for memory in store.knowledge.values()],
                )

    def load(self, embedding: HashEmbedding | None = None) -> MemoryStore:
        store = MemoryStore(embedding=embedding)
        if not self.path.exists():
            return store

        with closing(sqlite3.connect(self.path)) as connection:
            self._initialize(connection)
            for row in connection.execute(
                """
                SELECT user_id, key, id, value, confidence, version, scenes, evidence_ids, updated_at, status
                FROM preferences
                """
            ):
                memory = _preference_from_row(row)
                store.preferences[(memory.tenant_id, memory.user_id, memory.key)] = memory

            for row in connection.execute(
                """
                SELECT user_id, key, id, value, confidence, version, scenes, evidence_ids, updated_at, status
                FROM preference_history
                ORDER BY row_order
                """
            ):
                store.preference_history.append(_preference_from_row(row))

            for row in connection.execute(
                """
                SELECT id, title, content, tags, source_ids, version, created_at, updated_at, status, conflict_with
                FROM knowledge
                """
            ):
                memory = _knowledge_from_row(row)
                store.knowledge[memory.id] = memory

        store.rebuild_index()

        return store

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                id TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL,
                version INTEGER NOT NULL,
                scenes TEXT NOT NULL,
                evidence_ids TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS preference_history (
                row_order INTEGER PRIMARY KEY,
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                id TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL,
                version INTEGER NOT NULL,
                scenes TEXT NOT NULL,
                evidence_ids TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT NOT NULL,
                source_ids TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                conflict_with TEXT NOT NULL
            )
            """
        )


def _preference_row(memory: PreferenceMemory) -> tuple[str, str, str, str, float, int, str, str, str, str]:
    return (
        memory.user_id,
        memory.key,
        memory.id,
        memory.value,
        memory.confidence,
        memory.version,
        json.dumps(memory.scenes, ensure_ascii=False),
        json.dumps(memory.evidence_ids, ensure_ascii=False),
        memory.updated_at,
        memory.status.value,
    )


def _knowledge_row(memory: KnowledgeMemory) -> tuple[str, str, str, str, str, int, str, str, str, str]:
    return (
        memory.id,
        memory.title,
        memory.content,
        json.dumps(memory.tags, ensure_ascii=False),
        json.dumps(memory.source_ids, ensure_ascii=False),
        memory.version,
        memory.created_at,
        memory.updated_at,
        memory.status.value,
        json.dumps(memory.conflict_with, ensure_ascii=False),
    )


def _preference_from_row(row: tuple[object, ...]) -> PreferenceMemory:
    return PreferenceMemory(
        user_id=str(row[0]),
        key=str(row[1]),
        id=str(row[2]),
        value=str(row[3]),
        confidence=float(row[4]),
        version=int(row[5]),
        scenes=[str(item) for item in json.loads(str(row[6]))],
        evidence_ids=[str(item) for item in json.loads(str(row[7]))],
        updated_at=str(row[8]),
        status=MemoryStatus(str(row[9])),
    )


def _knowledge_from_row(row: tuple[object, ...]) -> KnowledgeMemory:
    return KnowledgeMemory(
        id=str(row[0]),
        title=str(row[1]),
        content=str(row[2]),
        tags=[str(item) for item in json.loads(str(row[3]))],
        source_ids=[str(item) for item in json.loads(str(row[4]))],
        version=int(row[5]),
        created_at=str(row[6]),
        updated_at=str(row[7]),
        status=MemoryStatus(str(row[8])),
        conflict_with=[str(item) for item in json.loads(str(row[9]))],
    )

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .embeddings import EmbeddingProvider
from .memory_store import MemoryStore
from .schemas import AuditEvent, KnowledgeMemory, MemoryStatus, MemoryTier, PreferenceMemory


SCHEMA_VERSION = 2


class SQLiteMemoryPersistence:
    """Persist scoped memory, vector caches and audit evidence in SQLite."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, store: MemoryStore) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            self._initialize(connection)
            with connection:
                for table in (
                    "preferences",
                    "preference_history",
                    "knowledge",
                    "audit_events",
                    "conflict_decisions",
                ):
                    connection.execute(f"DELETE FROM {table}")
                connection.executemany(
                    """
                    INSERT INTO preferences
                    (tenant_id, user_id, key, id, value, confidence, version, scenes, evidence_ids,
                     updated_at, status, valid_from, valid_to, tier, score_components)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [_preference_row(memory) for memory in store.preferences.values()],
                )
                connection.executemany(
                    """
                    INSERT INTO preference_history
                    (row_order, tenant_id, user_id, key, id, value, confidence, version, scenes,
                     evidence_ids, updated_at, status, valid_from, valid_to, tier, score_components)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (index, *_preference_row(memory))
                        for index, memory in enumerate(store.preference_history, start=1)
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO knowledge
                    (id, title, content, tags, source_ids, version, created_at, updated_at, status,
                     conflict_with, tenant_id, user_id, knowledge_type, scene, authority, privacy_level,
                     valid_from, valid_to, tier, embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [_knowledge_row(memory) for memory in store.knowledge.values()],
                )
                connection.executemany(
                    """
                    INSERT INTO audit_events
                    (row_order, id, action, tenant_id, user_id, target_ids, created_at, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (index, *_audit_row(event))
                        for index, event in enumerate(store.audit_events, start=1)
                    ],
                )
                connection.executemany(
                    "INSERT INTO conflict_decisions (row_order, payload) VALUES (?, ?)",
                    [
                        (index, json.dumps(decision, ensure_ascii=False, sort_keys=True))
                        for index, decision in enumerate(store.conflict_decisions, start=1)
                    ],
                )

    def load(self, embedding: EmbeddingProvider | None = None) -> MemoryStore:
        store = MemoryStore(embedding=embedding)
        if not self.path.exists():
            return store

        with closing(sqlite3.connect(self.path)) as connection:
            self._initialize(connection)
            for row in connection.execute(
                """
                SELECT tenant_id, user_id, key, id, value, confidence, version, scenes, evidence_ids,
                       updated_at, status, valid_from, valid_to, tier, score_components
                FROM preferences
                """
            ):
                memory = _preference_from_row(row)
                store.preferences[(memory.tenant_id, memory.user_id, memory.key)] = memory

            for row in connection.execute(
                """
                SELECT tenant_id, user_id, key, id, value, confidence, version, scenes, evidence_ids,
                       updated_at, status, valid_from, valid_to, tier, score_components
                FROM preference_history ORDER BY row_order
                """
            ):
                store.preference_history.append(_preference_from_row(row))

            for row in connection.execute(
                """
                SELECT id, title, content, tags, source_ids, version, created_at, updated_at, status,
                       conflict_with, tenant_id, user_id, knowledge_type, scene, authority, privacy_level,
                       valid_from, valid_to, tier, embedding
                FROM knowledge
                """
            ):
                memory = _knowledge_from_row(row)
                store.knowledge[memory.id] = memory

            for row in connection.execute(
                """
                SELECT id, action, tenant_id, user_id, target_ids, created_at, details
                FROM audit_events ORDER BY row_order
                """
            ):
                store.audit_events.append(_audit_from_row(row))

            for (payload,) in connection.execute(
                "SELECT payload FROM conflict_decisions ORDER BY row_order"
            ):
                store.conflict_decisions.append(json.loads(str(payload)))

        store.rebuild_index()
        return store

    @classmethod
    def _initialize(cls, connection: sqlite3.Connection) -> None:
        with connection:
            cls._migrate_legacy_tables(connection)
            cls._create_current_tables(connection)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @classmethod
    def _migrate_legacy_tables(cls, connection: sqlite3.Connection) -> None:
        legacy_tables: list[str] = []
        for table in ("preferences", "preference_history", "knowledge"):
            if cls._table_exists(connection, table) and "tenant_id" not in cls._table_columns(connection, table):
                legacy_name = f"{table}_legacy_v1"
                connection.execute(f"ALTER TABLE {table} RENAME TO {legacy_name}")
                legacy_tables.append(table)

        if not legacy_tables:
            return
        cls._create_current_tables(connection)
        if "preferences" in legacy_tables:
            connection.execute(
                """
                INSERT INTO preferences
                (tenant_id, user_id, key, id, value, confidence, version, scenes, evidence_ids,
                 updated_at, status, valid_from, valid_to, tier, score_components)
                SELECT 'default', user_id, key, id, value, confidence, version, scenes, evidence_ids,
                       updated_at, status, updated_at, NULL, 'long', '{}'
                FROM preferences_legacy_v1
                """
            )
            connection.execute("DROP TABLE preferences_legacy_v1")
        if "preference_history" in legacy_tables:
            connection.execute(
                """
                INSERT INTO preference_history
                (row_order, tenant_id, user_id, key, id, value, confidence, version, scenes,
                 evidence_ids, updated_at, status, valid_from, valid_to, tier, score_components)
                SELECT row_order, 'default', user_id, key, id, value, confidence, version, scenes,
                       evidence_ids, updated_at, status, updated_at, NULL, 'long', '{}'
                FROM preference_history_legacy_v1
                """
            )
            connection.execute("DROP TABLE preference_history_legacy_v1")
        if "knowledge" in legacy_tables:
            connection.execute(
                """
                INSERT INTO knowledge
                (id, title, content, tags, source_ids, version, created_at, updated_at, status,
                 conflict_with, tenant_id, user_id, knowledge_type, scene, authority, privacy_level,
                 valid_from, valid_to, tier, embedding)
                SELECT id, title, content, tags, source_ids, version, created_at, updated_at, status,
                       conflict_with, 'default', 'default_user', 'general', 'default', 0.5, 'internal',
                       created_at, NULL, 'long', '[]'
                FROM knowledge_legacy_v1
                """
            )
            connection.execute("DROP TABLE knowledge_legacy_v1")

    @staticmethod
    def _create_current_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                tenant_id TEXT NOT NULL,
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
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                tier TEXT NOT NULL,
                score_components TEXT NOT NULL,
                PRIMARY KEY (tenant_id, user_id, key)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS preference_history (
                row_order INTEGER PRIMARY KEY,
                tenant_id TEXT NOT NULL,
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
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                tier TEXT NOT NULL,
                score_components TEXT NOT NULL
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
                conflict_with TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                knowledge_type TEXT NOT NULL,
                scene TEXT NOT NULL,
                authority REAL NOT NULL,
                privacy_level TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                tier TEXT NOT NULL,
                embedding TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                row_order INTEGER PRIMARY KEY,
                id TEXT NOT NULL UNIQUE,
                action TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                user_id TEXT,
                target_ids TEXT NOT NULL,
                created_at TEXT NOT NULL,
                details TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conflict_decisions (
                row_order INTEGER PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_scope ON knowledge (tenant_id, user_id, scene, status)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_scope ON audit_events (tenant_id, user_id, created_at)")

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone() is not None

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _preference_row(memory: PreferenceMemory) -> tuple[object, ...]:
    return (
        memory.tenant_id,
        memory.user_id,
        memory.key,
        memory.id,
        memory.value,
        memory.confidence,
        memory.version,
        _json(memory.scenes),
        _json(memory.evidence_ids),
        memory.updated_at,
        memory.status.value,
        memory.valid_from or memory.updated_at,
        memory.valid_to,
        memory.tier.value,
        _json(memory.score_components),
    )


def _knowledge_row(memory: KnowledgeMemory) -> tuple[object, ...]:
    return (
        memory.id,
        memory.title,
        memory.content,
        _json(memory.tags),
        _json(memory.source_ids),
        memory.version,
        memory.created_at,
        memory.updated_at,
        memory.status.value,
        _json(memory.conflict_with),
        memory.tenant_id,
        memory.user_id,
        memory.knowledge_type,
        memory.scene,
        memory.authority,
        memory.privacy_level,
        memory.valid_from or memory.created_at,
        memory.valid_to,
        memory.tier.value,
        _json(memory.embedding),
    )


def _audit_row(event: AuditEvent) -> tuple[object, ...]:
    return (
        event.id,
        event.action,
        event.tenant_id,
        event.user_id,
        _json(event.target_ids),
        event.created_at,
        _json(event.details),
    )


def _preference_from_row(row: tuple[object, ...]) -> PreferenceMemory:
    return PreferenceMemory(
        tenant_id=str(row[0]),
        user_id=str(row[1]),
        key=str(row[2]),
        id=str(row[3]),
        value=str(row[4]),
        confidence=float(row[5]),
        version=int(row[6]),
        scenes=[str(item) for item in json.loads(str(row[7]))],
        evidence_ids=[str(item) for item in json.loads(str(row[8]))],
        updated_at=str(row[9]),
        status=MemoryStatus(str(row[10])),
        valid_from=str(row[11]),
        valid_to=str(row[12]) if row[12] is not None else None,
        tier=MemoryTier(str(row[13])),
        score_components={str(key): float(value) for key, value in json.loads(str(row[14])).items()},
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
        tenant_id=str(row[10]),
        user_id=str(row[11]),
        knowledge_type=str(row[12]),
        scene=str(row[13]),
        authority=float(row[14]),
        privacy_level=str(row[15]),
        valid_from=str(row[16]),
        valid_to=str(row[17]) if row[17] is not None else None,
        tier=MemoryTier(str(row[18])),
        embedding=[float(value) for value in json.loads(str(row[19]))],
    )


def _audit_from_row(row: tuple[object, ...]) -> AuditEvent:
    return AuditEvent(
        id=str(row[0]),
        action=str(row[1]),
        tenant_id=str(row[2]),
        user_id=str(row[3]) if row[3] is not None else None,
        target_ids=[str(item) for item in json.loads(str(row[4]))],
        created_at=str(row[5]),
        details=dict(json.loads(str(row[6]))),
    )

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from refengine.domain.models import ProcessedDocument

_SCHEMA_VERSION = 1


class SqliteDocumentRepository:
    """Persist complete processing snapshots transactionally."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_documents (
                    sha256 TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    generated_reference TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(processed_documents)").fetchall()
            }
            if "updated_at" not in columns:
                connection.execute(
                    """
                    ALTER TABLE processed_documents
                    ADD COLUMN updated_at TEXT
                    """
                )
                connection.execute(
                    """
                    UPDATE processed_documents
                    SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)
                    WHERE updated_at IS NULL
                    """
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version)
                VALUES (?)
                """,
                (_SCHEMA_VERSION,),
            )

    def save(self, document: ProcessedDocument) -> None:
        self.save_many([document])

    def save_many(self, documents: list[ProcessedDocument]) -> None:
        """Persist a complete snapshot in one SQLite transaction."""
        rows = [
            (
                document.sha256,
                str(document.source_path),
                document.status.value,
                document.generated_reference,
                document.model_dump_json(),
            )
            for document in documents
        ]
        with self._connection() as connection:
            connection.executemany(
                """
                INSERT INTO processed_documents (
                    sha256,
                    source_path,
                    status,
                    generated_reference,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sha256) DO UPDATE SET
                    source_path = excluded.source_path,
                    status = excluded.status,
                    generated_reference = excluded.generated_reference,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )

    def integrity_check(self) -> str:
        with self._connection() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0] if row is not None else "unknown")

    def count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) FROM processed_documents").fetchone()
        return int(row[0] if row is not None else 0)

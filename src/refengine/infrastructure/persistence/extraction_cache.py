from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from refengine import __version__
from refengine.domain.models import ProcessedDocument

_CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CacheSummary:
    entries: int
    payload_bytes: int
    schema_version: int


class ExtractionCache:
    """Persistent cache for source extraction before review and compilation.

    Cache keys include the source SHA-256, the application version, and an
    explicit processor signature. This intentionally favors correctness over
    aggressive reuse: a new RefEngine release invalidates old extraction data.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS extraction_cache (
                    cache_key TEXT PRIMARY KEY,
                    source_sha256 TEXT NOT NULL,
                    app_version TEXT NOT NULL,
                    processor_signature TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_extraction_cache_source
                ON extraction_cache(source_sha256)
                """
            )
            connection.execute(
                """
                INSERT INTO cache_metadata(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(_CACHE_SCHEMA_VERSION),),
            )
            connection.execute(
                "DELETE FROM extraction_cache WHERE app_version <> ?",
                (__version__,),
            )

    def get(
        self,
        source_sha256: str,
        processor_signature: str,
    ) -> ProcessedDocument | None:
        cache_key = self._cache_key(source_sha256, processor_signature)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM extraction_cache
                WHERE cache_key = ?
                  AND app_version = ?
                  AND processor_signature = ?
                """,
                (cache_key, __version__, processor_signature),
            ).fetchone()
            if row is None:
                return None
            try:
                document = ProcessedDocument.model_validate_json(str(row["payload_json"]))
            except (ValidationError, ValueError, TypeError):
                connection.execute(
                    "DELETE FROM extraction_cache WHERE cache_key = ?",
                    (cache_key,),
                )
                return None
            connection.execute(
                """
                UPDATE extraction_cache
                SET last_used_at = ?
                WHERE cache_key = ?
                """,
                (datetime.now(UTC).isoformat(), cache_key),
            )
            return document

    def put(
        self,
        document: ProcessedDocument,
        processor_signature: str,
    ) -> None:
        if document.status.value == "failed":
            return
        payload = document.model_dump_json()
        now = datetime.now(UTC).isoformat()
        cache_key = self._cache_key(document.sha256, processor_signature)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO extraction_cache (
                    cache_key,
                    source_sha256,
                    app_version,
                    processor_signature,
                    payload_json,
                    payload_bytes,
                    created_at,
                    last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    payload_bytes = excluded.payload_bytes,
                    last_used_at = excluded.last_used_at
                """,
                (
                    cache_key,
                    document.sha256,
                    __version__,
                    processor_signature,
                    payload,
                    len(payload.encode("utf-8")),
                    now,
                    now,
                ),
            )

    def summary(self) -> CacheSummary:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS entries,
                       COALESCE(SUM(payload_bytes), 0) AS payload_bytes
                FROM extraction_cache
                """
            ).fetchone()
            version_row = connection.execute(
                "SELECT value FROM cache_metadata WHERE key = 'schema_version'"
            ).fetchone()
        return CacheSummary(
            entries=int(row["entries"] if row is not None else 0),
            payload_bytes=int(row["payload_bytes"] if row is not None else 0),
            schema_version=int(version_row["value"] if version_row is not None else 0),
        )

    def clear(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS entries FROM extraction_cache").fetchone()
            count = int(row["entries"] if row is not None else 0)
            connection.execute("DELETE FROM extraction_cache")
        return count

    def prune(self, max_entries: int = 1000) -> int:
        if max_entries < 0:
            raise ValueError("max_entries must be non-negative")
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS entries FROM extraction_cache").fetchone()
            count = int(row["entries"] if row is not None else 0)
            remove_count = max(0, count - max_entries)
            if remove_count:
                connection.execute(
                    """
                    DELETE FROM extraction_cache
                    WHERE cache_key IN (
                        SELECT cache_key
                        FROM extraction_cache
                        ORDER BY last_used_at ASC
                        LIMIT ?
                    )
                    """,
                    (remove_count,),
                )
            return remove_count

    def integrity_check(self) -> str:
        with self._connection() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0] if row is not None else "unknown")

    @staticmethod
    def signature(payload: dict[str, object]) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _cache_key(source_sha256: str, processor_signature: str) -> str:
        payload = f"{__version__}\0{source_sha256}\0{processor_signature}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

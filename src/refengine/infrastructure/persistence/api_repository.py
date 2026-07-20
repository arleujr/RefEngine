from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from refengine.domain.enums import ApiRunStatus, ReferenceReadiness
from refengine.domain.models import ProcessedDocument
from refengine.services.reference_quality import assess_reference

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ApiRunRecord:
    run_id: str
    status: ApiRunStatus
    created_at: str
    started_at: str | None
    finished_at: str | None
    published_at: str | None
    access_date: str
    settings: dict[str, object]
    input_inventory: dict[str, object]
    error_message: str | None
    physical_sources: int
    selected_works: int
    ready_references: int
    review_required_references: int
    blocked_references: int
    excluded_works: int
    revision: int


@dataclass(frozen=True)
class ApiExportRecord:
    run_id: str
    format: str
    path: str
    sha256: str
    size_bytes: int
    created_at: str


class ApiRepository:
    """Persist API runs, selected works, review events, and exports locally."""

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
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS api_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    published_at TEXT,
                    access_date TEXT NOT NULL,
                    settings_json TEXT NOT NULL,
                    input_inventory_json TEXT NOT NULL,
                    error_message TEXT,
                    physical_sources INTEGER NOT NULL DEFAULT 0,
                    selected_works INTEGER NOT NULL DEFAULT 0,
                    ready_references INTEGER NOT NULL DEFAULT 0,
                    review_required_references INTEGER NOT NULL DEFAULT 0,
                    blocked_references INTEGER NOT NULL DEFAULT 0,
                    excluded_works INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS api_run_documents (
                    run_id TEXT NOT NULL,
                    work_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    canonical_key TEXT,
                    readiness TEXT NOT NULL,
                    included INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    original_payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, work_id),
                    FOREIGN KEY (run_id) REFERENCES api_runs(run_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_api_run_documents_status
                ON api_run_documents(run_id, readiness, included);

                CREATE TABLE IF NOT EXISTS api_review_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    work_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES api_runs(run_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS api_exports (
                    run_id TEXT NOT NULL,
                    format TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, format),
                    FOREIGN KEY (run_id) REFERENCES api_runs(run_id) ON DELETE CASCADE
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (_SCHEMA_VERSION,),
            )

    def create_run(
        self,
        *,
        run_id: str,
        access_date: str,
        settings: dict[str, object],
        input_inventory: dict[str, object],
    ) -> ApiRunRecord:
        created_at = _now()
        inventory_files = input_inventory.get("files", [])
        physical_sources = len(inventory_files) if isinstance(inventory_files, list) else 0
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO api_runs (
                    run_id, status, created_at, access_date, settings_json,
                    input_inventory_json, physical_sources
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    ApiRunStatus.QUEUED.value,
                    created_at,
                    access_date,
                    json.dumps(settings, ensure_ascii=False),
                    json.dumps(input_inventory, ensure_ascii=False),
                    physical_sources,
                ),
            )
        record = self.get_run(run_id)
        if record is None:
            raise RuntimeError("The API run could not be created.")
        return record

    def active_run(self) -> ApiRunRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM api_runs
                WHERE status IN (?, ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (ApiRunStatus.QUEUED.value, ApiRunStatus.PROCESSING.value),
            ).fetchone()
        return self._run_from_row(row) if row is not None else None

    def recover_interrupted_runs(self) -> int:
        now = _now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE api_runs
                SET status = ?, finished_at = ?,
                    error_message = COALESCE(error_message, ?),
                    revision = revision + 1
                WHERE status IN (?, ?)
                """,
                (
                    ApiRunStatus.FAILED.value,
                    now,
                    "The backend stopped before this run completed. Start a new run.",
                    ApiRunStatus.QUEUED.value,
                    ApiRunStatus.PROCESSING.value,
                ),
            )
        return int(cursor.rowcount)

    def set_status(
        self,
        run_id: str,
        status: ApiRunStatus,
        *,
        error_message: str | None = None,
    ) -> None:
        updates = ["status = ?", "revision = revision + 1"]
        values: list[object] = [status.value]
        if status is ApiRunStatus.PROCESSING:
            updates.append("started_at = ?")
            values.append(_now())
        if status in {ApiRunStatus.REVIEW, ApiRunStatus.FAILED}:
            updates.append("finished_at = ?")
            values.append(_now())
        if status is ApiRunStatus.PUBLISHED:
            updates.append("published_at = ?")
            values.append(_now())
        if error_message is not None or status is not ApiRunStatus.FAILED:
            updates.append("error_message = ?")
            values.append(error_message)
        values.append(run_id)
        with self._connection() as connection:
            cursor = connection.execute(
                f"UPDATE api_runs SET {', '.join(updates)} WHERE run_id = ?",
                values,
            )
            if cursor.rowcount != 1:
                raise KeyError(run_id)

    def get_run(self, run_id: str) -> ApiRunRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM api_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return self._run_from_row(row) if row is not None else None

    def list_runs(self, limit: int = 20) -> list[ApiRunRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM api_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def save_documents(
        self,
        run_id: str,
        documents: list[ProcessedDocument],
        *,
        preserve_original: bool,
    ) -> None:
        now = _now()
        rows = []
        for document in documents:
            assessment = assess_reference(document)
            payload = document.model_dump_json()
            rows.append(
                (
                    run_id,
                    document.sha256,
                    document.source_path.name,
                    document.canonical_key,
                    assessment.readiness.value,
                    int(document.include_in_output),
                    payload,
                    payload,
                    now,
                    int(preserve_original),
                )
            )
        with self._connection() as connection:
            connection.executemany(
                """
                INSERT INTO api_run_documents (
                    run_id, work_id, source_name, canonical_key, readiness,
                    included, payload_json, original_payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, work_id) DO UPDATE SET
                    source_name = excluded.source_name,
                    canonical_key = excluded.canonical_key,
                    readiness = excluded.readiness,
                    included = excluded.included,
                    payload_json = excluded.payload_json,
                    original_payload_json = CASE
                        WHEN ? = 1 THEN api_run_documents.original_payload_json
                        ELSE excluded.original_payload_json
                    END,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
        self.refresh_counts(run_id)

    def load_documents(self, run_id: str) -> list[ProcessedDocument]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM api_run_documents
                WHERE run_id = ?
                ORDER BY source_name COLLATE NOCASE
                """,
                (run_id,),
            ).fetchall()
        return [ProcessedDocument.model_validate_json(str(row[0])) for row in rows]

    def load_document(self, run_id: str, work_id: str) -> ProcessedDocument | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM api_run_documents
                WHERE run_id = ? AND work_id = ?
                """,
                (run_id, work_id),
            ).fetchone()
        return ProcessedDocument.model_validate_json(str(row[0])) if row else None

    def load_original_document(self, run_id: str, work_id: str) -> ProcessedDocument | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT original_payload_json FROM api_run_documents
                WHERE run_id = ? AND work_id = ?
                """,
                (run_id, work_id),
            ).fetchone()
        return ProcessedDocument.model_validate_json(str(row[0])) if row else None

    def append_review_event(
        self,
        *,
        run_id: str,
        work_id: str,
        action: str,
        payload: dict[str, object],
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO api_review_events (
                    run_id, work_id, action, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    work_id,
                    action,
                    json.dumps(payload, ensure_ascii=False),
                    _now(),
                ),
            )
            connection.execute(
                "UPDATE api_runs SET revision = revision + 1 WHERE run_id = ?",
                (run_id,),
            )

    def save_export(
        self,
        *,
        run_id: str,
        format: str,
        path: Path,
        sha256: str,
        size_bytes: int,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO api_exports (
                    run_id, format, path, sha256, size_bytes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, format) DO UPDATE SET
                    path = excluded.path,
                    sha256 = excluded.sha256,
                    size_bytes = excluded.size_bytes,
                    created_at = excluded.created_at
                """,
                (run_id, format, str(path), sha256, size_bytes, _now()),
            )

    def get_export(self, run_id: str, format: str) -> ApiExportRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM api_exports WHERE run_id = ? AND format = ?",
                (run_id, format),
            ).fetchone()
        if row is None:
            return None
        return ApiExportRecord(
            run_id=str(row["run_id"]),
            format=str(row["format"]),
            path=str(row["path"]),
            sha256=str(row["sha256"]),
            size_bytes=int(row["size_bytes"]),
            created_at=str(row["created_at"]),
        )

    def refresh_counts(self, run_id: str) -> None:
        documents = self.load_documents(run_id)
        included = [document for document in documents if document.include_in_output]
        readiness = [assess_reference(document).readiness for document in included]
        values = (
            len(documents),
            sum(item is ReferenceReadiness.READY for item in readiness),
            sum(item is ReferenceReadiness.REVIEW_REQUIRED for item in readiness),
            sum(item is ReferenceReadiness.BLOCKED for item in readiness),
            len(documents) - len(included),
            run_id,
        )
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE api_runs SET
                    selected_works = ?,
                    ready_references = ?,
                    review_required_references = ?,
                    blocked_references = ?,
                    excluded_works = ?,
                    revision = revision + 1
                WHERE run_id = ?
                """,
                values,
            )

    def integrity_check(self) -> str:
        with self._connection() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0] if row is not None else "unknown")

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> ApiRunRecord:
        return ApiRunRecord(
            run_id=str(row["run_id"]),
            status=ApiRunStatus(str(row["status"])),
            created_at=str(row["created_at"]),
            started_at=str(row["started_at"]) if row["started_at"] else None,
            finished_at=str(row["finished_at"]) if row["finished_at"] else None,
            published_at=str(row["published_at"]) if row["published_at"] else None,
            access_date=str(row["access_date"]),
            settings=json.loads(str(row["settings_json"])),
            input_inventory=json.loads(str(row["input_inventory_json"])),
            error_message=str(row["error_message"]) if row["error_message"] else None,
            physical_sources=int(row["physical_sources"]),
            selected_works=int(row["selected_works"]),
            ready_references=int(row["ready_references"]),
            review_required_references=int(row["review_required_references"]),
            blocked_references=int(row["blocked_references"]),
            excluded_works=int(row["excluded_works"]),
            revision=int(row["revision"]),
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()

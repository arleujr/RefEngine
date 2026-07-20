from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from refengine.domain.enums import ReviewState, WarningCode
from refengine.domain.models import CorrectionSuggestion, Evidence, ProcessedDocument
from refengine.services.author_parser import parse_review_authors
from refengine.services.bibliographic_record import (
    clear_reviewed_field,
    record_from_metadata,
    set_reviewed_field,
    set_reviewed_schema,
)
from refengine.services.catalog_review import (
    field_is_repeatable,
    parse_reviewed_values,
)
from refengine.services.correction_memory import (
    FIELD_LABELS,
    correction_candidate,
    current_field_value,
    normalize_correction_value,
)

_LEGACY_TO_CATALOG = {
    "authors": "authors",
    "title": "title",
    "journal": "periodical_title",
    "place": "place",
    "year": "publication_year",
    "publication_month": "publication_month",
    "volume": "volume",
    "issue": "issue",
    "pages": "article_pages",
    "article_number": "article_number",
    "doi": "doi",
    "url": "url",
    "institution": "academic_affiliation",
    "degree": "work_type",
    "program": "degree_course",
    "publisher": "publisher",
    "total_pages": "pagination",
    "corporate_author": "corporate_author",
}
_CATALOG_TO_LEGACY = {value: key for key, value in _LEGACY_TO_CATALOG.items()}


@dataclass(frozen=True)
class StoredCorrection:
    sha256: str
    field_name: str
    source_value: str | None
    corrected_value: str | None


class ReviewMemoryStore:
    """Persist explicit local corrections without creating hidden global overrides.

    Exact corrections are reapplied only to the same SHA-256. Cross-document
    suggestions remain limited to safe textual legacy fields and are never applied
    automatically.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS document_corrections (
                    sha256 TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    source_value TEXT,
                    corrected_value TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (sha256, field_name)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS correction_suggestions (
                    field_name TEXT NOT NULL,
                    field_label TEXT NOT NULL,
                    source_value TEXT NOT NULL,
                    source_normalized TEXT NOT NULL,
                    replacement_value TEXT NOT NULL,
                    replacement_normalized TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    confirmation_count INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (
                        field_name,
                        source_normalized,
                        replacement_normalized,
                        document_type
                    )
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_review_memory_suggestions
                ON correction_suggestions (
                    field_name,
                    source_normalized,
                    document_type
                )
                """
            )

    def apply_exact(self, document: ProcessedDocument) -> ProcessedDocument:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT field_name, corrected_value
                FROM document_corrections
                WHERE sha256 = ?
                ORDER BY field_name
                """,
                (document.sha256,),
            ).fetchall()
        if not rows:
            return self.attach_suggestions(document)

        result = document.model_copy(deep=True)
        record = result.bibliographic_record or record_from_metadata(
            result.metadata,
            result.source_path,
        )
        applied = False
        for row in rows:
            stored_field = str(row["field_name"])
            corrected_value = row["corrected_value"]
            if stored_field == "__schema_id__":
                record = set_reviewed_schema(
                    record,
                    schema_id=str(corrected_value) if corrected_value else None,
                    source="review_memory.sqlite3",
                )
                applied = True
                continue
            field_id = _LEGACY_TO_CATALOG.get(stored_field, stored_field)
            try:
                if corrected_value is None:
                    record = clear_reviewed_field(record, field_id=field_id)
                else:
                    values = parse_reviewed_values(
                        corrected_value,
                        repeatable=field_is_repeatable(field_id),
                    )
                    record = set_reviewed_field(
                        record,
                        field_id=field_id,
                        values=values,
                        source_file="review_memory.sqlite3",
                        method="review_memory_exact",
                    )
                    self._sync_legacy_metadata(result, stored_field, str(corrected_value))
            except ValueError:
                # Obsolete correction rows remain in SQLite but cannot alter the run.
                continue
            applied = True

        result.bibliographic_record = record
        result.resolved_bibliography = None
        result.generated_reference = None
        if applied:
            result.review_state = ReviewState.CORRECTED
            result.warnings = list(
                dict.fromkeys([*result.warnings, WarningCode.REVIEW_MEMORY_APPLIED])
            )
        return self.attach_suggestions(result)

    def attach_suggestions(self, document: ProcessedDocument) -> ProcessedDocument:
        result = document.model_copy(deep=True)
        suggestions: list[CorrectionSuggestion] = []
        with self._connection() as connection:
            for field_name in sorted(FIELD_LABELS):
                current = current_field_value(result, field_name)
                if not current:
                    continue
                normalized = normalize_correction_value(current)
                rows = connection.execute(
                    """
                    SELECT * FROM correction_suggestions
                    WHERE field_name = ?
                      AND source_normalized = ?
                      AND document_type = ?
                    ORDER BY confirmation_count DESC, updated_at DESC
                    """,
                    (field_name, normalized, result.metadata.document_type.value),
                ).fetchall()
                for row in rows:
                    if normalize_correction_value(current) == row["replacement_normalized"]:
                        continue
                    suggestions.append(
                        CorrectionSuggestion(
                            field_name=field_name,
                            field_label=str(row["field_label"]),
                            source_value=str(row["source_value"]),
                            replacement_value=str(row["replacement_value"]),
                            confirmation_count=int(row["confirmation_count"]),
                        )
                    )
        result.correction_suggestions = suggestions
        if suggestions:
            result.warnings = list(
                dict.fromkeys([*result.warnings, WarningCode.CORRECTION_SUGGESTION_AVAILABLE])
            )
        return result

    def remember_review(
        self,
        original: ProcessedDocument,
        reviewed: ProcessedDocument,
        changed_fields: dict[str, str | None],
    ) -> int:
        if reviewed.review_state not in {ReviewState.APPROVED, ReviewState.CORRECTED}:
            return 0
        now = datetime.now(UTC).isoformat()
        stored = 0
        with self._connection() as connection:
            for field_name, corrected_value in changed_fields.items():
                source_value = self._source_value(original, field_name)
                connection.execute(
                    """
                    INSERT INTO document_corrections (
                        sha256,
                        field_name,
                        source_value,
                        corrected_value,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(sha256, field_name) DO UPDATE SET
                        source_value = excluded.source_value,
                        corrected_value = excluded.corrected_value,
                        updated_at = excluded.updated_at
                    """,
                    (
                        original.sha256,
                        field_name,
                        source_value,
                        corrected_value,
                        now,
                    ),
                )

                legacy_field = _CATALOG_TO_LEGACY.get(field_name, field_name)
                candidate = correction_candidate(
                    field_name=legacy_field,
                    source_value=source_value,
                    replacement_value=corrected_value,
                    document_type=reviewed.metadata.document_type,
                )
                if candidate is not None:
                    connection.execute(
                        """
                        INSERT INTO correction_suggestions (
                            field_name,
                            field_label,
                            source_value,
                            source_normalized,
                            replacement_value,
                            replacement_normalized,
                            document_type,
                            confirmation_count,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                        ON CONFLICT(
                            field_name,
                            source_normalized,
                            replacement_normalized,
                            document_type
                        ) DO UPDATE SET
                            confirmation_count = confirmation_count + 1,
                            source_value = excluded.source_value,
                            replacement_value = excluded.replacement_value,
                            updated_at = excluded.updated_at
                        """,
                        (
                            candidate.field_name,
                            candidate.field_label,
                            candidate.source_value,
                            normalize_correction_value(candidate.source_value),
                            candidate.replacement_value,
                            normalize_correction_value(candidate.replacement_value),
                            candidate.document_type.value,
                            now,
                        ),
                    )
                stored += 1
        return stored

    def integrity_check(self) -> str:
        with self._connection() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0] if row is not None else "unknown")

    @staticmethod
    def _sync_legacy_metadata(
        document: ProcessedDocument,
        field_name: str,
        value: str,
    ) -> None:
        """Keep pre-catalog metadata coherent for existing local correction databases."""
        legacy_field = _CATALOG_TO_LEGACY.get(field_name, field_name)
        if legacy_field == "authors":
            authors = parse_review_authors(value)
            document.metadata.authors = authors
            document.metadata.authors_evidence = Evidence(
                value=value,
                confidence=1.0 if authors else 0.0,
                page_number=document.metadata.authors_evidence.page_number,
                excerpt=value,
                method="review_memory_exact",
            )
            return
        evidence = getattr(document.metadata, legacy_field, None)
        if not isinstance(evidence, Evidence):
            return
        setattr(
            document.metadata,
            legacy_field,
            Evidence(
                value=value,
                confidence=1.0,
                page_number=evidence.page_number,
                excerpt=value,
                method="review_memory_exact",
            ),
        )

    @staticmethod
    def _source_value(document: ProcessedDocument, field_name: str) -> str | None:
        if field_name == "__schema_id__":
            return (
                document.resolved_bibliography.schema_id if document.resolved_bibliography else None
            )
        field_id = _LEGACY_TO_CATALOG.get(field_name, field_name)
        resolved = document.resolved_bibliography
        if resolved is not None:
            values = resolved.values_for(field_id)
            if values:
                return "\n".join(values)
        legacy_field = _CATALOG_TO_LEGACY.get(field_id)
        if legacy_field is not None:
            return current_field_value(document, legacy_field)
        return None

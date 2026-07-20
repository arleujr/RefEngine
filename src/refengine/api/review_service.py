from __future__ import annotations

from datetime import date

from refengine.domain.enums import ReviewState
from refengine.domain.models import ProcessedDocument
from refengine.rules.catalog import NormativeCatalog, load_ufv_2025_catalog
from refengine.services.bibliographic_record import (
    clear_reviewed_field,
    record_from_metadata,
    set_reviewed_field,
    set_reviewed_schema,
)
from refengine.services.catalog_review import parse_reviewed_values
from refengine.services.reference_compiler import ReferenceCompiler
from refengine.services.reference_formatter import ReferenceFormatter


class ApiReviewError(ValueError):
    """Raised when an API review request violates the normative catalog."""


class ApiReviewService:
    """Apply local API edits and recompile the whole run deterministically."""

    def __init__(
        self,
        *,
        include_all_authors: bool = True,
        catalog: NormativeCatalog | None = None,
    ) -> None:
        self._catalog = catalog or load_ufv_2025_catalog()
        self._schemas = {schema.id: schema for schema in self._catalog.schemas}
        self._fields = {field.id: field for field in self._catalog.fields}
        self._compiler = ReferenceCompiler(
            ReferenceFormatter(
                include_all_authors=include_all_authors,
                output_policy=self._catalog.output_policy,
            )
        )

    def patch(
        self,
        documents: list[ProcessedDocument],
        *,
        work_id: str,
        access_date: date,
        schema_id_provided: bool,
        schema_id: str | None,
        field_changes: dict[str, str | list[str] | None],
        included: bool | None,
    ) -> tuple[list[ProcessedDocument], dict[str, str | None]]:
        index = self._index_for(documents, work_id)
        source = documents[index]
        document = source.model_copy(deep=True)
        record = document.bibliographic_record or record_from_metadata(
            document.metadata,
            document.source_path,
        )
        changes: dict[str, str | None] = {}

        # Exclusion is a complete user decision. It must not depend on schema
        # identification or mandatory fields, and it preserves the previously
        # extracted/reviewed data in case the work is included again later.
        if included is False:
            document.include_in_output = False
            document.review_state = ReviewState.EXCLUDED
            document.resolved_bibliography = None
            document.generated_reference = None
            documents[index] = document
            changes["__included__"] = "false"
            return self._compiler.compile(documents, access_date), changes

        if schema_id_provided:
            if schema_id is not None and schema_id not in self._schemas:
                raise ApiReviewError(f"Unknown UFV schema: {schema_id}")
            record = set_reviewed_schema(
                record,
                schema_id=schema_id,
                source="local-api",
            )
            changes["__schema_id__"] = schema_id

        effective_schema_id = (
            schema_id
            if schema_id_provided
            else (
                record.schema_override
                or (
                    document.resolved_bibliography.schema_id
                    if document.resolved_bibliography is not None
                    else None
                )
            )
        )
        effective_schema = self._schemas.get(effective_schema_id or "")

        for field_id, raw_value in field_changes.items():
            field = self._fields.get(field_id)
            if field is None:
                raise ApiReviewError(f"Unknown UFV catalog field: {field_id}")
            if effective_schema is None:
                raise ApiReviewError("Choose a UFV schema before editing bibliographic fields.")
            if field_id not in effective_schema.ordered_fields:
                raise ApiReviewError(
                    f"Field {field_id!r} does not belong to schema {effective_schema.id}."
                )
            if raw_value is None:
                record = clear_reviewed_field(record, field_id=field_id)
                changes[field_id] = None
                continue
            values = self._values(raw_value, repeatable=field.repeatable)
            if not values:
                raise ApiReviewError(
                    f"Field {field_id!r} cannot be replaced with an empty value; use null to clear it."
                )
            record = set_reviewed_field(
                record,
                field_id=field_id,
                values=values,
                source_file="local-api",
                method="api_review",
            )
            changes[field_id] = "\n".join(values)

        if included is not None:
            document.include_in_output = included
            document.review_state = ReviewState.PENDING if included else ReviewState.EXCLUDED
            changes["__included__"] = "true" if included else "false"
        elif changes:
            document.review_state = ReviewState.PENDING

        document.bibliographic_record = record
        document.resolved_bibliography = None
        document.generated_reference = None
        documents[index] = document
        return self._compiler.compile(documents, access_date), changes

    def approve(
        self,
        documents: list[ProcessedDocument],
        *,
        work_id: str,
        access_date: date,
    ) -> list[ProcessedDocument]:
        index = self._index_for(documents, work_id)
        document = documents[index].model_copy(deep=True)
        resolved = document.resolved_bibliography
        if not document.include_in_output:
            raise ApiReviewError("An excluded work cannot be approved.")
        if resolved is None or resolved.schema_id is None:
            raise ApiReviewError("The UFV schema has not been identified.")
        if resolved.missing_required_fields:
            missing = ", ".join(resolved.missing_required_fields)
            raise ApiReviewError(f"Required fields are missing: {missing}")
        if not document.generated_reference:
            raise ApiReviewError("The reference could not be generated.")
        document.review_state = ReviewState.APPROVED
        documents[index] = document
        return self._compiler.compile(documents, access_date)

    @staticmethod
    def reviewed_changes(document: ProcessedDocument) -> dict[str, str | None]:
        record = document.bibliographic_record
        if record is None:
            return {}
        changes: dict[str, str | None] = {}
        if record.schema_override is not None:
            changes["__schema_id__"] = record.schema_override
        for field_id in record.excluded_field_ids:
            changes[field_id] = None
        grouped: dict[str, list[tuple[int, str]]] = {}
        for candidate in record.field_candidates:
            if candidate.method != "api_review":
                continue
            grouped.setdefault(candidate.field_id, []).append(
                (candidate.sequence or 10_000, candidate.value)
            )
        for field_id, values in grouped.items():
            ordered = [value for _, value in sorted(values)]
            changes[field_id] = "\n".join(ordered)
        return changes

    @staticmethod
    def _values(value: str | list[str], *, repeatable: bool) -> list[str]:
        if isinstance(value, list):
            values = [str(item).strip() for item in value if str(item).strip()]
            if not repeatable and len(values) > 1:
                raise ApiReviewError("This catalog field accepts only one value.")
            return values
        return parse_reviewed_values(value, repeatable=repeatable)

    @staticmethod
    def _index_for(documents: list[ProcessedDocument], work_id: str) -> int:
        for index, document in enumerate(documents):
            if document.sha256 == work_id:
                return index
        raise KeyError(work_id)

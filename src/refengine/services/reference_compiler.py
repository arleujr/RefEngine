from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from refengine.domain.models import ProcessedDocument
from refengine.services.bibliographic_record import record_from_metadata
from refengine.services.candidate_resolver import CandidateResolver
from refengine.services.reference_formatter import ReferenceFormatter


class ReferenceCompiler:
    """Resolve candidate ledgers, sort works, and generate UFV references."""

    def __init__(
        self,
        formatter: ReferenceFormatter,
        resolver: CandidateResolver | None = None,
    ) -> None:
        self._formatter = formatter
        self._resolver = resolver or CandidateResolver()

    def compile(
        self,
        documents: list[ProcessedDocument],
        access_date: date,
    ) -> list[ProcessedDocument]:
        resolved_documents = [self._resolve_document(item, access_date) for item in documents]
        ordered = sorted(resolved_documents, key=self._sort_key)
        eligible = [
            item
            for item in ordered
            if item.include_in_output
            and item.status.value != "failed"
            and item.resolved_bibliography is not None
            and item.resolved_bibliography.ready_for_formatting
            and item.resolved_bibliography.schema_id in self._formatter.supported_schema_ids()
        ]
        counts: Counter[tuple[tuple[tuple[str, str], ...], str]] = Counter(
            self._duplicate_key(item) for item in eligible
        )
        suffix_indexes: defaultdict[tuple[tuple[tuple[str, str], ...], str], int] = defaultdict(int)

        compiled: list[ProcessedDocument] = []
        for source in ordered:
            document = source.model_copy(deep=True)
            resolved = document.resolved_bibliography
            if (
                not document.include_in_output
                or document.status.value == "failed"
                or resolved is None
                or not resolved.ready_for_formatting
                or resolved.schema_id not in self._formatter.supported_schema_ids()
            ):
                document.generated_reference = None
                compiled.append(document)
                continue

            key = self._duplicate_key(document)
            year_suffix = ""
            if counts[key] > 1:
                year_suffix = self._alphabetic_suffix(suffix_indexes[key])
                suffix_indexes[key] += 1
            document.generated_reference = self._formatter.format_resolved(
                resolved,
                access_date,
                year_suffix=year_suffix,
            )
            compiled.append(document)
        return compiled

    def _resolve_document(
        self,
        source: ProcessedDocument,
        access_date: date,
    ) -> ProcessedDocument:
        document = source.model_copy(deep=True)
        if document.status.value == "failed":
            document.resolved_bibliography = None
            return document
        record = document.bibliographic_record
        if record is None:
            record = record_from_metadata(document.metadata, document.source_path)
            document.bibliographic_record = record
        document.resolved_bibliography = self._resolver.resolve(
            record,
            access_date=access_date,
        )
        return document

    def _sort_key(self, document: ProcessedDocument) -> tuple[str, str, str]:
        resolved = document.resolved_bibliography
        if resolved is not None:
            return self._formatter.resolved_sort_key(resolved)
        return (document.source_path.name.casefold(), "", "")

    def _duplicate_key(
        self,
        document: ProcessedDocument,
    ) -> tuple[tuple[tuple[str, str], ...], str]:
        resolved = document.resolved_bibliography
        if resolved is None:
            return tuple(), "s.d."
        return (
            self._formatter.resolved_authorship_key(resolved),
            self._formatter.year_value(resolved),
        )

    @staticmethod
    def _alphabetic_suffix(index: int) -> str:
        result = ""
        value = index
        while True:
            value, remainder = divmod(value, 26)
            result = chr(ord("a") + remainder) + result
            if value == 0:
                return result
            value -= 1

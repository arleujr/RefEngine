from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

from refengine.domain.enums import (
    DocumentType,
    ErrorCode,
    ProcessingStatus,
    VariantType,
)
from refengine.domain.models import (
    ArticleMetadata,
    ProcessedDocument,
    ProcessingIncident,
    empty_evidence,
)
from refengine.infrastructure.pdf.document_processor import DocumentProcessor
from refengine.infrastructure.persistence.extraction_cache import ExtractionCache
from refengine.infrastructure.persistence.review_memory import ReviewMemoryStore
from refengine.infrastructure.persistence.sqlite_repository import SqliteDocumentRepository
from refengine.services.bibliographic_record import (
    merge_records,
    record_from_bibtex,
    record_from_metadata,
    record_from_ris,
)
from refengine.services.bibtex import (
    BibTeXEntry,
    BibTeXParseError,
    discover_bibtex,
    document_from_bibtex,
    parse_bibtex_file,
)
from refengine.services.bibtex_merge import match_bibtex_entry, merge_bibtex_metadata
from refengine.services.document_classifier import canonical_key, classify_variant
from refengine.services.file_discovery import discover_pdfs
from refengine.services.metadata_extractor import MetadataExtractor
from refengine.services.reference_compiler import ReferenceCompiler
from refengine.services.reference_formatter import ReferenceFormatter
from refengine.services.ris import (
    RisEntry,
    RisParseError,
    discover_ris,
    document_from_ris,
    parse_ris_file,
)
from refengine.services.ris_match import match_ris_entry
from refengine.services.validation import (
    apply_warning_status,
    classify_metadata,
    collect_warnings,
)
from refengine.services.variant_resolver import resolve_variants

logger = logging.getLogger(__name__)
_SPACE = re.compile(r"\s+")


@dataclass
class IngestStats:
    pdf_files: int = 0
    bibtex_files: int = 0
    bibtex_entries: int = 0
    ris_files: int = 0
    ris_entries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_writes: int = 0
    failed_sources: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


class IngestFolder:
    """Orchestrate PDF/BibTeX ingestion while preserving recoverable failures."""

    def __init__(
        self,
        processor: DocumentProcessor,
        extractor: MetadataExtractor,
        formatter: ReferenceFormatter,
        repository: SqliteDocumentRepository,
        review_memory: ReviewMemoryStore | None = None,
        extraction_cache: ExtractionCache | None = None,
    ) -> None:
        self._processor = processor
        self._extractor = extractor
        self._compiler = ReferenceCompiler(formatter)
        self._repository = repository
        self._review_memory = review_memory
        self._extraction_cache = extraction_cache
        self.stats = IngestStats()
        processor_signature_method = getattr(processor, "cache_signature", None)
        processor_signature = (
            str(processor_signature_method())
            if callable(processor_signature_method)
            else f"{type(processor).__module__}.{type(processor).__qualname__}"
        )
        extractor_signature_method = getattr(extractor, "cache_signature", None)
        extractor_signature = (
            str(extractor_signature_method())
            if callable(extractor_signature_method)
            else f"{type(extractor).__module__}.{type(extractor).__qualname__}"
        )
        self._processor_signature = f"{processor_signature}|{extractor_signature}"

    def execute(
        self,
        input_directory: Path,
        access_date: date,
        recursive: bool = True,
    ) -> list[ProcessedDocument]:
        self.stats = IngestStats()
        documents: list[ProcessedDocument] = []
        entries, bibtex_failures = self._load_bibtex_entries(
            input_directory,
            recursive,
        )
        ris_entries, ris_failures = self._load_ris_entries(
            input_directory,
            recursive,
        )
        documents.extend([*bibtex_failures, *ris_failures])
        unmatched_entries = list(entries)
        unmatched_ris_entries = list(ris_entries)

        pdf_paths = discover_pdfs(input_directory, recursive=recursive)
        self.stats.pdf_files = len(pdf_paths)
        for pdf_path in pdf_paths:
            logger.info("Ingesting %s", pdf_path.name)
            try:
                document = self._process_pdf(pdf_path)
                record = record_from_metadata(document.metadata, pdf_path)
                match = match_bibtex_entry(document, unmatched_entries)
                if match is not None:
                    merged_record = merge_records(record, record_from_bibtex(match.entry))
                    if merged_record is not None:
                        record = merged_record
                    document = merge_bibtex_metadata(document, match.entry)
                    unmatched_entries.remove(match.entry)
                ris_match = match_ris_entry(document, unmatched_ris_entries)
                if ris_match is not None:
                    merged_record = merge_records(record, record_from_ris(ris_match.entry))
                    if merged_record is not None:
                        record = merged_record
                    unmatched_ris_entries.remove(ris_match.entry)
                document.bibliographic_record = record
                document = self._reclassify(document)
                if self._review_memory is not None:
                    document = self._review_memory.apply_exact(document)
                    document = self._reclassify(document)
                documents.append(document)
            except Exception as exc:  # one bad source must not abort the batch
                logger.error("Failed to process %s: %s", pdf_path.name, exc)
                logger.debug("Source processing traceback", exc_info=True)
                self.stats.failed_sources += 1
                documents.append(self._failed_document(pdf_path, exc))

        for bibtex_entry in unmatched_entries:
            try:
                document = document_from_bibtex(bibtex_entry)
                document.bibliographic_record = record_from_bibtex(bibtex_entry)
                if self._review_memory is not None:
                    document = self._review_memory.apply_exact(document)
                    document = self._reclassify(document)
                documents.append(document)
            except Exception as exc:
                logger.error(
                    "Failed to process BibTeX entry %s from %s: %s",
                    bibtex_entry.key,
                    bibtex_entry.source_path.name,
                    exc,
                )
                logger.debug("BibTeX processing traceback", exc_info=True)
                self.stats.failed_sources += 1
                documents.append(self._failed_bibtex_entry(bibtex_entry, exc))

        for ris_entry in unmatched_ris_entries:
            try:
                document = document_from_ris(ris_entry)
                document.bibliographic_record = record_from_ris(ris_entry)
                if self._review_memory is not None:
                    document = self._review_memory.apply_exact(document)
                    document = self._reclassify(document)
                documents.append(document)
            except Exception as exc:
                logger.error(
                    "Failed to process RIS entry %s from %s: %s",
                    ris_entry.key,
                    ris_entry.source_path.name,
                    exc,
                )
                logger.debug("RIS processing traceback", exc_info=True)
                self.stats.failed_sources += 1
                documents.append(self._failed_ris_entry(ris_entry, exc))

        compiled = self._compiler.compile(resolve_variants(documents), access_date)
        save_many = getattr(self._repository, "save_many", None)
        if callable(save_many):
            save_many(compiled)
        else:
            for document in compiled:
                self._repository.save(document)
        return compiled

    def _process_pdf(
        self,
        pdf_path: Path,
    ) -> ProcessedDocument:
        sha256 = self._processor.sha256(pdf_path)
        raw_document: ProcessedDocument | None = None
        if self._extraction_cache is not None:
            raw_document = self._extraction_cache.get(
                sha256,
                self._processor_signature,
            )

        if raw_document is None:
            self.stats.cache_misses += 1
            raw_document = self._extract_pdf(pdf_path, sha256)
            if self._extraction_cache is not None:
                self._extraction_cache.put(
                    raw_document,
                    self._processor_signature,
                )
                self.stats.cache_writes += 1
        else:
            self.stats.cache_hits += 1
            logger.info("Extraction cache hit for %s", pdf_path.name)

        document = raw_document.model_copy(deep=True)
        document.source_path = pdf_path
        document.sha256 = sha256
        document.generated_reference = None
        document.incident = None
        document.variant_type = classify_variant(pdf_path, document.pages)
        document.canonical_key = canonical_key(document.metadata, pdf_path.name)

        document = self._reclassify(document, refresh_warnings=True)
        document.variant_type = classify_variant(pdf_path, document.pages)
        document.canonical_key = canonical_key(document.metadata, pdf_path.name)
        return document

    def _extract_pdf(self, pdf_path: Path, sha256: str) -> ProcessedDocument:
        pages = self._processor.process_pages(pdf_path)
        metadata = self._extractor.extract(pdf_path, pages)
        base_status, errors = classify_metadata(metadata)
        warnings = collect_warnings(pages, metadata)
        status = apply_warning_status(base_status, warnings)
        return ProcessedDocument(
            source_path=pdf_path,
            sha256=sha256,
            pages=pages,
            metadata=metadata,
            status=status,
            errors=errors,
            warnings=warnings,
            variant_type=classify_variant(pdf_path, pages),
            canonical_key=canonical_key(metadata, pdf_path.name),
        )

    def _load_bibtex_entries(
        self,
        input_directory: Path,
        recursive: bool,
    ) -> tuple[list[BibTeXEntry], list[ProcessedDocument]]:
        entries: list[BibTeXEntry] = []
        failures: list[ProcessedDocument] = []
        paths = discover_bibtex(input_directory, recursive=recursive)
        self.stats.bibtex_files = len(paths)
        for path in paths:
            logger.info("Reading BibTeX metadata from %s", path.name)
            try:
                parsed = parse_bibtex_file(path)
                if not parsed:
                    raise BibTeXParseError("No BibTeX entries were found.")
                entries.extend(parsed)
            except (OSError, BibTeXParseError) as exc:
                logger.error("BibTeX file %s could not be processed: %s", path.name, exc)
                logger.debug("BibTeX file traceback", exc_info=True)
                self.stats.failed_sources += 1
                failures.append(
                    self._failed_source(
                        path,
                        exc,
                        variant_type=VariantType.BIBTEX,
                        phase="bibtex_file_parse",
                    )
                )
        self.stats.bibtex_entries = len(entries)
        return entries, failures

    def _load_ris_entries(
        self,
        input_directory: Path,
        recursive: bool,
    ) -> tuple[list[RisEntry], list[ProcessedDocument]]:
        entries: list[RisEntry] = []
        failures: list[ProcessedDocument] = []
        paths = discover_ris(input_directory, recursive=recursive)
        self.stats.ris_files = len(paths)
        for path in paths:
            logger.info("Reading RIS metadata from %s", path.name)
            try:
                entries.extend(parse_ris_file(path))
            except (OSError, RisParseError) as exc:
                logger.error("RIS file %s could not be processed: %s", path.name, exc)
                logger.debug("RIS file traceback", exc_info=True)
                self.stats.failed_sources += 1
                failures.append(
                    self._failed_source(
                        path,
                        exc,
                        variant_type=VariantType.RIS,
                        phase="ris_file_parse",
                    )
                )
        self.stats.ris_entries = len(entries)
        return entries, failures

    @staticmethod
    def _reclassify(
        document: ProcessedDocument,
        *,
        refresh_warnings: bool = False,
    ) -> ProcessedDocument:
        updated = document.model_copy(deep=True)
        base_status, errors = classify_metadata(updated.metadata)
        updated.errors = errors
        if refresh_warnings:
            updated.warnings = collect_warnings(updated.pages, updated.metadata)
        updated.status = apply_warning_status(base_status, updated.warnings)
        return updated

    @staticmethod
    def _failed_document(pdf_path: Path, exc: Exception) -> ProcessedDocument:
        return IngestFolder._failed_source(
            pdf_path,
            exc,
            variant_type=VariantType.UNKNOWN,
            phase="pdf_processing",
        )

    @staticmethod
    def _failed_bibtex_entry(
        entry: BibTeXEntry,
        exc: Exception,
    ) -> ProcessedDocument:
        return ProcessedDocument(
            source_path=Path(f"{entry.source_path}#{entry.key}"),
            sha256=f"failed-bibtex:{entry.source_path.name}:{entry.key}",
            pages=[],
            metadata=_empty_metadata("bibtex_processing_failure"),
            status=ProcessingStatus.FAILED,
            errors=[ErrorCode.SOURCE_PROCESSING_FAILED],
            warnings=[],
            variant_type=VariantType.BIBTEX,
            canonical_key=f"failed-bibtex:{entry.key.casefold()}",
            incident=_incident(
                exc,
                phase="bibtex_entry_processing",
                source_path=entry.source_path,
            ),
        )

    @staticmethod
    def _failed_ris_entry(
        entry: RisEntry,
        exc: Exception,
    ) -> ProcessedDocument:
        return ProcessedDocument(
            source_path=Path(f"{entry.source_path}#{entry.key}"),
            sha256=f"failed-ris:{entry.source_path.name}:{entry.key}",
            pages=[],
            metadata=_empty_metadata("ris_processing_failure"),
            status=ProcessingStatus.FAILED,
            errors=[ErrorCode.SOURCE_PROCESSING_FAILED],
            warnings=[],
            variant_type=VariantType.RIS,
            canonical_key=f"failed-ris:{entry.key.casefold()}",
            incident=_incident(
                exc,
                phase="ris_entry_processing",
                source_path=entry.source_path,
            ),
        )

    @staticmethod
    def _failed_source(
        source_path: Path,
        exc: Exception,
        *,
        variant_type: VariantType,
        phase: str,
    ) -> ProcessedDocument:
        try:
            digest = DocumentProcessor.sha256(source_path)
        except Exception:
            digest = f"unavailable:{source_path.name}"
        return ProcessedDocument(
            source_path=source_path,
            sha256=digest,
            pages=[],
            metadata=_empty_metadata("processing_failure"),
            status=ProcessingStatus.FAILED,
            errors=[ErrorCode.SOURCE_PROCESSING_FAILED],
            warnings=[],
            variant_type=variant_type,
            canonical_key=f"failed:{source_path.name.casefold()}",
            incident=_incident(exc, phase=phase, source_path=source_path),
        )


def _incident(
    exc: Exception,
    *,
    phase: str,
    source_path: Path,
) -> ProcessingIncident:
    message = _SPACE.sub(" ", str(exc)).strip() or "Source processing failed."
    parent = str(source_path.parent)
    if parent and parent not in {".", ""}:
        message = message.replace(parent, "<input>")
    return ProcessingIncident(
        incident_id=uuid4().hex[:12],
        phase=phase,
        exception_type=type(exc).__name__,
        message=message[:500],
        recoverable=True,
    )


def _empty_metadata(method: str) -> ArticleMetadata:
    return ArticleMetadata(
        title=empty_evidence(method),
        authors=[],
        authors_evidence=empty_evidence(method),
        journal=empty_evidence(method),
        place=empty_evidence(method),
        year=empty_evidence(method),
        publication_month=empty_evidence(method),
        volume=empty_evidence(method),
        issue=empty_evidence(method),
        pages=empty_evidence(method),
        article_number=empty_evidence(method),
        doi=empty_evidence(method),
        url=empty_evidence(method),
        extractor=method,
        document_type=DocumentType.UNKNOWN,
    )

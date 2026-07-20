from __future__ import annotations

from refengine.domain.enums import (
    DocumentType,
    ErrorCode,
    ExtractionMethod,
    ProcessingStatus,
    WarningCode,
)
from refengine.domain.models import ArticleMetadata, PageText


def classify_metadata(metadata: ArticleMetadata) -> tuple[ProcessingStatus, list[ErrorCode]]:
    """Classify extraction quality with document-type-aware critical fields."""
    errors: list[ErrorCode] = []
    if metadata.title.value is None:
        errors.append(ErrorCode.TITLE_NOT_FOUND)
    if not metadata.authors and metadata.corporate_author.value is None:
        if metadata.authors_evidence.method == "not_visible_in_print":
            errors.append(ErrorCode.AUTHORS_NOT_VISIBLE_IN_SOURCE)
        else:
            errors.append(ErrorCode.AUTHORS_AMBIGUOUS)
    elif metadata.authors and metadata.authors_evidence.confidence < 0.6:
        errors.append(ErrorCode.AUTHORS_AMBIGUOUS)
    if metadata.year.value is None:
        errors.append(ErrorCode.YEAR_AMBIGUOUS)
    if metadata.document_type is DocumentType.JOURNAL_ARTICLE and metadata.journal.value is None:
        errors.append(ErrorCode.JOURNAL_NOT_FOUND)
    if (
        metadata.title.value is None
        and not metadata.authors
        and metadata.corporate_author.value is None
    ):
        return ProcessingStatus.FAILED, errors
    if errors:
        return ProcessingStatus.REVIEW_REQUIRED, errors
    return ProcessingStatus.PROCESSED, errors


def collect_warnings(pages: list[PageText], metadata: ArticleMetadata) -> list[WarningCode]:
    warnings: list[WarningCode] = []
    diagnostics = {page.diagnostic_code for page in pages if page.diagnostic_code}
    unavailable_pages = [page for page in pages if page.method is ExtractionMethod.UNAVAILABLE]
    if WarningCode.OCR_NOT_AVAILABLE.value in diagnostics or any(
        page.diagnostic_code is None for page in unavailable_pages
    ):
        warnings.append(WarningCode.OCR_NOT_AVAILABLE)
    if WarningCode.OCR_LANGUAGE_MISSING.value in diagnostics:
        warnings.append(WarningCode.OCR_LANGUAGE_MISSING)
    if unavailable_pages:
        warnings.append(WarningCode.PAGE_TEXT_UNAVAILABLE)
    if any(
        page.method is ExtractionMethod.OCR
        and page.confidence is not None
        and page.confidence < 0.65
        for page in pages
    ):
        warnings.append(WarningCode.OCR_LOW_CONFIDENCE)
    if any(page.method is ExtractionMethod.SKIPPED for page in pages):
        warnings.append(WarningCode.METADATA_PAGES_ONLY)
    if metadata.place.value is None and metadata.document_type is DocumentType.JOURNAL_ARTICLE:
        warnings.append(WarningCode.PLACE_NOT_IDENTIFIED)
    if metadata.authors_evidence.method == "not_visible_in_print":
        warnings.append(WarningCode.SOURCE_FIELD_NOT_VISIBLE)
    evidence = [
        metadata.title,
        metadata.authors_evidence,
        metadata.journal,
        metadata.place,
        metadata.year,
        metadata.publication_month,
        metadata.volume,
        metadata.issue,
        metadata.pages,
        metadata.article_number,
        metadata.doi,
        metadata.url,
        metadata.institution,
        metadata.degree,
        metadata.program,
        metadata.publisher,
        metadata.total_pages,
        metadata.corporate_author,
        metadata.department,
        metadata.access_date,
    ]
    if any(item.method in {"api_review", "review_memory_exact"} for item in evidence):
        warnings.append(WarningCode.HUMAN_REVIEW)
    if any(
        "inferred" in item.method
        or item.method
        in {
            "doi_structure",
            "publisher_profile",
            "web_print_profile",
        }
        for item in evidence
    ):
        warnings.append(WarningCode.INFERRED_METADATA)
    return list(dict.fromkeys(warnings))


def apply_warning_status(status: ProcessingStatus, warnings: list[WarningCode]) -> ProcessingStatus:
    if status is ProcessingStatus.PROCESSED and warnings:
        return ProcessingStatus.PROCESSED_WITH_WARNINGS
    return status

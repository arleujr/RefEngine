from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from refengine.domain.enums import (
    DocumentType,
    ExtractionMethod,
    ProcessingStatus,
    QualityIssueCode,
    ReferenceReadiness,
    ReviewState,
    WarningCode,
)
from refengine.domain.models import ProcessedDocument, ReferenceQualityAssessment
from refengine.services.reference_formatter import ReferenceFormatter

_HEURISTIC_AUTHOR_METHODS = {
    "generic_front_matter",
    "layout_block_after_title",
    "text_after_title",
}
_HUMAN_REVIEW_METHODS = {
    "api_review",
    "review_memory_exact",
}


def assess_reference(document: ProcessedDocument) -> ReferenceQualityAssessment:
    """Classify whether a generated reference is ready, reviewable, or blocked.

    This gate does not compare against a hidden answer key. It relies only on
    extraction status, visible field evidence, confidence, document type, and
    explicit human approval.
    """
    if not document.include_in_output:
        return _assessment(
            document,
            ReferenceReadiness.BLOCKED,
            [QualityIssueCode.SECONDARY_VARIANT],
        )

    if document.status is ProcessingStatus.FAILED:
        return _assessment(
            document,
            ReferenceReadiness.BLOCKED,
            [QualityIssueCode.EXTRACTION_BLOCKED],
        )

    resolved = document.resolved_bibliography
    if resolved is not None:
        if resolved.schema_id is None:
            return _assessment(
                document,
                ReferenceReadiness.BLOCKED,
                [QualityIssueCode.REFERENCE_SCHEMA_NOT_IDENTIFIED],
            )
        if resolved.schema_id not in ReferenceFormatter.supported_schema_ids():
            return _assessment(
                document,
                ReferenceReadiness.BLOCKED,
                [QualityIssueCode.REFERENCE_SCHEMA_NOT_IMPLEMENTED],
            )
        if resolved.missing_required_fields:
            return _assessment(
                document,
                ReferenceReadiness.BLOCKED,
                [QualityIssueCode.REQUIRED_REFERENCE_FIELD_MISSING],
            )
    elif document.status is ProcessingStatus.REVIEW_REQUIRED:
        return _assessment(
            document,
            ReferenceReadiness.BLOCKED,
            [QualityIssueCode.EXTRACTION_BLOCKED],
        )

    if not document.generated_reference:
        return _assessment(
            document,
            ReferenceReadiness.BLOCKED,
            [QualityIssueCode.REFERENCE_NOT_GENERATED],
        )

    if _is_human_approved(document):
        return _assessment(document, ReferenceReadiness.READY, [])

    issues: list[QualityIssueCode] = []
    metadata = document.metadata
    if resolved is not None and resolved.conflicting_fields:
        issues.append(QualityIssueCode.REFERENCE_FIELD_CONFLICT)

    if document.native_page_count == 0 and document.ocr_page_count > 0:
        issues.append(QualityIssueCode.OCR_ONLY_SOURCE)

    if metadata.authors and metadata.authors_evidence.method in _HEURISTIC_AUTHOR_METHODS:
        issues.append(QualityIssueCode.HEURISTIC_AUTHOR_EXTRACTION)

    if metadata.title.value and metadata.title.confidence < 0.9:
        issues.append(QualityIssueCode.LOW_TITLE_CONFIDENCE)

    if metadata.authors and metadata.authors_evidence.confidence < 0.9:
        issues.append(QualityIssueCode.LOW_AUTHOR_CONFIDENCE)

    if _critical_field_uses_low_confidence_ocr(document):
        issues.append(QualityIssueCode.LOW_CONFIDENCE_OCR_EVIDENCE)

    if WarningCode.BIBTEX_CONFLICT_REVIEW in document.warnings:
        issues.append(QualityIssueCode.STRUCTURED_METADATA_CONFLICT)

    if document.correction_suggestions:
        issues.append(QualityIssueCode.CORRECTION_SUGGESTION_AVAILABLE)

    if resolved is None and metadata.document_type is DocumentType.UNKNOWN:
        issues.append(QualityIssueCode.UNSUPPORTED_DOCUMENT_TYPE)

    readiness = ReferenceReadiness.REVIEW_REQUIRED if issues else ReferenceReadiness.READY
    return _assessment(document, readiness, _unique(issues))


def build_reference_quality_report(
    documents: list[ProcessedDocument],
) -> dict[str, object]:
    """Build a machine-readable readiness report for all physical documents."""
    assessments = [assess_reference(document) for document in documents]
    selected = [
        assessment
        for assessment in assessments
        if QualityIssueCode.SECONDARY_VARIANT not in assessment.issues
    ]
    counts = Counter(assessment.readiness.value for assessment in selected)
    return {
        "physical_documents": len(documents),
        "selected_works": len(selected),
        "generated_references": sum(assessment.reference_generated for assessment in selected),
        "ready_references": counts[ReferenceReadiness.READY.value],
        "review_required_references": counts[ReferenceReadiness.REVIEW_REQUIRED.value],
        "blocked_references": counts[ReferenceReadiness.BLOCKED.value],
        "policy": {
            "hidden_answer_key_used": False,
            "hash_bound_metadata_used": False,
            "explicit_human_approval_can_clear_review_flags": True,
            "drafts_are_exported_separately": True,
        },
        "documents": [assessment.model_dump(mode="json") for assessment in assessments],
    }


def ready_reference_documents(
    documents: Iterable[ProcessedDocument],
) -> list[ProcessedDocument]:
    """Return selected documents whose references passed the quality gate."""
    return [
        document
        for document in documents
        if assess_reference(document).readiness is ReferenceReadiness.READY
    ]


def review_reference_documents(
    documents: Iterable[ProcessedDocument],
) -> list[ProcessedDocument]:
    """Return selected generated references that still need review."""
    return [
        document
        for document in documents
        if assess_reference(document).readiness is ReferenceReadiness.REVIEW_REQUIRED
    ]


def _critical_field_uses_low_confidence_ocr(
    document: ProcessedDocument,
) -> bool:
    page_by_number = {page.page_number: page for page in document.pages}
    metadata = document.metadata
    evidence = [
        metadata.title,
        metadata.authors_evidence,
        metadata.journal,
        metadata.year,
        metadata.volume,
        metadata.pages,
        metadata.article_number,
        metadata.institution,
        metadata.degree,
        metadata.total_pages,
        metadata.department,
    ]
    for field in evidence:
        if field.value is None or field.page_number is None:
            continue
        page = page_by_number.get(field.page_number)
        if (
            page is not None
            and page.method is ExtractionMethod.OCR
            and page.confidence is not None
            and page.confidence < 0.8
        ):
            return True
    return False


def _is_human_approved(document: ProcessedDocument) -> bool:
    if document.review_state not in {
        ReviewState.APPROVED,
        ReviewState.CORRECTED,
    }:
        return False
    if document.review_state is ReviewState.APPROVED:
        return True

    record = document.bibliographic_record
    if record is not None:
        if record.schema_override is not None:
            return True
        if any(candidate.method in _HUMAN_REVIEW_METHODS for candidate in record.field_candidates):
            return True
        if record.excluded_field_ids:
            return True

    metadata = document.metadata
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
    ]
    return any(item.method in _HUMAN_REVIEW_METHODS for item in evidence)


def _assessment(
    document: ProcessedDocument,
    readiness: ReferenceReadiness,
    issues: list[QualityIssueCode],
) -> ReferenceQualityAssessment:
    return ReferenceQualityAssessment(
        source_file=document.source_path.name,
        sha256=document.sha256,
        canonical_key=document.canonical_key,
        variant_type=document.variant_type,
        readiness=readiness,
        issues=issues,
        review_state=document.review_state,
        reference_generated=document.generated_reference is not None,
        generated_reference=document.generated_reference,
    )


def _unique(values: list[QualityIssueCode]) -> list[QualityIssueCode]:
    return list(dict.fromkeys(values))

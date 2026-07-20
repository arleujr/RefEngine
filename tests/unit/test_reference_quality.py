from __future__ import annotations

from pathlib import Path

from refengine.domain.enums import (
    DocumentType,
    ProcessingStatus,
    QualityIssueCode,
    ReferenceReadiness,
    ReviewState,
    VariantType,
)
from refengine.domain.models import (
    ArticleMetadata,
    Author,
    Evidence,
    ProcessedDocument,
)
from refengine.services.reference_quality import assess_reference


def evidence(
    value: str | None, confidence: float = 0.98, method: str = "publisher_profile"
) -> Evidence:
    return Evidence(
        value=value,
        confidence=confidence if value else 0,
        page_number=1 if value else None,
        excerpt=value,
        method=method,
    )


def journal_document(*, author_method: str = "publisher_profile") -> ProcessedDocument:
    metadata = ArticleMetadata(
        title=evidence("Article title"),
        authors=[Author(full_name="Ana Silva", family_name="Silva", given_names="Ana")],
        authors_evidence=evidence("Ana Silva", method=author_method),
        journal=evidence("Journal"),
        place=evidence(None),
        year=evidence("2025"),
        publication_month=evidence(None),
        volume=evidence("10"),
        issue=evidence(None),
        pages=evidence("1-10"),
        article_number=evidence(None),
        doi=evidence("10.0000/example"),
        url=evidence("https://doi.org/10.0000/example"),
        extractor="test",
        document_type=DocumentType.JOURNAL_ARTICLE,
    )
    return ProcessedDocument(
        source_path=Path("article.pdf"),
        sha256="abc",
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.PROCESSED_WITH_WARNINGS,
        generated_reference="SILVA, Ana. Article title...",
        variant_type=VariantType.PUBLISHER_ORIGINAL,
        canonical_key="article",
        include_in_output=True,
    )


def test_strong_automatic_reference_is_ready() -> None:
    assessment = assess_reference(journal_document())

    assert assessment.readiness is ReferenceReadiness.READY
    assert assessment.issues == []


def test_heuristic_author_extraction_requires_review() -> None:
    assessment = assess_reference(journal_document(author_method="layout_block_after_title"))

    assert assessment.readiness is ReferenceReadiness.REVIEW_REQUIRED
    assert QualityIssueCode.HEURISTIC_AUTHOR_EXTRACTION in assessment.issues


def test_explicit_human_approval_promotes_reference() -> None:
    document = journal_document(author_method="layout_block_after_title")
    document.review_state = ReviewState.APPROVED

    assessment = assess_reference(document)

    assert assessment.readiness is ReferenceReadiness.READY
    assert assessment.issues == []


def test_secondary_variant_is_blocked_from_final_output() -> None:
    document = journal_document()
    document.include_in_output = False

    assessment = assess_reference(document)

    assert assessment.readiness is ReferenceReadiness.BLOCKED
    assert assessment.issues == [QualityIssueCode.SECONDARY_VARIANT]

from refengine.domain.enums import ErrorCode, ProcessingStatus
from refengine.domain.models import ArticleMetadata, Author, Evidence
from refengine.services.validation import classify_metadata


def evidence(value: str | None, confidence: float = 1.0) -> Evidence:
    return Evidence(value=value, confidence=confidence, method="test")


def test_marks_missing_journal_for_review() -> None:
    metadata = ArticleMetadata(
        title=evidence("A valid title"),
        authors=[Author(full_name="Ana Silva", family_name="Silva", given_names="Ana")],
        authors_evidence=evidence("Ana Silva", 0.9),
        journal=evidence(None, 0),
        place=evidence(None, 0),
        year=evidence("2024"),
        publication_month=evidence(None, 0),
        volume=evidence(None, 0),
        issue=evidence(None, 0),
        pages=evidence(None, 0),
        article_number=evidence("10"),
        doi=evidence(None, 0),
        url=evidence(None, 0),
        extractor="test",
    )

    status, errors = classify_metadata(metadata)

    assert status is ProcessingStatus.REVIEW_REQUIRED
    assert ErrorCode.JOURNAL_NOT_FOUND in errors


def test_metadata_ocr_can_limit_processing_to_front_matter() -> None:
    from refengine.infrastructure.pdf.document_processor import DocumentProcessor

    processor = DocumentProcessor(
        metadata_ocr_page_limit=3,
        include_last_page_in_metadata_mode=False,
    )

    assert processor._ocr_indexes(20) == {0, 1, 2}

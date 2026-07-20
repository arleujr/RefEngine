from datetime import date
from pathlib import Path

from refengine.domain.enums import ProcessingStatus
from refengine.domain.models import ArticleMetadata, Evidence, ProcessedDocument
from refengine.services.reference_compiler import ReferenceCompiler
from refengine.services.reference_formatter import ReferenceFormatter


def ev(value: str | None) -> Evidence:
    return Evidence(value=value, confidence=1 if value else 0, method="test")


def test_review_required_document_has_no_final_reference() -> None:
    metadata = ArticleMetadata(
        title=ev("Title"),
        authors=[],
        authors_evidence=ev(None),
        journal=ev(None),
        place=ev(None),
        year=ev("2024"),
        publication_month=ev(None),
        volume=ev(None),
        issue=ev(None),
        pages=ev(None),
        article_number=ev(None),
        doi=ev(None),
        url=ev(None),
        extractor="test",
    )
    document = ProcessedDocument(
        source_path=Path("x.pdf"),
        sha256="x",
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.REVIEW_REQUIRED,
    )
    result = ReferenceCompiler(ReferenceFormatter()).compile([document], date(2025, 1, 1))[0]
    assert result.generated_reference is None

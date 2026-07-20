from datetime import date
from pathlib import Path

from refengine.domain.enums import ProcessingStatus
from refengine.domain.models import ArticleMetadata, Evidence, ProcessedDocument
from refengine.infrastructure.export.reference_report_exporter import export_reference_report
from refengine.services.bibliographic_record import record_from_metadata
from refengine.services.reference_compiler import ReferenceCompiler
from refengine.services.reference_formatter import ReferenceFormatter


def ev(value: str | None) -> Evidence:
    return Evidence(value=value, confidence=1.0 if value else 0.0, method="test")


def test_report_names_missing_required_fields(tmp_path: Path) -> None:
    metadata = ArticleMetadata(
        title=ev("Incomplete article"),
        authors=[],
        authors_evidence=ev(None),
        journal=ev("Journal"),
        place=ev("Viçosa"),
        year=ev("2024"),
        publication_month=ev(None),
        volume=ev("1"),
        issue=ev(None),
        pages=ev("1-2"),
        article_number=ev(None),
        doi=ev(None),
        url=ev(None),
        extractor="test",
    )
    document = ProcessedDocument(
        source_path=Path("incomplete.pdf"),
        sha256="d" * 64,
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.PROCESSED,
    )
    document.bibliographic_record = record_from_metadata(metadata, document.source_path)
    compiled = ReferenceCompiler(ReferenceFormatter()).compile([document], date(2026, 7, 14))
    output = tmp_path / "reference_report.txt"
    export_reference_report(compiled, output)
    text = output.read_text(encoding="utf-8")
    assert "Blocked references: 1" in text
    assert "Autores pessoais" in text
    assert "5.12.21" in text

import json
from pathlib import Path

from refengine.domain.enums import DocumentType, ProcessingStatus, VariantType
from refengine.domain.models import ArticleMetadata, Evidence, ProcessedDocument
from refengine.infrastructure.export.bibliographic_candidates_exporter import (
    export_bibliographic_candidates,
)
from refengine.services.bibliographic_record import record_from_metadata


def evidence(value: str | None) -> Evidence:
    return Evidence(
        value=value,
        confidence=0.9 if value else 0,
        method="fixture",
        excerpt=value,
    )


def test_exports_candidate_ledger(tmp_path: Path) -> None:
    metadata = ArticleMetadata(
        title=evidence("Example article"),
        authors=[],
        authors_evidence=evidence(None),
        journal=evidence("Journal"),
        place=evidence(None),
        year=evidence("2025"),
        publication_month=evidence(None),
        volume=evidence(None),
        issue=evidence(None),
        pages=evidence(None),
        article_number=evidence(None),
        doi=evidence(None),
        url=evidence(None),
        extractor="fixture",
        document_type=DocumentType.JOURNAL_ARTICLE,
    )
    document = ProcessedDocument(
        source_path=Path("example.pdf"),
        sha256="a" * 64,
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.PROCESSED,
        variant_type=VariantType.PUBLISHER_ORIGINAL,
        bibliographic_record=record_from_metadata(metadata, Path("example.pdf")),
    )
    output = tmp_path / "candidates.json"

    export_bibliographic_candidates([document], output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload[0]["record"]["source_files"] == ["example.pdf"]
    assert any(
        candidate["field_id"] == "title" for candidate in payload[0]["record"]["field_candidates"]
    )

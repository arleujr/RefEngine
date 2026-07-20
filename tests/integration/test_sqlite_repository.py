from pathlib import Path

from refengine.domain.enums import ProcessingStatus
from refengine.domain.models import ArticleMetadata, Author, Evidence, ProcessedDocument
from refengine.infrastructure.persistence.sqlite_repository import SqliteDocumentRepository


def evidence(value: str | None, confidence: float = 1.0) -> Evidence:
    return Evidence(value=value, confidence=confidence, method="test")


def test_saves_processed_document(tmp_path: Path) -> None:
    repository = SqliteDocumentRepository(tmp_path / "catalog.sqlite3")
    metadata = ArticleMetadata(
        title=evidence("Title"),
        authors=[Author(full_name="Ana Silva", family_name="Silva", given_names="Ana")],
        authors_evidence=evidence("Ana Silva"),
        journal=evidence("Journal"),
        place=evidence(None, 0),
        year=evidence("2024"),
        publication_month=evidence(None, 0),
        volume=evidence(None, 0),
        issue=evidence(None, 0),
        pages=evidence(None, 0),
        article_number=evidence("1"),
        doi=evidence(None, 0),
        url=evidence(None, 0),
        extractor="test",
    )
    document = ProcessedDocument(
        source_path=Path("article.pdf"),
        sha256="abc",
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.PROCESSED,
        generated_reference="SILVA, Ana. Title. Journal, [s. l.], art. 1, 2024.",
    )

    repository.save(document)

    assert (tmp_path / "catalog.sqlite3").exists()

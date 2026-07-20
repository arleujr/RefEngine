from pathlib import Path

from refengine.domain.enums import DocumentType, ProcessingStatus, VariantType
from refengine.domain.models import ArticleMetadata, Evidence, ProcessedDocument
from refengine.infrastructure.persistence.extraction_cache import ExtractionCache


def evidence(value: str | None) -> Evidence:
    return Evidence(value=value, confidence=1.0 if value else 0.0, method="test")


def document(source: Path) -> ProcessedDocument:
    metadata = ArticleMetadata(
        title=evidence("Cached title"),
        authors=[],
        authors_evidence=evidence(None),
        journal=evidence("Journal"),
        place=evidence(None),
        year=evidence("2024"),
        publication_month=evidence(None),
        volume=evidence("1"),
        issue=evidence(None),
        pages=evidence("1-2"),
        article_number=evidence(None),
        doi=evidence(None),
        url=evidence(None),
        extractor="test",
        document_type=DocumentType.JOURNAL_ARTICLE,
    )
    return ProcessedDocument(
        source_path=source,
        sha256="a" * 64,
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.PROCESSED,
        variant_type=VariantType.PUBLISHER_ORIGINAL,
    )


def test_cache_is_keyed_by_source_and_processor_signature(tmp_path: Path) -> None:
    cache = ExtractionCache(tmp_path / "cache.sqlite3")
    source = tmp_path / "article.pdf"
    cached = document(source)

    cache.put(cached, "signature-a")

    hit = cache.get(cached.sha256, "signature-a")
    miss = cache.get(cached.sha256, "signature-b")

    assert hit is not None
    assert hit.metadata.title.value == "Cached title"
    assert miss is None
    assert cache.summary().entries == 1
    assert cache.integrity_check() == "ok"


def test_cache_clear_does_not_delete_database(tmp_path: Path) -> None:
    cache = ExtractionCache(tmp_path / "cache.sqlite3")
    cache.put(document(tmp_path / "article.pdf"), "signature")

    assert cache.clear() == 1
    assert cache.summary().entries == 0
    assert cache.database_path.exists()

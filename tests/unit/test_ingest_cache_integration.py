from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from refengine.application.ingest_folder import IngestFolder
from refengine.domain.enums import DocumentType, ExtractionMethod
from refengine.domain.models import ArticleMetadata, Author, Evidence, PageText
from refengine.infrastructure.persistence.extraction_cache import ExtractionCache
from refengine.services.reference_formatter import ReferenceFormatter


def evidence(value: str | None) -> Evidence:
    return Evidence(value=value, confidence=1.0 if value else 0.0, method="test")


class CountingProcessor:
    def __init__(self) -> None:
        self.calls = 0

    def cache_signature(self) -> str:
        return "processor-v1"

    def sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def process_pages(self, path: Path) -> list[PageText]:
        self.calls += 1
        return [
            PageText(
                page_number=1,
                text="enough native content for a deterministic test",
                method=ExtractionMethod.NATIVE,
                character_count=48,
            )
        ]


class Extractor:
    def extract(self, path: Path, pages: list[PageText]) -> ArticleMetadata:
        author = Author(full_name="Ana Silva", family_name="Silva", given_names="Ana")
        return ArticleMetadata(
            title=evidence("A cached article"),
            authors=[author],
            authors_evidence=evidence(author.full_name),
            journal=evidence("Journal"),
            place=evidence("Viçosa"),
            year=evidence("2024"),
            publication_month=evidence(None),
            volume=evidence("1"),
            issue=evidence("1"),
            pages=evidence("1-2"),
            article_number=evidence(None),
            doi=evidence(None),
            url=evidence(None),
            extractor="test",
            document_type=DocumentType.JOURNAL_ARTICLE,
        )


class Repository:
    def __init__(self) -> None:
        self.saved = []

    def save_many(self, documents):
        self.saved = list(documents)


def test_second_run_reuses_raw_pdf_extraction(tmp_path: Path) -> None:
    source = tmp_path / "article.pdf"
    source.write_bytes(b"same document")
    processor = CountingProcessor()
    cache = ExtractionCache(tmp_path / "cache.sqlite3")

    first = IngestFolder(
        processor=processor,  # type: ignore[arg-type]
        extractor=Extractor(),  # type: ignore[arg-type]
        formatter=ReferenceFormatter(),
        repository=Repository(),  # type: ignore[arg-type]
        extraction_cache=cache,
    )
    first.execute(tmp_path, date(2026, 7, 14))

    second = IngestFolder(
        processor=processor,  # type: ignore[arg-type]
        extractor=Extractor(),  # type: ignore[arg-type]
        formatter=ReferenceFormatter(),
        repository=Repository(),  # type: ignore[arg-type]
        extraction_cache=cache,
    )
    documents = second.execute(tmp_path, date(2026, 7, 14))

    assert processor.calls == 1
    assert first.stats.cache_misses == 1
    assert first.stats.cache_writes == 1
    assert second.stats.cache_hits == 1
    assert documents[0].generated_reference is not None


class VersionedExtractor(Extractor):
    def __init__(self, signature: str) -> None:
        self.signature = signature

    def cache_signature(self) -> str:
        return self.signature


def test_extractor_signature_invalidates_cached_pdf_metadata(tmp_path: Path) -> None:
    source = tmp_path / "article.pdf"
    source.write_bytes(b"same document")
    processor = CountingProcessor()
    cache = ExtractionCache(tmp_path / "cache.sqlite3")

    first = IngestFolder(
        processor=processor,  # type: ignore[arg-type]
        extractor=VersionedExtractor("extractor-v1"),  # type: ignore[arg-type]
        formatter=ReferenceFormatter(),
        repository=Repository(),  # type: ignore[arg-type]
        extraction_cache=cache,
    )
    first.execute(tmp_path, date(2026, 7, 14))

    second = IngestFolder(
        processor=processor,  # type: ignore[arg-type]
        extractor=VersionedExtractor("extractor-v2"),  # type: ignore[arg-type]
        formatter=ReferenceFormatter(),
        repository=Repository(),  # type: ignore[arg-type]
        extraction_cache=cache,
    )
    second.execute(tmp_path, date(2026, 7, 14))

    assert processor.calls == 2
    assert second.stats.cache_misses == 1
    assert second.stats.cache_hits == 0

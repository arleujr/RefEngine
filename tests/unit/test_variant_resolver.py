from pathlib import Path

from refengine.domain.enums import ProcessingStatus, VariantType, WarningCode
from refengine.domain.models import ArticleMetadata, Evidence, ProcessedDocument
from refengine.services.variant_resolver import resolve_variants


def ev(value: str | None) -> Evidence:
    return Evidence(value=value, confidence=1 if value else 0, method="test")


def metadata() -> ArticleMetadata:
    return ArticleMetadata(
        title=ev("Title"),
        authors=[],
        authors_evidence=ev(None),
        journal=ev("Journal"),
        place=ev(None),
        year=ev("2024"),
        publication_month=ev(None),
        volume=ev("1"),
        issue=ev(None),
        pages=ev(None),
        article_number=ev("1"),
        doi=ev("10.1/test"),
        url=ev(None),
        extractor="test",
    )


def test_prefers_publisher_original_and_excludes_browser_print() -> None:
    original = ProcessedDocument(
        source_path=Path("original.pdf"),
        sha256="a",
        pages=[],
        metadata=metadata(),
        status=ProcessingStatus.PROCESSED,
        variant_type=VariantType.PUBLISHER_ORIGINAL,
        canonical_key="doi:x",
    )
    printed = ProcessedDocument(
        source_path=Path("print.pdf"),
        sha256="b",
        pages=[],
        metadata=metadata(),
        status=ProcessingStatus.PROCESSED,
        variant_type=VariantType.BROWSER_PRINT,
        canonical_key="doi:x",
    )

    result = resolve_variants([printed, original])
    selected = next(item for item in result if item.sha256 == "a")
    duplicate = next(item for item in result if item.sha256 == "b")

    assert selected.include_in_output is True
    assert duplicate.include_in_output is False
    assert WarningCode.DUPLICATE_VARIANT in duplicate.warnings


def test_merges_original_and_print_copy_when_cleaned_filenames_and_year_match() -> None:
    original_metadata = metadata()
    printed_metadata = metadata().model_copy(deep=True)
    printed_metadata.title = Evidence(
        value="Wrong heading extracted from browser print",
        confidence=0.55,
        method="text_heading_heuristic",
    )
    printed_metadata.authors = []
    printed_metadata.authors_evidence = ev(None)
    printed_metadata.doi = ev(None)

    original = ProcessedDocument(
        source_path=Path("Study title pdf original.pdf"),
        sha256="original",
        pages=[],
        metadata=original_metadata,
        status=ProcessingStatus.PROCESSED,
        variant_type=VariantType.PUBLISHER_ORIGINAL,
        canonical_key="title:title|year:2024",
    )
    printed = ProcessedDocument(
        source_path=Path("Study title pdf impresso.pdf"),
        sha256="printed",
        pages=[],
        metadata=printed_metadata,
        status=ProcessingStatus.PROCESSED_WITH_WARNINGS,
        variant_type=VariantType.BROWSER_PRINT,
        canonical_key="title:wrong heading|year:2024",
    )

    result = resolve_variants([printed, original])

    assert sum(item.include_in_output for item in result) == 1
    assert next(item for item in result if item.sha256 == "printed").include_in_output is False

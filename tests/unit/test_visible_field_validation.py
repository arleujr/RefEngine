from refengine.domain.enums import DocumentType, ErrorCode, WarningCode
from refengine.domain.models import ArticleMetadata, Evidence
from refengine.services.validation import classify_metadata, collect_warnings


def evidence(value: str | None, method: str) -> Evidence:
    return Evidence(
        value=value,
        confidence=0.95 if value else 0,
        method=method,
    )


def test_collapsed_author_section_has_precise_diagnostic() -> None:
    metadata = ArticleMetadata(
        title=evidence("Visible title", "web_print_profile"),
        authors=[],
        authors_evidence=evidence(None, "not_visible_in_print"),
        journal=evidence("Scientia Agricola", "web_print_profile"),
        place=evidence("Piracicaba", "web_print_profile"),
        year=evidence("2015", "web_print_profile"),
        publication_month=evidence("July/August", "web_print_profile"),
        volume=evidence("72", "web_print_profile"),
        issue=evidence("4", "web_print_profile"),
        pages=evidence(None, "not_visible_in_print"),
        article_number=evidence(None, "not_visible_in_print"),
        doi=evidence("10.1590/example", "doi_regex"),
        url=evidence("https://doi.org/10.1590/example", "web_print_profile"),
        extractor="scielo_web_print",
        document_type=DocumentType.JOURNAL_ARTICLE,
    )

    _, errors = classify_metadata(metadata)
    warnings = collect_warnings([], metadata)

    assert ErrorCode.AUTHORS_NOT_VISIBLE_IN_SOURCE in errors
    assert WarningCode.SOURCE_FIELD_NOT_VISIBLE in warnings
    assert ErrorCode.AUTHORS_AMBIGUOUS not in errors

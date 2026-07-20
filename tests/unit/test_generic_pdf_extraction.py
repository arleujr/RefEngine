from refengine.domain.enums import DocumentType, ExtractionMethod
from refengine.domain.models import PageText
from refengine.services.document_classifier import classify_document_type
from refengine.services.generic_pdf import article_signals, generic_periodical_fields


def page(number: int, text: str) -> PageText:
    return PageText(
        page_number=number,
        text=text,
        method=ExtractionMethod.NATIVE,
        character_count=len(text),
        confidence=1.0,
    )


def test_generic_article_is_identified_from_independent_structure_signals() -> None:
    pages = [
        page(
            1,
            """
            A generic article title
            Ana Silva; Bruno Souza
            Journal of Applied Examples 12 (2024) 101-112
            DOI: 10.1234/example.2024.15

            Abstract
            This study evaluates a generic extraction strategy.
            Keywords: metadata; references; PDF
            Received 2 January 2024; Accepted 10 March 2024
            """,
        ),
        page(2, "Methods and results."),
        page(3, "References\nSILVA, A. Previous work. 2020."),
    ]

    signals = article_signals(pages)

    assert signals.has_doi is True
    assert signals.has_abstract is True
    assert signals.has_references is True
    assert signals.looks_like_periodical_article is True
    assert classify_document_type(pages) is DocumentType.JOURNAL_ARTICLE


def test_generic_parser_extracts_visible_periodical_metadata() -> None:
    text = """
    A generic article title
    Ana Silva; Bruno Souza
    Journal of Applied Examples 12 (2024) 101-112
    DOI: 10.1234/example.2024.15
    Available online 18 April 2024
    https://publisher.example/articles/15
    Abstract
    Text.
    """

    result = generic_periodical_fields(
        text,
        text,
        doi="10.1234/example.2024.15",
    )

    assert result["title"] == "A generic article title"
    assert result["authors"] == "Ana Silva; Bruno Souza"
    assert result["journal"] == "Journal of Applied Examples"
    assert result["volume"] == "12"
    assert result["year"] == "2024"
    assert result["pages"] == "101-112"
    assert result["source_url"] == "https://publisher.example/articles/15"
    assert result["extractor"] == "generic_periodical_structure"


def test_conference_pdf_is_not_forced_into_journal_article_schema() -> None:
    pages = [
        page(
            1,
            """
            Proceedings of the 8th International Conference on Examples
            A conference paper
            DOI: 10.1234/conf.2024.15
            Abstract
            Conference paper abstract.
            Keywords: conference; example
            """,
        ),
        page(2, "References\nExample reference."),
    ]

    assert article_signals(pages).has_event_marker is True
    assert classify_document_type(pages) is DocumentType.UNKNOWN

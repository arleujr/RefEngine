from refengine.domain.models import ArticleMetadata, Evidence
from refengine.services.document_classifier import canonical_key


def e(value: str | None) -> Evidence:
    return Evidence(value=value, confidence=1 if value else 0, method="test")


def metadata(title: str, year: str, doi: str) -> ArticleMetadata:
    return ArticleMetadata(
        title=e(title),
        authors=[],
        authors_evidence=e(None),
        journal=e("Journal"),
        place=e(None),
        year=e(year),
        publication_month=e(None),
        volume=e(None),
        issue=e(None),
        pages=e(None),
        article_number=e(None),
        doi=e(doi),
        url=e(None),
        extractor="test",
    )


def test_title_and_year_group_variants_even_when_doi_differs() -> None:
    original = metadata("Qualidade fisiológica de sementes", "2009", "10.4025/example")
    printed = metadata("Qualidade fisiológica de sementes", "2009", "10.1590/example")
    assert canonical_key(original) == canonical_key(printed)


from refengine.domain.enums import DocumentType, ExtractionMethod
from refengine.domain.models import PageText
from refengine.services.document_classifier import classify_document_type


def test_article_is_not_misclassified_from_manual_citation_in_later_page() -> None:
    pages = [
        PageText(
            page_number=1,
            text=(
                "DOI: 10.4025/actasciagron.v31i2.396 "
                "Acta Scientiarum. Agronomy Maringá, v. 31, n. 2, p. 307-312, 2009"
            ),
            method=ExtractionMethod.NATIVE,
            character_count=120,
        ),
        PageText(
            page_number=2,
            text="O teste seguiu as Regras para análise de sementes do Ministério da Agricultura.",
            method=ExtractionMethod.NATIVE,
            character_count=87,
        ),
    ]

    assert classify_document_type(pages) is DocumentType.JOURNAL_ARTICLE


def test_academic_work_tolerates_common_ocr_spelling_of_dissertacao() -> None:
    pages = [
        PageText(
            page_number=1,
            text=(
                "Dissertagao (mestrado) apresentada ao Programa de Pós-Graduação "
                "em Fitotecnia da Universidade Federal de Viçosa."
            ),
            method=ExtractionMethod.OCR,
            character_count=120,
        )
    ]

    assert classify_document_type(pages) is DocumentType.DISSERTATION

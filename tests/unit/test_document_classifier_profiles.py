from refengine.domain.enums import DocumentType, ExtractionMethod
from refengine.domain.models import PageText
from refengine.services.document_classifier import classify_document_type


def page(text: str) -> PageText:
    return PageText(
        page_number=1,
        text=text,
        method=ExtractionMethod.NATIVE,
        character_count=len(text),
        confidence=1.0,
    )


def test_ieee_front_matter_is_journal_article() -> None:
    result = classify_document_type(
        [
            page(
                "Received 17 March 2023, accepted 6 April 2023, "
                "date of publication 10 April 2023. "
                "Digital Object Identifier 10.1109/ACCESS.2023.3265998"
            )
        ]
    )
    assert result is DocumentType.JOURNAL_ARTICLE


def test_mdpi_sensors_footer_is_journal_article() -> None:
    result = classify_document_type(
        [page("Sensors 2020, 20, 4319; doi:10.3390/s20154319 www.mdpi.com/journal/sensors")]
    )
    assert result is DocumentType.JOURNAL_ARTICLE

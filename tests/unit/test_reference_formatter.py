from datetime import date

from refengine.domain.bibliography import (
    ResolutionStatus,
    ResolvedBibliographicField,
    ResolvedBibliographicRecord,
)
from refengine.services.reference_formatter import ReferenceFormatter


def field(field_id: str, value: str) -> ResolvedBibliographicField:
    return ResolvedBibliographicField(
        field_id=field_id,
        values=[value],
        status=ResolutionStatus.SELECTED,
        confidence=1.0,
        reason="test",
    )


def resolved_article(
    month: str = "Aug.", doi: str = "10.3390/s20154319"
) -> ResolvedBibliographicRecord:
    return ResolvedBibliographicRecord(
        record_id="article",
        schema_id="ufv.22",
        family="periodical_article",
        medium="electronic",
        fields={
            "authors": field("authors", "André Dantas de Medeiros"),
            "title": field("title", "Machine Learning for Seed Quality Classification"),
            "periodical_title": field("periodical_title", "Sensors"),
            "place": field("place", "Basel"),
            "publication_year": field("publication_year", "2020"),
            "publication_month": field("publication_month", month),
            "volume": field("volume", "20"),
            "issue": field("issue", "15"),
            "article_number": field("article_number", "4319"),
            "doi": field("doi", doi),
            "url": field("url", "https://doi.org/10.3390/s20154319"),
            "access_date": field("access_date", "2026-07-12"),
        },
        ready_for_formatting=True,
    )


def test_formats_article_number_without_page_label() -> None:
    result = ReferenceFormatter().format_resolved(
        resolved_article(),
        date(2026, 7, 12),
    )

    assert result is not None
    assert "art. 4319" in result
    assert "p. 4319" not in result
    assert "DOI: https://doi.org/10.3390/s20154319" in result
    assert "Disponível em:" not in result
    assert "Acesso em:" not in result


def test_normalizes_english_month_to_portuguese() -> None:
    result = ReferenceFormatter().format_resolved(
        resolved_article("Apr."),
        date(2026, 7, 12),
    )

    assert result is not None
    assert ", abr. 2020." in result
    assert "Apr." not in result


def test_normalizes_doi_url_without_duplicating_prefix() -> None:
    result = ReferenceFormatter().format_resolved(
        resolved_article(doi="https://doi.org/10.3390/s20154319"),
        date(2026, 7, 12),
    )

    assert result is not None
    assert "https://doi.org/https://" not in result
    assert "DOI: https://doi.org/10.3390/s20154319." in result


def test_keeps_a_distinct_repository_url_beside_the_doi() -> None:
    record = resolved_article()
    record.fields["url"] = field("url", "https://repository.example.org/items/4319")

    result = ReferenceFormatter().format_resolved(record, date(2026, 7, 12))

    assert result is not None
    assert "DOI: https://doi.org/10.3390/s20154319." in result
    assert "Disponível em: https://repository.example.org/items/4319." in result
    assert "Acesso em: 12 jul. 2026." in result


def test_alphabetical_sort_key_ignores_accents() -> None:
    accented = resolved_article()
    accented.fields["authors"] = field("authors", "Ávila, Ana")
    plain = resolved_article()
    plain.fields["authors"] = field("authors", "Barros, Bruno")

    formatter = ReferenceFormatter()

    assert formatter.resolved_sort_key(accented) < formatter.resolved_sort_key(plain)

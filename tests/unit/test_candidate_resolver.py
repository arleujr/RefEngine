from datetime import date

from refengine.domain.bibliography import (
    BibliographicFieldCandidate,
    CanonicalBibliographicRecord,
    DocumentTypeCandidate,
    ResolutionStatus,
    SourceFormat,
)
from refengine.services.candidate_resolver import CandidateResolver


def candidate(
    field_id: str,
    value: str,
    *,
    source_format: SourceFormat,
    source_file: str,
    confidence: float = 0.95,
    method: str = "visible_text",
    sequence: int | None = None,
) -> BibliographicFieldCandidate:
    return BibliographicFieldCandidate(
        field_id=field_id,
        value=value,
        normalized_value=" ".join(value.casefold().replace("-", " ").split()),
        source_format=source_format,
        source_file=source_file,
        method=method,
        confidence=confidence,
        sequence=sequence,
    )


def article_record() -> CanonicalBibliographicRecord:
    return CanonicalBibliographicRecord(
        record_id="record",
        document_type_candidates=[
            DocumentTypeCandidate(
                schema_id="ufv.22",
                family="periodical_article",
                medium="electronic",
                source_format=SourceFormat.BIBTEX,
                source_file="article.bib",
                confidence=0.99,
                reason="BibTeX @article",
            )
        ],
        field_candidates=[
            candidate(
                "authors",
                "Julio Marcos Filho",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                sequence=1,
            ),
            candidate(
                "authors",
                "Julio Marcos Filho",
                source_format=SourceFormat.BIBTEX,
                source_file="article.bib",
                method="bibtex_metadata",
                sequence=1,
            ),
            candidate(
                "title",
                "Seed vigor testing",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "title",
                "Seed vigor testing",
                source_format=SourceFormat.BIBTEX,
                source_file="article.bib",
                method="bibtex_raw_field",
            ),
            candidate(
                "periodical_title",
                "Scientia Agricola",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "publication_year",
                "2015",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "url",
                "https://doi.org/10.1590/example",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
        ],
    )


def test_resolver_selects_complete_article_and_execution_access_date() -> None:
    resolved = CandidateResolver().resolve(article_record(), access_date=date(2026, 7, 14))

    assert resolved.schema_id == "ufv.22"
    assert resolved.ready_for_formatting is True
    assert resolved.missing_required_fields == []
    assert resolved.value_for("title") == "Seed vigor testing"
    assert resolved.value_for("access_date") == "2026-07-14"
    assert resolved.values_for("authors") == ["Julio Marcos Filho"]


def test_resolver_marks_close_high_confidence_disagreement() -> None:
    record = article_record()
    record.field_candidates.extend(
        [
            candidate(
                "title",
                "Seed vigour testing",
                source_format=SourceFormat.RIS,
                source_file="article.ris",
                confidence=0.99,
                method="ris_raw_field",
            )
        ]
    )

    resolved = CandidateResolver().resolve(record, access_date=date(2026, 7, 14))

    title = resolved.field("title")
    assert title is not None
    assert title.status is ResolutionStatus.CONFLICT
    assert "title" in resolved.conflicting_fields
    assert len(title.alternatives) >= 2


def test_resolver_prefers_reviewed_value_without_losing_alternative() -> None:
    record = article_record()
    record.field_candidates.append(
        candidate(
            "title",
            "Seed vigor testing: reviewed title",
            source_format=SourceFormat.PDF,
            source_file="article.pdf",
            confidence=1.0,
            method="api_review",
        )
    )

    resolved = CandidateResolver().resolve(record, access_date=date(2026, 7, 14))

    title = resolved.field("title")
    assert title is not None
    assert title.value == "Seed vigor testing: reviewed title"
    assert title.status is ResolutionStatus.SELECTED
    assert len(title.alternatives) >= 2


def test_monograph_accepts_corporate_responsibility_instead_of_personal_author() -> None:
    record = CanonicalBibliographicRecord(
        record_id="manual",
        document_type_candidates=[
            DocumentTypeCandidate(
                schema_id="ufv.1",
                family="monograph",
                medium="print",
                source_format=SourceFormat.PDF,
                source_file="manual.pdf",
                confidence=0.99,
                reason="manual classification",
            )
        ],
        field_candidates=[
            candidate(
                "corporate_author",
                "BRASIL. Ministério da Agricultura",
                source_format=SourceFormat.PDF,
                source_file="manual.pdf",
            ),
            candidate(
                "title",
                "Regras para análise de sementes",
                source_format=SourceFormat.PDF,
                source_file="manual.pdf",
            ),
            candidate(
                "place", "Brasília, DF", source_format=SourceFormat.PDF, source_file="manual.pdf"
            ),
            candidate(
                "publisher", "MAPA/ACS", source_format=SourceFormat.PDF, source_file="manual.pdf"
            ),
            candidate(
                "publication_year", "2009", source_format=SourceFormat.PDF, source_file="manual.pdf"
            ),
        ],
    )

    resolved = CandidateResolver().resolve(record, access_date=date(2026, 7, 14))

    assert resolved.ready_for_formatting is True
    assert resolved.missing_required_fields == []


def test_uses_normative_unknown_place_when_publication_place_is_absent() -> None:
    record = CanonicalBibliographicRecord(
        record_id="print-article-no-place",
        document_type_candidates=[
            DocumentTypeCandidate(
                schema_id="ufv.21",
                family="periodical_article",
                medium="print",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                confidence=0.99,
                reason="journal article",
            )
        ],
        field_candidates=[
            candidate(
                "authors",
                "Kazumasa Himi",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                sequence=1,
            ),
            candidate(
                "title",
                "Effect of seed coat color",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "periodical_title",
                "Euphytica",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "publication_year",
                "2002",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
        ],
    )

    resolved = CandidateResolver().resolve(record, access_date=date(2026, 7, 14))

    assert resolved.ready_for_formatting is True
    assert resolved.value_for("place") == "[S. l.]"
    assert resolved.field("place").selected_sources == ["catalog:<ufv-2025:5.4.3>"]


def test_aligns_doi_url_with_selected_doi_without_hiding_conflict() -> None:
    record = CanonicalBibliographicRecord(
        record_id="identifier-conflict",
        document_type_candidates=[
            DocumentTypeCandidate(
                schema_id="ufv.22",
                family="periodical_article",
                medium="electronic",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                confidence=0.99,
                reason="journal article",
            )
        ],
        field_candidates=[
            candidate(
                "authors",
                "Ana Silva",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                sequence=1,
            ),
            candidate(
                "title", "Example", source_format=SourceFormat.PDF, source_file="article.pdf"
            ),
            candidate(
                "periodical_title",
                "Journal",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "publication_year",
                "2024",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "doi",
                "10.4025/example",
                source_format=SourceFormat.BIBTEX,
                source_file="article.bib",
                method="bibtex_raw_field",
            ),
            candidate(
                "doi",
                "10.1590/other",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                method="doi_regex",
            ),
            candidate(
                "url",
                "https://doi.org/10.1590/other",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "url",
                "https://doi.org/10.4025/example",
                source_format=SourceFormat.RIS,
                source_file="article.ris",
                method="ris_raw_field",
            ),
        ],
    )

    resolved = CandidateResolver().resolve(record, access_date=date(2026, 7, 14))

    selected_doi = resolved.value_for("doi")
    assert selected_doi is not None
    assert (
        resolved.value_for("url")
        == f"https://doi.org/{CandidateResolver._normalize_doi(selected_doi)}"
    )
    assert resolved.field("url").status is ResolutionStatus.CONFLICT


def test_derives_doi_url_when_only_mismatched_doi_url_exists() -> None:
    record = CanonicalBibliographicRecord(
        record_id="identifier-derived",
        document_type_candidates=[
            DocumentTypeCandidate(
                schema_id="ufv.22",
                family="periodical_article",
                medium="electronic",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                confidence=0.99,
                reason="journal article",
            )
        ],
        field_candidates=[
            candidate(
                "authors",
                "Ana Silva",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                sequence=1,
            ),
            candidate(
                "title", "Example", source_format=SourceFormat.PDF, source_file="article.pdf"
            ),
            candidate(
                "periodical_title",
                "Journal",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "publication_year",
                "2024",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
            candidate(
                "doi",
                "10.4025/example",
                source_format=SourceFormat.BIBTEX,
                source_file="article.bib",
                method="bibtex_raw_field",
            ),
            candidate(
                "url",
                "https://doi.org/10.1590/other",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
            ),
        ],
    )

    resolved = CandidateResolver().resolve(record, access_date=date(2026, 7, 14))

    assert resolved.value_for("url") == "https://doi.org/10.4025/example"
    assert "derived locally" in resolved.field("url").reason

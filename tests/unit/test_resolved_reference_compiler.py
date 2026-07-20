from datetime import date
from pathlib import Path

from refengine.domain.bibliography import (
    BibliographicFieldCandidate,
    CanonicalBibliographicRecord,
    DocumentTypeCandidate,
    SourceFormat,
)
from refengine.domain.enums import DocumentType, ProcessingStatus
from refengine.domain.models import ArticleMetadata, Author, Evidence, ProcessedDocument
from refengine.services.reference_compiler import ReferenceCompiler
from refengine.services.reference_formatter import ReferenceFormatter


def ev(value: str | None) -> Evidence:
    return Evidence(value=value, confidence=0.95 if value else 0, method="legacy")


def test_compiler_formats_selected_candidates_not_legacy_metadata() -> None:
    metadata = ArticleMetadata(
        title=ev("Wrong legacy title"),
        authors=[Author(full_name="Wrong Person", family_name="Person", given_names="Wrong")],
        authors_evidence=ev("Wrong Person"),
        journal=ev("Wrong Journal"),
        place=ev("Wrong Place"),
        year=ev("1900"),
        publication_month=ev(None),
        volume=ev(None),
        issue=ev(None),
        pages=ev(None),
        article_number=ev(None),
        doi=ev(None),
        url=ev(None),
        extractor="test",
        document_type=DocumentType.JOURNAL_ARTICLE,
    )
    record = CanonicalBibliographicRecord(
        record_id="resolved",
        document_type_candidates=[
            DocumentTypeCandidate(
                schema_id="ufv.21",
                family="periodical_article",
                medium="print",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                confidence=0.99,
                reason="test",
            )
        ],
        field_candidates=[
            BibliographicFieldCandidate(
                field_id="authors",
                value="Ana Silva",
                normalized_value="ana silva",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                method="visible",
                confidence=0.99,
                sequence=1,
            ),
            BibliographicFieldCandidate(
                field_id="title",
                value="Correct title",
                normalized_value="correct title",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                method="visible",
                confidence=0.99,
            ),
            BibliographicFieldCandidate(
                field_id="periodical_title",
                value="Correct Journal",
                normalized_value="correct journal",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                method="visible",
                confidence=0.99,
            ),
            BibliographicFieldCandidate(
                field_id="place",
                value="Viçosa",
                normalized_value="vicosa",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                method="visible",
                confidence=0.99,
            ),
            BibliographicFieldCandidate(
                field_id="publication_year",
                value="2025",
                normalized_value="2025",
                source_format=SourceFormat.PDF,
                source_file="article.pdf",
                method="visible",
                confidence=0.99,
            ),
        ],
    )
    document = ProcessedDocument(
        source_path=Path("article.pdf"),
        sha256="abc",
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.PROCESSED,
        bibliographic_record=record,
    )

    compiled = ReferenceCompiler(ReferenceFormatter()).compile([document], date(2026, 7, 14))[0]

    assert (
        compiled.generated_reference == "SILVA, Ana. Correct title. Correct Journal, Viçosa, 2025."
    )
    assert compiled.resolved_bibliography is not None
    assert compiled.resolved_bibliography.value_for("title") == "Correct title"


def test_academic_formatter_does_not_repeat_course_already_inside_work_type() -> None:
    record = CanonicalBibliographicRecord(
        record_id="thesis",
        document_type_candidates=[
            DocumentTypeCandidate(
                schema_id="ufv.2",
                family="academic_work",
                medium="print",
                source_format=SourceFormat.PDF,
                source_file="thesis.pdf",
                confidence=0.99,
                reason="test",
            )
        ],
        field_candidates=[
            BibliographicFieldCandidate(
                field_id="authors",
                value="André Dantas de Medeiros",
                normalized_value="andre dantas de medeiros",
                source_format=SourceFormat.PDF,
                source_file="thesis.pdf",
                method="visible",
                confidence=0.99,
                sequence=1,
            ),
            BibliographicFieldCandidate(
                field_id="title",
                value="Aplicações avançadas",
                normalized_value="aplicacoes avancadas",
                source_format=SourceFormat.PDF,
                source_file="thesis.pdf",
                method="visible",
                confidence=0.99,
            ),
            BibliographicFieldCandidate(
                field_id="presentation_year",
                value="2023",
                normalized_value="2023",
                source_format=SourceFormat.PDF,
                source_file="thesis.pdf",
                method="visible",
                confidence=0.99,
            ),
            BibliographicFieldCandidate(
                field_id="work_type",
                value="Tese (Doutorado em Fitotecnia)",
                normalized_value="tese doutorado em fitotecnia",
                source_format=SourceFormat.PDF,
                source_file="thesis.pdf",
                method="visible",
                confidence=0.99,
            ),
            BibliographicFieldCandidate(
                field_id="degree_course",
                value="Fitotecnia",
                normalized_value="fitotecnia",
                source_format=SourceFormat.PDF,
                source_file="thesis.pdf",
                method="visible",
                confidence=0.99,
            ),
            BibliographicFieldCandidate(
                field_id="academic_affiliation",
                value="Universidade Federal de Viçosa",
                normalized_value="universidade federal de vicosa",
                source_format=SourceFormat.PDF,
                source_file="thesis.pdf",
                method="visible",
                confidence=0.99,
            ),
            BibliographicFieldCandidate(
                field_id="academic_place",
                value="Viçosa, MG",
                normalized_value="vicosa mg",
                source_format=SourceFormat.PDF,
                source_file="thesis.pdf",
                method="visible",
                confidence=0.99,
            ),
            BibliographicFieldCandidate(
                field_id="defense_year",
                value="2023",
                normalized_value="2023",
                source_format=SourceFormat.PDF,
                source_file="thesis.pdf",
                method="visible",
                confidence=0.99,
            ),
        ],
    )
    metadata = ArticleMetadata(
        title=ev("legacy"),
        authors=[],
        authors_evidence=ev(None),
        journal=ev(None),
        place=ev(None),
        year=ev(None),
        publication_month=ev(None),
        volume=ev(None),
        issue=ev(None),
        pages=ev(None),
        article_number=ev(None),
        doi=ev(None),
        url=ev(None),
        extractor="test",
        document_type=DocumentType.THESIS,
    )
    document = ProcessedDocument(
        source_path=Path("thesis.pdf"),
        sha256="thesis",
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.PROCESSED,
        bibliographic_record=record,
    )

    compiled = ReferenceCompiler(ReferenceFormatter()).compile([document], date(2026, 7, 14))[0]

    assert "Tese (Doutorado em Fitotecnia) (Fitotecnia)" not in compiled.generated_reference
    assert (
        "Tese (Doutorado em Fitotecnia) – Universidade Federal de Viçosa"
        in compiled.generated_reference
    )

from datetime import date
from pathlib import Path

from refengine.domain.bibliography import (
    ResolutionStatus,
    ResolvedBibliographicField,
    ResolvedBibliographicRecord,
)
from refengine.domain.enums import DocumentType
from refengine.domain.models import ArticleMetadata, Author, Evidence
from refengine.services.bibliographic_record import record_from_metadata
from refengine.services.candidate_resolver import CandidateResolver
from refengine.services.metadata_extractor import MetadataExtractor
from refengine.services.reference_formatter import ReferenceFormatter


def evidence(value: str | None, confidence: float = 0.9, method: str = "visible") -> Evidence:
    return Evidence(value=value, confidence=confidence if value else 0.0, method=method)


def academic_metadata() -> ArticleMetadata:
    return ArticleMetadata(
        title=evidence("Exemplo de trabalho acadêmico", 0.98, "academic_catalog_record"),
        authors=[
            Author(
                full_name="Júlia Martins Soares", family_name="Soares", given_names="Júlia Martins"
            )
        ],
        authors_evidence=evidence("JÚLIA MARTINS SOARES", 0.98, "academic_cover"),
        journal=evidence(None),
        place=evidence("Viçosa, MG", 0.92, "academic_front_matter"),
        year=evidence("2023", 0.97, "publisher_header"),
        publication_month=evidence(None),
        volume=evidence(None),
        issue=evidence(None),
        pages=evidence(None),
        article_number=evidence(None),
        doi=evidence("10.47328/ufvbbt.2023.336", 0.99, "doi_regex"),
        url=evidence("https://doi.org/10.47328/ufvbbt.2023.336", 0.92, "publisher_url_pattern"),
        extractor="generic",
        document_type=DocumentType.DISSERTATION,
        institution=evidence("Universidade Federal de Viçosa", 0.9, "academic_front_matter"),
        degree=evidence("Dissertação (Mestrado em Fitotecnia)", 0.9, "academic_front_matter"),
        total_pages=evidence("55", 0.85, "physical_description"),
        department=evidence("Departamento de Agronomia", 0.9, "academic_front_matter"),
    )


def selected(field_id: str, value: str) -> ResolvedBibliographicField:
    return ResolvedBibliographicField(
        field_id=field_id,
        values=[value],
        status=ResolutionStatus.SELECTED,
        confidence=1.0,
        reason="test",
    )


def test_ocr_academic_front_matter_recovers_ufv_fields_without_filename_rules() -> None:
    text = """
    JULIA MARTINS SOARES
    ESPECTROSCOPIA NO INFRAVERMELHO PROXIMO E METODOS QUIMIOMETRICOS
    Dissertacao apresentada a Universidade Federal de Vigosa, como parte das
    exigencias do Programa de Pos-Graduagao em Fitotecnia.
    VICOSA - MINAS GERAIS
    2023
    Ficha catalografica elaborada pela Biblioteca Central da Universidade Federal de Vicosa
    Soares, Julia Martins, 1998-
    S676e Espectroscopia no infravermelho proximo e métodos quimiométricos para classificacao
    de sementes / Julia Martins Soares. — Vigosa, MG, 2023.
    1 dissertagao eletrônica (55 f.).
    Departamento de Agronomia.
    """

    fields = MetadataExtractor()._academic_fields(text, DocumentType.DISSERTATION, 56)

    assert fields["institution"] == "Universidade Federal de Viçosa"
    assert fields["department"] == "Departamento de Agronomia"
    assert fields["place"] == "Viçosa, MG"
    assert fields["total_pages"] == "55"


def test_academic_catalog_title_is_generic_and_preserves_source_case() -> None:
    text = """
    Ficha catalográfica elaborada pela Biblioteca Central
    Rocha, Sérgio Barbosa Ferreira, 1990-
    R672c Caracterização de variedades de Cannabis sativa L. cultivadas no Brasil
    para uso medicinal e industrial / Sérgio Barbosa Ferreira Rocha. – Viçosa, MG, 2022.
    1 dissertação eletrônica (91 f.).
    """
    extractor = MetadataExtractor()

    record = extractor._academic_catalog_record(text)
    title = extractor._title(None, [], text, DocumentType.DISSERTATION, {})

    assert record["title"] == (
        "Caracterização de variedades de Cannabis sativa L. cultivadas no Brasil "
        "para uso medicinal e industrial"
    )
    assert title.value == record["title"]
    assert "Brasil" in title.value


def test_academic_record_combines_affiliation_and_derives_degree_course() -> None:
    record = record_from_metadata(academic_metadata(), Path("source.pdf"))
    resolved = CandidateResolver().resolve(record, access_date=date(2026, 7, 14))

    assert resolved.value_for("academic_affiliation") == (
        "Departamento de Agronomia, Universidade Federal de Viçosa"
    )
    assert resolved.value_for("degree_course") == "Mestrado em Fitotecnia"
    assert resolved.value_for("access_date") == "2026-07-14"
    assert not resolved.missing_required_fields


def test_academic_formatter_keeps_online_identifiers_from_the_source() -> None:
    record = ResolvedBibliographicRecord(
        record_id="academic",
        schema_id="ufv.2",
        family="academic_work",
        medium="print",
        fields={
            "authors": selected("authors", "Júlia Martins Soares"),
            "title": selected("title", "Espectroscopia no infravermelho próximo"),
            "presentation_year": selected("presentation_year", "2023"),
            "pagination": selected("pagination", "55"),
            "work_type": selected("work_type", "Dissertação (Mestrado em Fitotecnia)"),
            "degree_course": selected("degree_course", "Mestrado em Fitotecnia"),
            "academic_affiliation": selected(
                "academic_affiliation",
                "Departamento de Agronomia, Universidade Federal de Viçosa",
            ),
            "academic_place": selected("academic_place", "Viçosa, MG"),
            "defense_year": selected("defense_year", "2023"),
            "doi": selected("doi", "10.47328/ufvbbt.2023.336"),
            "url": selected("url", "https://doi.org/10.47328/ufvbbt.2023.336"),
            "access_date": selected("access_date", "2026-07-14"),
        },
        ready_for_formatting=True,
    )

    formatted = ReferenceFormatter().format_resolved(record, date(2026, 7, 14))

    assert formatted is not None
    assert "Departamento de Agronomia, Universidade Federal de Viçosa" in formatted
    assert "DOI: https://doi.org/10.47328/ufvbbt.2023.336" in formatted
    assert "Disponível em: https://doi.org/10.47328/ufvbbt.2023.336" not in formatted
    assert "Acesso em: 14 jul. 2026" not in formatted


def test_monograph_catalog_record_is_extracted_without_document_specific_constants() -> None:
    text = """
    Catalogação na Fonte
    Biblioteca Nacional de Agricultura – BINAGRI
    Brasil. Ministério da Agricultura, Pecuária e Abastecimento.
    Regras para análise de sementes / Ministério da Agricultura,
    Pecuária e Abastecimento. Secretaria de Defesa Agropecuária. –
    Brasília : Mapa/ACS, 2009.
    399 p.
    ISBN 978-85-99851-70-8
    """

    result = MetadataExtractor()._monograph_catalog_record(text)

    assert result == {
        "title": "Regras para análise de sementes",
        "corporate_author": "BRASIL. Ministério da Agricultura, Pecuária e Abastecimento",
        "place": "Brasília",
        "publisher": "Mapa/ACS",
        "year": "2009",
        "total_pages": "399",
    }


def test_book_extent_maps_to_physical_description_not_academic_pagination() -> None:
    metadata = academic_metadata().model_copy(
        update={
            "document_type": DocumentType.BOOK_MANUAL,
            "institution": evidence(None),
            "degree": evidence(None),
            "department": evidence(None),
            "program": evidence(None),
            "total_pages": evidence("399", 0.95, "catalog_record"),
            "corporate_author": evidence(
                "Brasil. Ministério da Agricultura, Pecuária e Abastecimento",
                0.95,
                "catalog_record",
            ),
        }
    )

    record = record_from_metadata(metadata, Path("manual.pdf"))

    assert [item.value for item in record.candidates_for("physical_description")] == ["399 p."]
    assert not record.candidates_for("pagination")


def test_classifier_recognizes_generic_corporate_monograph_catalog_record() -> None:
    from refengine.domain.enums import DocumentType, ExtractionMethod
    from refengine.domain.models import PageText
    from refengine.services.document_classifier import classify_document_type

    pages = [
        PageText(
            page_number=1,
            text=(
                "Catalogação na Fonte Biblioteca Nacional. "
                "Brasil. Ministério da Agricultura. Manual técnico / Ministério da Agricultura. "
                "Brasília: Editora Pública, 2009. 399 p. ISBN 978-85-00000-00-0."
            ),
            method=ExtractionMethod.NATIVE,
            character_count=180,
        )
    ]

    assert classify_document_type(pages) is DocumentType.BOOK_MANUAL

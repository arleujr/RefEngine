from datetime import date

import pytest

from refengine.domain.bibliography import (
    ResolutionStatus,
    ResolvedBibliographicField,
    ResolvedBibliographicRecord,
)
from refengine.rules.catalog import load_ufv_2025_catalog
from refengine.services.reference_formatter import ReferenceFormatter

VALUES = {
    "authors": ["Ana Maria Silva", "Bruno Costa"],
    "corporate_author": ["UNIVERSIDADE FEDERAL DE VIÇOSA"],
    "jurisdiction": ["BRASIL"],
    "entity_heading": ["MINISTÉRIO DA AGRICULTURA"],
    "event_name": ["CONGRESSO BRASILEIRO DE SEMENTES"],
    "event_number": ["5"],
    "event_year": ["2024"],
    "event_place": ["Viçosa, MG"],
    "title": ["Título principal"],
    "subtitle": ["subtítulo"],
    "edition": ["2. ed."],
    "version": ["Versão 2.0"],
    "other_responsibility": ["Tradução de Carla Souza"],
    "place": ["Viçosa, MG"],
    "publisher": ["Editora UFV"],
    "publication_year": ["2024"],
    "publication_date": ["jul. 2024"],
    "start_year": ["2020"],
    "end_year": ["2024"],
    "physical_description": ["120 p."],
    "illustrations": ["il. color."],
    "dimensions": ["30 cm"],
    "series": ["Coleção Pesquisa, 2"],
    "notes": ["Inclui bibliografia"],
    "isbn": ["978-85-0000-000-0"],
    "issn": ["1234-5678"],
    "doi": ["10.0000/exemplo"],
    "url": ["https://example.invalid/documento"],
    "access_date": ["2026-07-14"],
    "access_time": ["14:30"],
    "support": ["E-book"],
    "advisor": ["João Pereira"],
    "presentation_year": ["2024"],
    "pagination": ["120 f."],
    "work_type": ["Dissertação"],
    "degree_course": ["Mestrado em Fitotecnia"],
    "academic_affiliation": ["Universidade Federal de Viçosa"],
    "academic_place": ["Viçosa, MG"],
    "defense_year": ["2024"],
    "part_title": ["Capítulo experimental"],
    "part_subtitle": ["resultados"],
    "host_authors": ["Carlos Lima"],
    "host_title": ["Livro de sementes"],
    "host_subtitle": ["fundamentos"],
    "host_edition": ["2. ed."],
    "volume": ["10"],
    "chapter": ["3"],
    "part_pages": ["15-24"],
    "recipient": ["Maria Souza"],
    "correspondence_date": ["6 jun. 2024"],
    "correspondence_description": ["1 carta"],
    "event_document_title": ["Anais [...]"],
    "event_pagination": ["300 p."],
    "event_notes": ["Tema: Qualidade de sementes"],
    "periodical_title": ["Revista de Sementes"],
    "periodical_subtitle": ["ciência e tecnologia"],
    "year_designation": ["12"],
    "issue": ["2"],
    "fascicle": ["1"],
    "article_pages": ["10-20"],
    "article_number": ["e123"],
    "publication_month": ["jul."],
    "publication_period": ["jul./ago."],
    "supplement_designation": ["Suplemento 1"],
    "consulted_period": ["2022-2024"],
    "newspaper_title": ["Jornal da Ciência"],
    "newspaper_subtitle": ["edição nacional"],
    "newspaper_date": ["14 jul. 2024"],
    "newspaper_section": ["Ciência, Caderno 2"],
    "newspaper_pages": ["B1-B2"],
    "patent_depositor": ["Universidade Federal de Viçosa"],
    "patent_holder": ["Universidade Federal de Viçosa"],
    "patent_attorney": ["Maria Costa"],
    "patent_number": ["BR 102024000001"],
    "deposit_date": ["1 jan. 2024"],
    "grant_date": ["1 jun. 2025"],
    "patent_classification": ["Int. Cl. A01C 1/00"],
    "legal_document_name": ["Lei"],
    "legal_document_number": ["12.345"],
    "legal_document_date": ["1 jan. 2024"],
    "ementa": ["Dispõe sobre a matéria"],
    "publication_source": ["Diário Oficial da União, Brasília, DF, 2 jan. 2024"],
    "court": ["Supremo Tribunal Federal"],
    "court_division": ["2. Turma"],
    "legal_document_type": ["Recurso Extraordinário"],
    "process_number": ["123456/SP"],
    "judicial_unit": ["São Paulo"],
    "relator": ["Min. Ana Silva"],
    "judgment_date": ["1 fev. 2024"],
    "administrative_act_type": ["Portaria"],
    "administrative_act_number": ["100"],
    "signature_date": ["1 mar. 2024"],
    "registry_office": ["Cartório de Registro Civil"],
    "registry_document_type": ["Certidão de nascimento de Ana Silva"],
    "registry_date": ["9 ago. 1979"],
    "director": ["Walter Silva"],
    "producer": ["Maria Costa"],
    "audiovisual_responsibilities": ["Roteiro: João Lima"],
    "media_support": ["1 DVD (120 min), son., color."],
    "sound_responsibility": ["Compositor e intérprete: João Silva"],
    "composer": ["Ludwig van Beethoven"],
    "performer": ["Simone"],
    "narrator": ["Pedro Bial"],
    "recording_label": ["Biscoito Fino"],
    "track": ["faixa 7"],
    "instrument": ["Piano"],
    "iconographic_support": ["1 fotografia, color."],
    "scale": ["1:50.000"],
    "map_description": ["1 mapa, color."],
    "creator": ["Marcel Duchamp"],
    "manufacturer": ["Museu Experimental"],
    "electronic_description": ["Programa de computador"],
    "service_title": ["Sistema de análise de sementes"],
    "software_version": ["Versão 1.0"],
}


def selected(field_id: str, values: list[str]) -> ResolvedBibliographicField:
    return ResolvedBibliographicField(
        field_id=field_id,
        values=values,
        status=ResolutionStatus.SELECTED,
        confidence=1.0,
        reason="synthetic catalog fixture",
    )


SCHEMAS = load_ufv_2025_catalog().schemas


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda schema: schema.id)
def test_every_catalog_schema_has_a_working_formatter(schema) -> None:
    fields = {
        field_id: selected(field_id, VALUES[field_id])
        for field_id in schema.ordered_fields
        if field_id in VALUES
    }
    record = ResolvedBibliographicRecord(
        record_id=schema.id,
        schema_id=schema.id,
        family=schema.family,
        medium=schema.medium,
        fields=fields,
        ready_for_formatting=True,
    )

    result = ReferenceFormatter().format_resolved(record, date(2026, 7, 14))

    assert result is not None
    assert result.endswith(".")
    assert "  " not in result


def test_part_of_monograph_follows_in_structure() -> None:
    schema = next(item for item in SCHEMAS if item.id == "ufv.4")
    fields = {
        field_id: selected(field_id, VALUES[field_id])
        for field_id in schema.ordered_fields
        if field_id in VALUES
    }
    result = ReferenceFormatter().format_resolved(
        ResolvedBibliographicRecord(
            record_id="part",
            schema_id=schema.id,
            family=schema.family,
            medium=schema.medium,
            fields=fields,
            ready_for_formatting=True,
        ),
        date(2026, 7, 14),
    )
    assert result is not None
    assert (
        "Capítulo experimental: resultados. In: LIMA, Carlos. Livro de sementes: fundamentos."
        in result
    )
    assert "p. 15-24." in result


def test_electronic_score_can_omit_unknown_publisher_without_fake_block() -> None:
    fields = {
        "composer": selected("composer", ["Chiquinha Gonzaga"]),
        "title": selected("title", ["Gaúcho"]),
        "instrument": selected("instrument", ["Piano"]),
        "publication_year": selected("publication_year", ["1997"]),
        "physical_description": selected("physical_description", ["1 partitura"]),
        "url": selected("url", ["https://example.invalid/gaucho.pdf"]),
        "access_date": selected("access_date", ["2026-07-14"]),
    }
    record = ResolvedBibliographicRecord(
        record_id="score",
        schema_id="ufv.28",
        family="score",
        medium="electronic",
        fields=fields,
        ready_for_formatting=True,
    )
    result = ReferenceFormatter().format_resolved(record, date(2026, 7, 14))
    assert result is not None
    assert "[S. l.]: [s. n.]" not in result
    assert "Piano. 1997. 1 partitura." in result

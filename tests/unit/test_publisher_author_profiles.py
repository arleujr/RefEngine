from refengine.domain.enums import DocumentType
from refengine.services.metadata_extractor import MetadataExtractor


def test_mdpi_prefers_complete_standard_author_metadata() -> None:
    extractor = MetadataExtractor()
    evidence = extractor._authors_block(
        title="Machine Learning for Seed Quality Classification",
        blocks=[],
        internal_author=(
            "André Dantas de Medeiros, Laércio Junio da Silva, "
            "João Paulo Oliveira Ribeiro, Kamylla Calzolari Ferreira, "
            "Jorge Tadeu Fim Rosas, Abraão Almeida Santos and "
            "Clíssia Barboza da Silva"
        ),
        searchable_text="Machine Learning 1 Agronomy Department",
        bibliographic={"extractor": "mdpi"},
        document_type=DocumentType.JOURNAL_ARTICLE,
    )
    assert evidence.method == "publisher_pdf_metadata"
    assert evidence.value.endswith("Clíssia Barboza da Silva")
    assert "Agronomy Department" not in evidence.value


def test_legacy_periodical_stops_before_affiliation() -> None:
    extractor = MetadataExtractor()
    result = extractor._profile_authors(
        "Effect of seed coat color on seed dormancy in different environments "
        "Atsushi Torada1 & Yoichi Amano2 1Hokkaido Green-Bio Institute "
        "Received 24 June 2001",
        "Effect of seed coat color on seed dormancy in different environments",
        "legacy_periodical",
    )
    assert result == "Atsushi Torada1 & Yoichi Amano2"


def test_scientific_name_does_not_block_uppercase_normalization() -> None:
    assert MetadataExtractor._looks_mostly_uppercase(
        "CARACTERIZAÇÃO DE VARIEDADES DE Cannabis sativa L. CULTIVADAS NO BRASIL"
    )

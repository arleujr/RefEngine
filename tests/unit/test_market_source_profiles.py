from refengine.services.author_parser import parse_authors
from refengine.services.metadata_extractor import MetadataExtractor


def test_parses_middle_dot_authors_and_compound_surname() -> None:
    authors = parse_authors("Grégorio Crini1 · Eric Lichtfouse2 · Agata Lo Giudice3")

    assert [author.full_name for author in authors] == [
        "Grégorio Crini",
        "Eric Lichtfouse",
        "Agata Lo Giudice",
    ]
    assert authors[-1].family_name == "Lo Giudice"


def test_normalizes_portuguese_particles_from_uppercase_author() -> None:
    authors = parse_authors("ANDRÉ DANTAS DE MEDEIROS; MARTHA FREIRE DA SILVA")

    assert [author.full_name for author in authors] == [
        "André Dantas de Medeiros",
        "Martha Freire da Silva",
    ]


def test_global_sustainability_profile_uses_layout_lines() -> None:
    extractor = MetadataExtractor()
    text = """
    Global Sustainability Research
    REVIEW ARTICLE
    A review of the industrial use and global sustainability of Cannabis sativa
    Asif Raihan1*, Tashdid Rahman Bijoy2
    1Institute of Climate Change
    """

    title = extractor._profile_title(
        text,
        None,
        "global_sustainability_research",
        [],
    )
    authors = extractor._profile_authors(
        text,
        title,
        "global_sustainability_research",
    )

    assert title == ("A review of the industrial use and global sustainability of Cannabis sativa")
    assert authors == "Asif Raihan1*, Tashdid Rahman Bijoy2"


def test_ufv_catalog_record_is_comparison_free_parser() -> None:
    extractor = MetadataExtractor()
    text = """
    Ficha catalográfica elaborada pela Biblioteca Central
    Aplicações avançadas de aprendizado de máquina e ferramentas de análise
    de imagens para classificação e fenotipagem de sementes /
    André Dantas de Medeiros. – Viçosa, MG, 2023.
    1 tese eletrônica (77 f.): il.
    """

    record = extractor._academic_catalog_record(text)

    assert record["author"] == "André Dantas de Medeiros"
    assert record["total_pages"] == "77"
    assert record["title"].endswith("fenotipagem de sementes")

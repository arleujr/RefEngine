from refengine.services.web_print_metadata import extract_web_print_metadata


def test_springer_nature_print_extracts_visible_article_fields() -> None:
    text = """
    SPRINGER NATURE Link Login
    Medical cannabinoids: a pharmacology-based
    systematic review and meta-analysis for all
    relevant medical indications
    Review Open access Published: 19 August 2022
    Volume 20, article number 259 (2022) Cite this article
    BMC Medicine
    >
    Ainhoa Bilbao & Rainer Spanagel
    Abstract
    """

    metadata = extract_web_print_metadata(text)

    assert metadata is not None
    assert metadata.profile == "springer_nature_web_print"
    assert metadata.title == (
        "Medical cannabinoids: a pharmacology-based systematic review "
        "and meta-analysis for all relevant medical indications"
    )
    assert metadata.authors == "Ainhoa Bilbao; Rainer Spanagel"
    assert metadata.journal == "BMC Medicine"
    assert metadata.year == "2022"
    assert metadata.volume == "20"
    assert metadata.article_number == "259"


def test_locus_print_uses_visible_citation_and_uri() -> None:
    text = """
    LOCUS Navegar Estatísticas
    Aplicações avançadas de aprendizado de máquina e ferra-
    mentas de análise de imagem para classificação e fenoti-
    pagem de sementes
    Arquivos
    Data
    2023-10-17
    Autores
    Medeiros, André Dantas de
    Editor
    Universidade Federal de Viçosa
    Resumo
    texto do resumo
    Citação
    MEDEIROS, André Dantas de. Aplicações avançadas de aprendizado de máquina e ferramentas de análise de
    imagem para classificação e fenotipagem de sementes. 2023. 77 f. Tese (Doutorado em Fitotecnia) - Universi-
    dade Federal de Viçosa, Viçosa. 2023.
    URI
    https://locus.ufv.br//handle/123456789/32161
    Coleções
    Fitotecnia
    """

    metadata = extract_web_print_metadata(text)

    assert metadata is not None
    assert metadata.profile == "locus_repository_web_print"
    assert metadata.authors == "André Dantas de Medeiros"
    assert metadata.year == "2023"
    assert metadata.total_pages == "77"
    assert metadata.degree == "Tese (Doutorado em Fitotecnia)"
    assert metadata.institution == "Universidade Federal de Viçosa"
    assert metadata.place == "Viçosa, MG"
    assert metadata.source_url == "https://locus.ufv.br/handle/123456789/32161"


def test_sciencedirect_print_cleans_author_footnote_symbols() -> None:
    text = """
    ScienceDirect
    Renewable and Sustainable Energy Reviews
    Volume 51, November 2015, Pages 29-42
    Energy and environmental assessment of
    industrial hemp for building applications: A
    review
    Carlo Ingrao “* 2 &, Agata Lo Giudice ?, Jacopo Bacenetti ‘, Caterina Tricase º, Giovanni Dotelli 4, Marco
    Fiala ©, Valentina Siracusa º, Charles Mbohwa ©
    Show more
    https://doi.org/10.1016/j.rser.2015.06.002
    Abstract
    """

    metadata = extract_web_print_metadata(text)

    assert metadata is not None
    assert metadata.profile == "sciencedirect_web_print"
    assert metadata.title == (
        "Energy and environmental assessment of industrial hemp for building applications: a review"
    )
    assert metadata.authors == (
        "Carlo Ingrao; Agata Lo Giudice; Jacopo Bacenetti; "
        "Caterina Tricase; Giovanni Dotelli; Marco Fiala; "
        "Valentina Siracusa; Charles Mbohwa"
    )
    assert metadata.journal == "Renewable and Sustainable Energy Reviews"
    assert metadata.volume == "51"
    assert metadata.pages == "29-42"
    assert metadata.source_url == "https://doi.org/10.1016/j.rser.2015.06.002"


def test_scielo_collapsed_authors_are_not_invented() -> None:
    text = """
    Brasil pt_BR
    Scientia Agricola
    Sumario
    REVIEW Sci. agric. (Piracicaba, Braz.) 72 (4) Jul-Aug 2015
    https://doi.org/10.1590/0103-9016-2015-0007
    à Seed vigor testing: an
    overview of the past, present
    and future perspective
    Authorship SCIMAGO INSTITUTIONS RANKINGS
    Abstract
    """

    metadata = extract_web_print_metadata(text)

    assert metadata is not None
    assert metadata.profile == "scielo_web_print"
    assert metadata.title == (
        "Seed vigor testing: an overview of the past, present and future perspective"
    )
    assert metadata.authors is None
    assert metadata.author_visibility == "collapsed_or_absent"
    assert metadata.journal == "Scientia Agricola"
    assert metadata.place == "Piracicaba"
    assert metadata.volume == "72"
    assert metadata.issue == "4"
    assert metadata.year == "2015"


def test_scielo_ocr_translation_marker_is_not_part_of_primary_title() -> None:
    text = """
    Acta Scientiarum. Agronomy
    Produção Vegetal Acta Sci., Agron. 31 (2) Jun 2009
    https://doi.org/10.1590/S1807-86212009000200018
    Qualidade fisiológica de sementes de cultivares e linhagens de soja no Estado de Minas Gerais ©
    Physiological quality of soybean seed cultivars and lineages in Minas Gerais State
    Autoria SCIMAGO INSTITUTIONS RANKINGS
    Resumo
    """

    metadata = extract_web_print_metadata(text)

    assert metadata is not None
    assert metadata.title == (
        "Qualidade fisiológica de sementes de cultivares e linhagens de soja "
        "no Estado de Minas Gerais"
    )

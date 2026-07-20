from refengine.domain.enums import DocumentType
from refengine.services.author_parser import parse_authors
from refengine.services.metadata_extractor import MetadataExtractor


def test_visible_author_spelling_is_not_silently_replaced() -> None:
    extractor = MetadataExtractor()
    title = (
        "Qualidade fisiológica de sementes de cultivares e linhagens de soja "
        "no Estado de Minas Gerais"
    )
    visible_line = (
        "Edmar Soares de Vasconcelos1*, Múcio Silva Reis2, Tuneo Sedyiama2 e Cosme Damião Cruz3"
    )
    blocks = [
        (0, 0, 100, 20, title, 0, 0),
        (0, 25, 100, 40, visible_line, 0, 0),
        (0, 45, 100, 70, "Departamento de Fitotecnia", 0, 0),
    ]

    evidence = extractor._authors_block(
        title=title,
        blocks=blocks,
        internal_author=None,
        searchable_text=f"{title}\n{visible_line}",
        bibliographic={"extractor": "scielo_scientia_agricola"},
        document_type=DocumentType.JOURNAL_ARTICLE,
    )

    assert evidence.method in {"text_after_title", "layout_block_after_title"}
    assert [author.full_name for author in parse_authors(evidence.value)] == [
        "Edmar Soares de Vasconcelos",
        "Múcio Silva Reis",
        "Tuneo Sedyiama",
        "Cosme Damião Cruz",
    ]

from pathlib import Path

from refengine.domain.enums import (
    DocumentType,
    ProcessingStatus,
    VariantType,
)
from refengine.domain.models import ArticleMetadata, Author, Evidence, ProcessedDocument
from refengine.services.variant_resolver import resolve_variants


def evidence(value: str | None) -> Evidence:
    return Evidence(
        value=value,
        confidence=0.95 if value else 0,
        method="test",
    )


def document(
    *,
    name: str,
    sha256: str,
    title: str,
    variant: VariantType,
) -> ProcessedDocument:
    metadata = ArticleMetadata(
        title=evidence(title),
        authors=[
            Author(
                full_name="André Dantas de Medeiros",
                family_name="Medeiros",
                given_names="André Dantas de",
            )
        ],
        authors_evidence=evidence("André Dantas de Medeiros"),
        journal=evidence(None),
        place=evidence("Viçosa, MG"),
        year=evidence("2023"),
        publication_month=evidence(None),
        volume=evidence(None),
        issue=evidence(None),
        pages=evidence(None),
        article_number=evidence(None),
        doi=evidence(None),
        url=evidence(None),
        extractor="test",
        document_type=DocumentType.THESIS,
        institution=evidence("Universidade Federal de Viçosa"),
        degree=evidence("Tese (Doutorado em Fitotecnia)"),
        total_pages=evidence("77"),
    )
    return ProcessedDocument(
        source_path=Path(name),
        sha256=sha256,
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.PROCESSED_WITH_WARNINGS,
        variant_type=variant,
        canonical_key=f"title:{title.casefold()}|year:2023",
    )


def test_secondary_ocr_variant_tolerates_minor_title_inflection() -> None:
    original = document(
        name="original.pdf",
        sha256="original",
        title=(
            "Aplicações avançadas de aprendizado de máquina e ferramentas "
            "de análise de imagens para classificação e fenotipagem de sementes"
        ),
        variant=VariantType.INSTITUTIONAL_REPOSITORY,
    )
    printed = document(
        name="printed.pdf",
        sha256="printed",
        title=(
            "Aplicações avançadas de aprendizado de máquina e ferramentas "
            "de análise de imagem para classificação e fenotipagem de sementes"
        ),
        variant=VariantType.BROWSER_PRINT,
    )

    resolved = resolve_variants([original, printed])

    selected = [item for item in resolved if item.include_in_output]
    secondary = [item for item in resolved if not item.include_in_output]
    assert len(selected) == 1
    assert selected[0].sha256 == "original"
    assert len(secondary) == 1
    assert secondary[0].canonical_key == selected[0].canonical_key


def test_two_originals_are_not_fuzzy_merged() -> None:
    first = document(
        name="first.pdf",
        sha256="first",
        title="Seed quality analysis by image processing",
        variant=VariantType.PUBLISHER_ORIGINAL,
    )
    second = document(
        name="second.pdf",
        sha256="second",
        title="Seed quality analyses by image processing",
        variant=VariantType.PUBLISHER_ORIGINAL,
    )

    resolved = resolve_variants([first, second])

    assert all(item.include_in_output for item in resolved)

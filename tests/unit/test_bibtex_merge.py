from pathlib import Path

from refengine.domain.enums import (
    DocumentType,
    ProcessingStatus,
    VariantType,
    WarningCode,
)
from refengine.domain.models import ArticleMetadata, Evidence, ProcessedDocument
from refengine.services.bibtex import parse_bibtex_file
from refengine.services.bibtex_merge import match_bibtex_entry, merge_bibtex_metadata


def evidence(value: str | None, method: str = "pdf") -> Evidence:
    return Evidence(value=value, confidence=0.95 if value else 0, method=method)


def pdf_document() -> ProcessedDocument:
    return ProcessedDocument(
        source_path=Path("article.pdf"),
        sha256="abc",
        pages=[],
        metadata=ArticleMetadata(
            title=evidence(
                "Energy and environmental assessment of industrial hemp for building applications: a review"
            ),
            authors=[],
            authors_evidence=evidence(None),
            journal=evidence("Renewable and Sustainable Energy Reviews"),
            place=evidence(None),
            year=evidence("2015"),
            publication_month=evidence(None),
            volume=evidence("51"),
            issue=evidence(None),
            pages=evidence("29-42"),
            article_number=evidence(None),
            doi=evidence("10.1016/j.rser.2015.06.002"),
            url=evidence(None),
            extractor="test",
            document_type=DocumentType.JOURNAL_ARTICLE,
        ),
        status=ProcessingStatus.PROCESSED,
        variant_type=VariantType.PUBLISHER_ORIGINAL,
    )


def test_doi_match_and_structured_merge(tmp_path: Path) -> None:
    bib = tmp_path / "article.bib"
    bib.write_text(
        """@article{x, title={Energy and environmental assessment of industrial hemp for building applications: A review}, author={Carlo Ingrao}, journal={Renewable and Sustainable Energy Reviews}, year={2015}, volume={51}, pages={29-42}, doi={10.1016/j.rser.2015.06.002}, url={https://example.test/article}}""",
        encoding="utf-8",
    )
    entry = parse_bibtex_file(bib)[0]
    document = pdf_document()

    match = match_bibtex_entry(document, [entry])
    assert match is not None
    assert match.method == "doi"

    merged = merge_bibtex_metadata(document, entry)
    assert merged.metadata.authors[0].full_name == "Carlo Ingrao"
    assert merged.metadata.url.value == "https://example.test/article"
    assert WarningCode.BIBTEX_METADATA_APPLIED in merged.warnings

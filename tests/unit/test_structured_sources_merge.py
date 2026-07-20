from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from refengine.application.ingest_folder import IngestFolder
from refengine.domain.bibliography import SourceFormat
from refengine.domain.enums import DocumentType, ExtractionMethod
from refengine.domain.models import ArticleMetadata, Evidence, PageText
from refengine.services.reference_formatter import ReferenceFormatter


def evidence(value: str | None) -> Evidence:
    return Evidence(value=value, confidence=0.95 if value else 0.0, method="test")


class Processor:
    def sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def process_pages(self, path: Path) -> list[PageText]:
        return [
            PageText(
                page_number=1,
                text="Article content available as native text.",
                method=ExtractionMethod.NATIVE,
                character_count=41,
            )
        ]


class Extractor:
    def extract(self, path: Path, pages: list[PageText]) -> ArticleMetadata:
        return ArticleMetadata(
            title=evidence("Energy and environmental assessment"),
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
            doi=evidence("10.1016/example"),
            url=evidence(None),
            extractor="test",
            document_type=DocumentType.JOURNAL_ARTICLE,
        )


class Repository:
    def save_many(self, documents: list[object]) -> None:
        self.documents = documents


def test_matching_pdf_bibtex_and_ris_become_one_work_with_all_sources(tmp_path: Path) -> None:
    (tmp_path / "article.pdf").write_bytes(b"pdf fixture")
    (tmp_path / "article.BIBTEX").write_text(
        """@article{sample,
  author = {Carlo Ingrao and Agata Lo Giudice},
  title = {Energy and environmental assessment},
  journal = {Renewable and Sustainable Energy Reviews},
  year = {2015},
  volume = {51},
  pages = {29-42},
  doi = {10.1016/example}
}
""",
        encoding="utf-8",
    )
    (tmp_path / "article.ris").write_text(
        """TY  - JOUR
ID  - sample-ris
AU  - Ingrao, Carlo
AU  - Lo Giudice, Agata
TI  - Energy and environmental assessment
JF  - Renewable and Sustainable Energy Reviews
PY  - 2015
VL  - 51
SP  - 29
EP  - 42
DO  - 10.1016/example
ER  -
""",
        encoding="utf-8",
    )

    documents = IngestFolder(
        processor=Processor(),  # type: ignore[arg-type]
        extractor=Extractor(),  # type: ignore[arg-type]
        formatter=ReferenceFormatter(),
        repository=Repository(),  # type: ignore[arg-type]
    ).execute(tmp_path, date(2026, 7, 15))

    assert len(documents) == 1
    record = documents[0].bibliographic_record
    assert record is not None
    assert set(record.source_files) == {"article.pdf", "article.BIBTEX", "article.ris"}
    assert {candidate.source_format for candidate in record.field_candidates} >= {
        SourceFormat.PDF,
        SourceFormat.BIBTEX,
        SourceFormat.RIS,
    }

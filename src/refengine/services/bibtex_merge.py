from __future__ import annotations

import difflib
from dataclasses import dataclass

from refengine.domain.enums import WarningCode
from refengine.domain.models import ArticleMetadata, Evidence, ProcessedDocument
from refengine.services.bibtex import (
    BibTeXEntry,
    metadata_from_bibtex,
    normalize_doi,
    normalized_title,
)


@dataclass(frozen=True)
class BibTeXMatch:
    entry: BibTeXEntry
    score: float
    method: str


def match_bibtex_entry(
    document: ProcessedDocument,
    entries: list[BibTeXEntry],
) -> BibTeXMatch | None:
    document_doi = normalize_doi(document.metadata.doi.value)
    if document_doi:
        for entry in entries:
            if entry.doi and entry.doi.casefold() == document_doi.casefold():
                return BibTeXMatch(entry=entry, score=1.0, method="doi")

    title = normalized_title(document.metadata.title.value)
    if not title:
        return None
    best: BibTeXMatch | None = None
    for entry in entries:
        candidate = normalized_title(entry.title)
        if not candidate:
            continue
        if (
            document.metadata.year.value
            and entry.year
            and document.metadata.year.value != entry.year
        ):
            continue
        score = difflib.SequenceMatcher(None, title, candidate).ratio()
        if score < 0.92:
            continue
        if best is None or score > best.score:
            best = BibTeXMatch(entry=entry, score=score, method="title")
    return best


def merge_bibtex_metadata(
    document: ProcessedDocument,
    entry: BibTeXEntry,
) -> ProcessedDocument:
    """Merge one explicit BibTeX record into a PDF-derived document.

    Structured citation metadata is preferred for bibliographic fields, while
    every conflicting replacement is surfaced as a review warning. The source
    PDF remains attached to the document for evidence and OCR diagnostics.
    """
    merged = document.model_copy(deep=True)
    structured = metadata_from_bibtex(entry)
    conflicts = False

    if structured.authors:
        old = _author_text(merged.metadata)
        new = _author_text(structured)
        conflicts = conflicts or _meaningful_conflict(old, new)
        merged.metadata.authors = structured.authors
        merged.metadata.authors_evidence = structured.authors_evidence

    for field_name in (
        "title",
        "journal",
        "place",
        "year",
        "publication_month",
        "volume",
        "issue",
        "pages",
        "article_number",
        "doi",
        "url",
        "institution",
        "degree",
        "program",
        "publisher",
        "total_pages",
        "corporate_author",
        "department",
    ):
        incoming: Evidence = getattr(structured, field_name)
        if not incoming.value:
            continue
        current: Evidence = getattr(merged.metadata, field_name)
        if field_name in {
            "title",
            "journal",
            "year",
            "volume",
            "issue",
            "pages",
            "article_number",
            "doi",
        }:
            conflicts = conflicts or _meaningful_conflict(current.value, incoming.value)
        setattr(merged.metadata, field_name, incoming)

    if structured.document_type.value != "unknown":
        if (
            merged.metadata.document_type.value != "unknown"
            and merged.metadata.document_type != structured.document_type
        ):
            conflicts = True
        merged.metadata.document_type = structured.document_type

    merged.metadata.extractor = f"{merged.metadata.extractor}+bibtex"
    merged.warnings = list(
        dict.fromkeys(
            [
                *merged.warnings,
                WarningCode.BIBTEX_METADATA_APPLIED,
                *([WarningCode.BIBTEX_CONFLICT_REVIEW] if conflicts else []),
            ]
        )
    )
    return merged


def _author_text(metadata: ArticleMetadata) -> str | None:
    if metadata.authors:
        return "; ".join(author.full_name for author in metadata.authors)
    return metadata.authors_evidence.value


def _meaningful_conflict(first: str | None, second: str | None) -> bool:
    if not first or not second:
        return False
    return _normalize(first) != _normalize(second)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("–", "-").replace("—", "-").split())

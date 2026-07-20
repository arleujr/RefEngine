from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import fitz

from refengine.domain.enums import DocumentType, ExtractionMethod, VariantType
from refengine.domain.models import ArticleMetadata, PageText
from refengine.services.generic_pdf import article_signals


def _front_text(pages: list[PageText], limit: int = 6) -> str:
    non_empty = [page.text for page in pages if page.text][:limit]
    return " ".join(non_empty).casefold()


def classify_document_type(pages: list[PageText]) -> DocumentType:
    """Classify using front matter while ignoring citations later in the work."""
    front = _front_text(pages)
    normalized_front = normalize(front)

    dissertation_word = re.search(r"\bdisserta(?:cao|gao|cdo)\b", normalized_front)
    dissertation_context = any(
        marker in normalized_front
        for marker in ("mestrado", "apresentada", "submetida", "programa de pos graduacao")
    )
    if dissertation_word and dissertation_context:
        return DocumentType.DISSERTATION

    thesis_word = re.search(r"\btese\b", normalized_front)
    thesis_context = any(
        marker in normalized_front
        for marker in ("doutorado", "apresentada", "submetida", "programa de pos graduacao")
    )
    if thesis_word and thesis_context:
        return DocumentType.THESIS

    journal_markers = (
        "scientific reports",
        "plant methods",
        "sensors & actuators",
        "ieee access",
        "euphytica",
        "bmc medicine",
        "environmental chemistry letters",
        "renewable and sustainable energy reviews",
        "scientia agricola",
        "acta scientiarum",
        "global sustainability research",
    )
    if any(marker in front for marker in journal_markers):
        return DocumentType.JOURNAL_ARTICLE
    if "digital object identifier 10." in front and "date of publication" in front:
        return DocumentType.JOURNAL_ARTICLE
    if (
        re.search(r"\bsensors\s+20\d{2},\s*\d+,\s*\d+", front)
        and "mdpi.com/journal/sensors" in front
    ):
        return DocumentType.JOURNAL_ARTICLE
    if re.search(r"\bdoi\s*:\s*10\.", front) and re.search(r"\bv\.?\s*\d+", front):
        return DocumentType.JOURNAL_ARTICLE

    catalog_record = (
        "catalogação na fonte" in front
        or "catalogacao na fonte" in normalized_front
        or "ficha catalográfica" in front
        or "ficha catalografica" in normalized_front
    )
    monograph_publication = bool(re.search(r"\bisbn\s+[0-9x-]+", normalized_front)) and bool(
        re.search(r"\b(?:1|2|3|4|5|6|7|8|9|10)[ªa]?\s+edicao\b", normalized_front)
    )
    corporate_publication = (
        catalog_record
        and bool(
            re.search(
                r"\b(?:ministerio|universidade|instituto|fundacao|organizacao)\b", normalized_front
            )
        )
        and bool(re.search(r"\b(?:19|20)\d{2}\b", normalized_front))
    )
    if monograph_publication or corporate_publication:
        return DocumentType.BOOK_MANUAL

    if "notícias agrícolas" in front or ("publicado em" in front and "gov.br" in front):
        return DocumentType.WEB_ARTICLE

    # Generic fallback: require several independent, visible article signals.
    # This is intentionally publication-independent and avoids classifying a PDF
    # as an article from a DOI alone, because books, chapters and proceedings may
    # also receive DOI identifiers.
    if article_signals(pages).looks_like_periodical_article:
        return DocumentType.JOURNAL_ARTICLE
    return DocumentType.UNKNOWN


def classify_variant(pdf_path: Path, pages: list[PageText]) -> VariantType:
    try:
        with fitz.open(pdf_path) as document:
            metadata = document.metadata
    except Exception:
        metadata = {}
    producer = (metadata.get("producer") or "").casefold()
    creator = (metadata.get("creator") or "").casefold()
    title = (metadata.get("title") or "").casefold()
    if "microsoft" in producer and "print" in producer:
        return VariantType.BROWSER_PRINT
    if "chrome" in creator or title.startswith("brasil -"):
        return VariantType.BROWSER_PRINT
    native = sum(page.method is ExtractionMethod.NATIVE for page in pages)
    ocr = sum(page.method is ExtractionMethod.OCR for page in pages)
    if native == 0 and ocr > 0:
        return VariantType.SCANNED
    text = _front_text(pages, 3)
    document_type = classify_document_type(pages)
    if (
        document_type in {DocumentType.THESIS, DocumentType.DISSERTATION}
        and "universidade federal de viçosa" in text
    ):
        return VariantType.INSTITUTIONAL_REPOSITORY
    return VariantType.PUBLISHER_ORIGINAL


def canonical_key(metadata: ArticleMetadata, source_name: str = "") -> str:
    """Build a duplicate key, preferring DOI and then normalized title/year."""
    title = normalize(metadata.title.value or "")
    year = normalize(metadata.year.value or "")
    if title:
        return f"title:{title}|year:{year}"
    doi = normalize_doi(metadata.doi.value)
    if doi:
        return f"doi:{doi}"
    stem = normalize(Path(source_name).stem)
    stem = re.sub(
        r"\b(pdf|original|impresso|imprimido|site|gratuito|texto completo)\b",
        " ",
        stem,
    )
    stem = re.sub(r"\s+", " ", stem).strip()
    return f"file:{stem}" if stem else "unknown"


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).strip()


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.IGNORECASE)
    return cleaned.rstrip(".,;").casefold()

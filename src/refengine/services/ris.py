from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from refengine.domain.enums import DocumentType, VariantType
from refengine.domain.models import ArticleMetadata, Author, Evidence, ProcessedDocument
from refengine.services.author_parser import parse_authors
from refengine.services.bibtex import normalize_doi, normalized_title
from refengine.services.validation import apply_warning_status, classify_metadata, collect_warnings

_SPACE = re.compile(r"\s+")
_TAG_LINE = re.compile(r"^\s*([A-Z0-9]{2})\s*-\s?(.*)$")


@dataclass(frozen=True)
class RisEntry:
    entry_type: str
    key: str
    fields: dict[str, list[str]]
    source_path: Path

    @property
    def doi(self) -> str | None:
        return normalize_doi(_first(self.fields, "DO"))

    @property
    def title(self) -> str | None:
        return _first(self.fields, "TI", "T1", "CT")

    @property
    def year(self) -> str | None:
        value = _first(self.fields, "PY", "Y1", "DA")
        if not value:
            return None
        match = re.search(r"\b(?:19|20)\d{2}\b", value)
        return match.group(0) if match else value


class RisParseError(ValueError):
    """Raised when a RIS file does not contain valid terminated records."""


def discover_ris(directory: Path, recursive: bool = True) -> list[Path]:
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.casefold() == ".ris"),
        key=lambda path: str(path.relative_to(directory)).casefold(),
    )


def parse_ris_file(path: Path) -> list[RisEntry]:
    payload = _read_text(path)
    records: list[RisEntry] = []
    current: dict[str, list[str]] = {}
    last_tag: str | None = None

    for raw_line in payload.splitlines():
        line = raw_line.rstrip("\r\n")
        match = _TAG_LINE.match(line)
        if match:
            tag, value = match.group(1), match.group(2).strip()
            if tag == "ER":
                if current:
                    records.append(_entry_from_fields(path, current, len(records) + 1))
                current = {}
                last_tag = None
                continue
            current.setdefault(tag, []).append(value)
            last_tag = tag
            continue

        if line.strip() and last_tag and current.get(last_tag):
            current[last_tag][-1] = f"{current[last_tag][-1]} {line.strip()}".strip()

    if current:
        raise RisParseError("RIS record is missing the terminating 'ER  -' line.")
    if not records:
        raise RisParseError("No RIS records were found.")
    return records


def metadata_from_ris(entry: RisEntry) -> ArticleMetadata:
    fields = entry.fields
    authors = parse_ris_authors(fields.get("AU") or fields.get("A1") or [])
    author_text = "; ".join(author.full_name for author in authors)
    title = _first(fields, "TI", "T1", "CT")
    journal = _first(fields, "JF", "JO", "JA", "T2")
    year = entry.year
    doi = entry.doi
    url = _first(fields, "UR", "L1", "L2")
    if not url and doi:
        url = f"https://doi.org/{doi}"
    start_page = _first(fields, "SP")
    end_page = _first(fields, "EP")
    pages = _page_range(start_page, end_page)
    institution = (
        _first(fields, "IN", "PB")
        if _document_type(entry.entry_type)
        in {
            DocumentType.THESIS,
            DocumentType.DISSERTATION,
        }
        else None
    )
    publisher = _first(fields, "PB")
    place = _first(fields, "CY", "PP")
    method = "ris_structured_metadata"
    return ArticleMetadata(
        title=_evidence(title, method),
        authors=authors,
        authors_evidence=_evidence(author_text or None, method),
        journal=_evidence(journal, method),
        place=_evidence(place, method),
        year=_evidence(year, method),
        publication_month=_evidence(_publication_month(fields), method),
        volume=_evidence(_first(fields, "VL"), method),
        issue=_evidence(_first(fields, "IS"), method),
        pages=_evidence(pages, method),
        article_number=_evidence(_first(fields, "AN", "M1"), method),
        doi=_evidence(doi, method),
        url=_evidence(url, method),
        extractor="ris",
        document_type=_document_type(entry.entry_type),
        institution=_evidence(institution, method),
        degree=_evidence(_degree(entry), method),
        program=_evidence(_first(fields, "C2", "C3"), method),
        publisher=_evidence(publisher, method),
        total_pages=_evidence(_first(fields, "NV"), method),
        corporate_author=_evidence(_first(fields, "A3"), method),
        department=_evidence(_first(fields, "AD"), method),
        access_date=_evidence(None, "not_provided", confidence=0.0),
    )


def document_from_ris(entry: RisEntry) -> ProcessedDocument:
    metadata = metadata_from_ris(entry)
    status, errors = classify_metadata(metadata)
    warnings = collect_warnings([], metadata)
    status = apply_warning_status(status, warnings)
    digest = hashlib.sha256(
        entry.source_path.read_bytes() + b"\0" + entry.key.encode("utf-8")
    ).hexdigest()
    return ProcessedDocument(
        source_path=Path(f"{entry.source_path}#{entry.key}"),
        sha256=digest,
        pages=[],
        metadata=metadata,
        status=status,
        errors=errors,
        warnings=warnings,
        variant_type=VariantType.RIS,
        canonical_key=_canonical_key(metadata, entry.key),
    )


def parse_ris_authors(values: list[str]) -> list[Author]:
    authors: list[Author] = []
    for raw_name in values:
        name = _clean(raw_name)
        if not name:
            continue
        if "," in name:
            family, given = [part.strip() for part in name.split(",", maxsplit=1)]
            if family:
                authors.append(
                    Author(
                        full_name=" ".join(part for part in (given, family) if part),
                        family_name=family,
                        given_names=given,
                    )
                )
                continue
        parsed = parse_authors(name)
        if parsed:
            authors.extend(parsed)
    return authors


def ris_normalized_title(entry: RisEntry) -> str:
    return normalized_title(entry.title)


def _entry_from_fields(path: Path, fields: dict[str, list[str]], index: int) -> RisEntry:
    entry_type = (_first(fields, "TY") or "GEN").upper()
    key = _first(fields, "ID", "AN") or f"record-{index}"
    cleaned = {
        tag: [_clean(value) for value in values if _clean(value)] for tag, values in fields.items()
    }
    return RisEntry(entry_type=entry_type, key=key, fields=cleaned, source_path=path)


def _document_type(entry_type: str) -> DocumentType:
    normalized = entry_type.upper()
    if normalized in {"JOUR", "MGZN", "NEWS"}:
        return DocumentType.JOURNAL_ARTICLE
    if normalized in {"THES"}:
        return DocumentType.THESIS
    if normalized in {"BOOK", "RPRT", "SER", "MANUAL"}:
        return DocumentType.BOOK_MANUAL
    if normalized in {"ELEC", "WEB"}:
        return DocumentType.WEB_ARTICLE
    return DocumentType.UNKNOWN


def _degree(entry: RisEntry) -> str | None:
    explicit = _first(entry.fields, "M3", "N1")
    if explicit:
        lowered = explicit.casefold()
        if "disser" in lowered or "master" in lowered:
            return "Dissertação"
        if "tese" in lowered or "thesis" in lowered or "doctoral" in lowered:
            return "Tese"
        return explicit
    return "Tese" if entry.entry_type.upper() == "THES" else None


def _publication_month(fields: dict[str, list[str]]) -> str | None:
    date_value = _first(fields, "PY", "Y1", "DA")
    if not date_value:
        return None
    match = re.search(r"(?:19|20)\d{2}[/-](\d{1,2})", date_value)
    return match.group(1) if match else None


def _page_range(start: str | None, end: str | None) -> str | None:
    if start and end and start != end:
        return f"{start}-{end}"
    return start or end


def _first(fields: dict[str, list[str]], *tags: str) -> str | None:
    for tag in tags:
        values = fields.get(tag, [])
        for value in values:
            if value and value.strip():
                return value.strip()
    return None


def _read_text(path: Path) -> str:
    payload = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _clean(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _SPACE.sub(" ", normalized).strip()


def _evidence(value: str | None, method: str, confidence: float = 0.99) -> Evidence:
    return Evidence(
        value=value,
        confidence=confidence if value else 0.0,
        page_number=None,
        excerpt=value,
        method=method,
    )


def _canonical_key(metadata: ArticleMetadata, fallback: str) -> str:
    if metadata.doi.value:
        return f"doi:{metadata.doi.value.casefold()}"
    title = normalized_title(metadata.title.value)
    year = metadata.year.value or ""
    return f"ris:{title or fallback.casefold()}:{year}"

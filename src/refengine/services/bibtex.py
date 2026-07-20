from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from refengine.domain.enums import DocumentType, VariantType
from refengine.domain.models import ArticleMetadata, Author, Evidence, ProcessedDocument
from refengine.services.author_parser import parse_authors
from refengine.services.validation import apply_warning_status, classify_metadata, collect_warnings

_DOI_PREFIX = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
_LATEX_ACCENTS = {
    r"\\'a": "á",
    r"\\'e": "é",
    r"\\'i": "í",
    r"\\'o": "ó",
    r"\\'u": "ú",
    r'\\"a': "ä",
    r'\\"e': "ë",
    r'\\"i': "ï",
    r'\\"o': "ö",
    r'\\"u': "ü",
    r"\\~a": "ã",
    r"\\~n": "ñ",
    r"\\~o": "õ",
    r"\\c{c}": "ç",
    r"\\c c": "ç",
}


@dataclass(frozen=True)
class BibTeXEntry:
    entry_type: str
    key: str
    fields: dict[str, str]
    source_path: Path

    @property
    def doi(self) -> str | None:
        return normalize_doi(self.fields.get("doi"))

    @property
    def title(self) -> str | None:
        return clean_bibtex_text(self.fields.get("title"))

    @property
    def year(self) -> str | None:
        return clean_bibtex_text(self.fields.get("year"))


class BibTeXParseError(ValueError):
    """Raised when a BibTeX file is structurally malformed."""


def discover_bibtex(directory: Path, recursive: bool = True) -> list[Path]:
    """Discover .bib and .bibtex files deterministically and case-insensitively."""
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    supported = {".bib", ".bibtex"}
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.casefold() in supported),
        key=lambda path: str(path.relative_to(directory)).casefold(),
    )


def parse_bibtex_file(path: Path) -> list[BibTeXEntry]:
    payload = _read_text(path)
    entries: list[BibTeXEntry] = []
    for entry_type, key, body in _scan_entries(payload):
        entries.append(
            BibTeXEntry(
                entry_type=entry_type.casefold(),
                key=key.strip(),
                fields=_parse_fields(body),
                source_path=path,
            )
        )
    return entries


def metadata_from_bibtex(entry: BibTeXEntry) -> ArticleMetadata:
    fields = entry.fields
    title = clean_bibtex_text(fields.get("title"))
    author_text = clean_bibtex_text(fields.get("author"))
    authors = parse_bibtex_authors(author_text)
    document_type = _document_type(entry.entry_type)
    doi = normalize_doi(fields.get("doi"))
    url = clean_bibtex_text(fields.get("url"))
    if not url and doi:
        url = f"https://doi.org/{doi}"

    journal = clean_bibtex_text(fields.get("journal") or fields.get("journaltitle"))
    institution = clean_bibtex_text(fields.get("school") or fields.get("institution"))
    degree = _degree(entry.entry_type, fields)
    publisher = clean_bibtex_text(fields.get("publisher"))
    place = clean_bibtex_text(fields.get("address") or fields.get("location"))
    pages = clean_bibtex_text(fields.get("pages"))
    article_number = clean_bibtex_text(
        fields.get("articleno") or fields.get("eid") or fields.get("numberofarticle")
    )
    total_pages = clean_bibtex_text(fields.get("pagetotal"))
    corporate_author = None
    if not authors and author_text:
        corporate_author = author_text

    method = "bibtex_structured_metadata"
    return ArticleMetadata(
        title=_evidence(title, method),
        authors=authors,
        authors_evidence=_evidence(
            "; ".join(author.full_name for author in authors) or author_text,
            method,
        ),
        journal=_evidence(journal, method),
        place=_evidence(place, method),
        year=_evidence(clean_bibtex_text(fields.get("year")), method),
        publication_month=_evidence(clean_bibtex_text(fields.get("month")), method),
        volume=_evidence(clean_bibtex_text(fields.get("volume")), method),
        issue=_evidence(clean_bibtex_text(fields.get("number") or fields.get("issue")), method),
        pages=_evidence(pages, method),
        article_number=_evidence(article_number, method),
        doi=_evidence(doi, method),
        url=_evidence(url, method),
        extractor="bibtex",
        document_type=document_type,
        institution=_evidence(institution, method),
        degree=_evidence(degree, method),
        program=_evidence(clean_bibtex_text(fields.get("program")), method),
        publisher=_evidence(publisher, method),
        total_pages=_evidence(total_pages, method),
        corporate_author=_evidence(corporate_author, method),
        department=_evidence(clean_bibtex_text(fields.get("department")), method),
        access_date=_evidence(None, "not_provided", confidence=0.0),
    )


def document_from_bibtex(entry: BibTeXEntry) -> ProcessedDocument:
    metadata = metadata_from_bibtex(entry)
    status, errors = classify_metadata(metadata)
    warnings = collect_warnings([], metadata)
    status = apply_warning_status(status, warnings)
    digest = hashlib.sha256(
        entry.source_path.read_bytes() + b"\0" + entry.key.encode("utf-8")
    ).hexdigest()
    synthetic_path = Path(f"{entry.source_path}#{entry.key}")
    return ProcessedDocument(
        source_path=synthetic_path,
        sha256=digest,
        pages=[],
        metadata=metadata,
        status=status,
        errors=errors,
        warnings=warnings,
        variant_type=VariantType.BIBTEX,
        canonical_key=_canonical_key(metadata, entry.key),
    )


def parse_bibtex_authors(value: str | None) -> list[Author]:
    if not value:
        return []
    authors: list[Author] = []
    for raw_name in _split_authors(value):
        name = clean_bibtex_text(raw_name)
        if not name:
            continue
        if "," in name:
            family, given = [part.strip() for part in name.split(",", maxsplit=1)]
            full = " ".join(part for part in (given, family) if part)
            if family and given:
                authors.append(Author(full_name=full, family_name=family, given_names=given))
                continue
        parsed = parse_authors(name)
        if parsed:
            authors.extend(parsed)
    return authors


def clean_bibtex_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", value)
    for source, replacement in _LATEX_ACCENTS.items():
        text = text.replace(source, replacement)
    text = text.replace(r"\&", "&").replace("~", " ")
    text = _remove_protective_braces(text)
    text = _SPACE.sub(" ", text).strip()
    return text or None


def normalize_doi(value: str | None) -> str | None:
    cleaned = clean_bibtex_text(value)
    if not cleaned:
        return None
    cleaned = _DOI_PREFIX.sub("", cleaned).strip().rstrip(".")
    return cleaned or None


def normalized_title(value: str | None) -> str:
    cleaned = clean_bibtex_text(value) or ""
    normalized = unicodedata.normalize("NFKD", cleaned.casefold())
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _read_text(path: Path) -> str:
    payload = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _scan_entries(payload: str) -> Iterator[tuple[str, str, str]]:
    index = 0
    length = len(payload)
    while index < length:
        marker = payload.find("@", index)
        if marker < 0:
            return
        type_match = re.match(r"@\s*([A-Za-z]+)\s*([({])", payload[marker:])
        if not type_match:
            index = marker + 1
            continue
        entry_type = type_match.group(1)
        opening = type_match.group(2)
        closing = "}" if opening == "{" else ")"
        content_start = marker + type_match.end()
        content_end = _find_matching(payload, content_start - 1, opening, closing)
        content = payload[content_start:content_end]
        key, body = _split_key_and_body(content)
        if entry_type.casefold() not in {"comment", "preamble", "string"}:
            yield entry_type, key, body
        index = content_end + 1


def _find_matching(payload: str, opening_index: int, opening: str, closing: str) -> int:
    depth = 0
    quoted = False
    escaped = False
    for index in range(opening_index, len(payload)):
        character = payload[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"' and opening == "(":
            quoted = not quoted
            continue
        if quoted:
            continue
        if character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return index
    raise BibTeXParseError("Unclosed BibTeX entry.")


def _split_key_and_body(content: str) -> tuple[str, str]:
    depth = 0
    quoted = False
    escaped = False
    for index, character in enumerate(content):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
            continue
        if quoted:
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth = max(0, depth - 1)
        elif character == "," and depth == 0:
            return content[:index].strip(), content[index + 1 :]
    raise BibTeXParseError("BibTeX entry has no key/body separator.")


def _parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = 0
    while index < len(body):
        while index < len(body) and (body[index].isspace() or body[index] == ","):
            index += 1
        if index >= len(body):
            break
        name_match = re.match(r"([A-Za-z][A-Za-z0-9_:-]*)", body[index:])
        if not name_match:
            index += 1
            continue
        name = name_match.group(1).casefold()
        index += name_match.end()
        while index < len(body) and body[index].isspace():
            index += 1
        if index >= len(body) or body[index] != "=":
            raise BibTeXParseError(f"Field {name!r} has no '='.")
        index += 1
        while index < len(body) and body[index].isspace():
            index += 1
        value, index = _read_field_value(body, index)
        fields[name] = value
    return fields


def _read_field_value(body: str, index: int) -> tuple[str, int]:
    parts: list[str] = []
    while index < len(body):
        while index < len(body) and body[index].isspace():
            index += 1
        if index >= len(body):
            break
        character = body[index]
        if character == "{":
            end = _find_matching(body, index, "{", "}")
            parts.append(body[index + 1 : end])
            index = end + 1
        elif character == '"':
            value, index = _read_quoted(body, index)
            parts.append(value)
        else:
            start = index
            while index < len(body) and body[index] not in {",", "#"}:
                index += 1
            parts.append(body[start:index].strip())
        while index < len(body) and body[index].isspace():
            index += 1
        if index < len(body) and body[index] == "#":
            index += 1
            continue
        break
    while index < len(body) and body[index].isspace():
        index += 1
    if index < len(body) and body[index] == ",":
        index += 1
    return "".join(parts).strip(), index


def _read_quoted(body: str, index: int) -> tuple[str, int]:
    index += 1
    start = index
    escaped = False
    parts: list[str] = []
    while index < len(body):
        character = body[index]
        if escaped:
            parts.append(body[start : index - 1])
            parts.append(character)
            start = index + 1
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            parts.append(body[start:index])
            return "".join(parts), index + 1
        index += 1
    raise BibTeXParseError("Unclosed quoted BibTeX value.")


def _split_authors(value: str) -> list[str]:
    authors: list[str] = []
    depth = 0
    start = 0
    index = 0
    lowered = value.casefold()
    while index < len(value):
        character = value[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and lowered.startswith(" and ", index):
            authors.append(value[start:index].strip())
            index += 5
            start = index
            continue
        index += 1
    authors.append(value[start:].strip())
    return [author for author in authors if author]


def _remove_protective_braces(value: str) -> str:
    previous = None
    current = value
    while previous != current:
        previous = current
        current = re.sub(r"\{([^{}]*)\}", r"\1", current)
    return current.replace("{", "").replace("}", "")


def _document_type(entry_type: str) -> DocumentType:
    normalized = entry_type.casefold()
    if normalized == "article":
        return DocumentType.JOURNAL_ARTICLE
    if normalized in {"phdthesis", "thesis"}:
        return DocumentType.THESIS
    if normalized in {"mastersthesis", "masterthesis"}:
        return DocumentType.DISSERTATION
    if normalized in {"book", "manual", "techreport", "report"}:
        return DocumentType.BOOK_MANUAL
    if normalized in {"online", "webpage"}:
        return DocumentType.WEB_ARTICLE
    return DocumentType.UNKNOWN


def _degree(entry_type: str, fields: dict[str, str]) -> str | None:
    explicit = clean_bibtex_text(fields.get("type"))
    if explicit:
        return explicit
    normalized = entry_type.casefold()
    if normalized in {"phdthesis", "thesis"}:
        return "Tese"
    if normalized in {"mastersthesis", "masterthesis"}:
        return "Dissertação"
    return None


def _evidence(value: str | None, method: str, confidence: float = 0.99) -> Evidence:
    return Evidence(
        value=value,
        confidence=confidence if value else 0.0,
        page_number=None,
        excerpt=value,
        method=method if value else "not_extracted",
    )


def _canonical_key(metadata: ArticleMetadata, fallback: str) -> str:
    doi = normalize_doi(metadata.doi.value)
    if doi:
        return f"doi:{doi.casefold()}"
    title = normalized_title(metadata.title.value)
    year = metadata.year.value or ""
    return f"title:{title}|year:{year}" if title else f"bibtex:{fallback.casefold()}"

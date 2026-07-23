from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from refengine.domain.models import PageText

_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s<>\]\[{}\"']+", re.IGNORECASE)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

_SECTION_MARKERS = {
    "abstract": re.compile(r"(?im)^\s*(?:abstract|resumo)\s*[:—-]?\s*$"),
    "keywords": re.compile(r"(?im)^\s*(?:keywords?|key\s+words|palavras[- ]chave)\s*[:—-]"),
    "references": re.compile(
        r"(?im)^\s*(?:references|refer[eê]ncias|bibliography|bibliografia)\s*$"
    ),
}
_ARTICLE_LABEL = re.compile(
    r"(?im)^\s*(?:research|review|original|scientific|technical)\s+article\b"
    r"|^\s*(?:short communication|article in press)\b"
)
_PUBLICATION_HISTORY = re.compile(
    r"(?is)\breceived\b.{0,180}\baccepted\b"
    r"|\bavailable online\b"
    r"|\bpublished online\b"
    r"|\bdate of publication\b"
)
_EVENT_MARKER = re.compile(
    r"(?i)\b(?:proceedings of|conference|congress|symposium|workshop|seminar)\b"
)
_MONOGRAPH_MARKER = re.compile(r"(?i)\bISBN(?:-1[03])?\b")
_PERIODICAL_MARKER = re.compile(
    r"(?i)\bISSN\b"
    r"|\bvol(?:ume)?\.?\s*\d+"
    r"|\bv\.?\s*\d+\s*,\s*n\.?\s*\d+"
    r"|\bissue\s*\d+"
    r"|\bpp?\.?\s*\d+\s*[-–—]\s*\d+"
)

_PORTUGUESE_CITATION = re.compile(
    r"(?im)^\s*(?P<journal>[A-ZÀ-Ý][^\n]{2,140}?)\s*,?\s*"
    r"v\.?\s*(?P<volume>\d+)"
    r"(?:\s*,\s*n\.?\s*(?P<issue>[A-Za-z0-9.-]+))?"
    r"(?:\s*,\s*p\.?\s*(?P<start>\d+)\s*[-–—]\s*(?P<end>\d+))?"
    r"(?:\s*,[^\n]{0,70})?\s*,?\s*(?P<year>(?:19|20)\d{2})\s*$"
)
_ELSEVIER_CITATION = re.compile(
    r"(?im)^\s*(?P<journal>[A-ZÀ-Ý][^\n]{2,140}?)\s+"
    r"(?P<volume>\d+)\s*\((?P<year>(?:19|20)\d{2})\)\s*"
    r"(?:(?P<start>\d+)\s*[-–—]\s*(?P<end>\d+)|(?P<article>[A-Za-z]?\d{4,}))\s*$"
)
_VOLUME_ISSUE = re.compile(
    r"(?i)\b(?:vol(?:ume)?\.?|v\.?)\s*(?P<volume>\d+)"
    r"(?:\s*[,;]?\s*(?:no\.?|n\.?|issue)\s*(?P<issue>[A-Za-z0-9.-]+))?"
)
_PAGE_RANGE = re.compile(r"(?i)\b(?:pp?\.?|pages?)\s*(?P<start>\d+)\s*[-–—]\s*(?P<end>\d+)")
_ARTICLE_NUMBER = re.compile(
    r"(?i)\b(?:article(?:\s+number)?|art\.?\s*no\.?)\s*[:#]?\s*(?P<number>[A-Za-z]?\d{4,})\b"
)
_PUBLISHED_YEAR = re.compile(
    r"(?i)\b(?:published|publication(?:\s+date)?|available online)\b"
    r"[^\n]{0,80}?\b(?P<year>(?:19|20)\d{2})\b"
)
_COPYRIGHT_YEAR = re.compile(r"(?i)(?:©|copyright)\s*(?P<year>(?:19|20)\d{2})")
_EXPLICIT_JOURNAL = re.compile(
    r"(?im)^\s*(?:journal(?:\s+title)?|published\s+in)\s*[:—-]\s*"
    r"(?P<journal>[^\n]{3,140})\s*$"
)
_ISSN = re.compile(r"(?i)\b(?:e-?ISSN|p-?ISSN|ISSN)\b")

_AUTHOR_SEPARATOR = re.compile(r"\s*(?:;|\band\b|\be\b|&)\s*", re.IGNORECASE)
_AUTHOR_NOISE = re.compile(
    r"(?i)\b(?:abstract|resumo|keywords?|palavras[- ]chave|doi|issn|volume|issue|received|accepted|published|references)\b"
)


@dataclass(frozen=True)
class ArticleSignals:
    """Generic, publication-independent signals found in a PDF."""

    has_doi: bool
    has_abstract: bool
    has_keywords: bool
    has_references: bool
    has_article_label: bool
    has_publication_history: bool
    has_periodical_marker: bool
    has_event_marker: bool
    has_monograph_marker: bool

    @property
    def looks_like_periodical_article(self) -> bool:
        """Return true only when several independent article signals agree."""
        if self.has_event_marker or self.has_monograph_marker:
            return False
        if self.has_article_label and (
            self.has_doi or self.has_abstract or self.has_periodical_marker
        ):
            return True
        if (
            self.has_doi
            and self.has_abstract
            and (self.has_references or self.has_periodical_marker or self.has_publication_history)
        ):
            return True
        if self.has_abstract and self.has_references and self.has_periodical_marker:
            return True
        return bool(
            self.has_periodical_marker
            and self.has_publication_history
            and (self.has_doi or self.has_references or self.has_keywords)
        )


def article_signals(pages: list[PageText]) -> ArticleSignals:
    """Inspect page text without relying on a publisher or known journal name."""
    front = _bounded_text(pages[:8], 120_000)
    whole = _bounded_text(pages, 240_000)
    normalized_front = normalize_for_matching(front)
    normalized_whole = normalize_for_matching(whole)
    return ArticleSignals(
        has_doi=bool(_DOI.search(front)),
        has_abstract=bool(_SECTION_MARKERS["abstract"].search(front)),
        has_keywords=bool(_SECTION_MARKERS["keywords"].search(front)),
        has_references=bool(_SECTION_MARKERS["references"].search(whole)),
        has_article_label=bool(_ARTICLE_LABEL.search(front)),
        has_publication_history=bool(_PUBLICATION_HISTORY.search(front)),
        has_periodical_marker=bool(_PERIODICAL_MARKER.search(front)),
        has_event_marker=bool(_EVENT_MARKER.search(normalized_front)),
        has_monograph_marker=bool(_MONOGRAPH_MARKER.search(normalized_whole)),
    )


def generic_periodical_fields(
    first_text: str,
    searchable_text: str,
    *,
    doi: str | None,
) -> dict[str, str | bool]:
    """Extract common journal metadata from generic front-matter patterns.

    The function deliberately returns only values supported by visible text. It does
    not infer a journal from a DOI registry or from a filename.
    """
    front = _bounded_string(f"{first_text}\n{searchable_text}", 180_000)
    clean_lines = [_clean_line(line) for line in front.splitlines()]
    lines = [line for line in clean_lines if line]
    result: dict[str, str | bool] = {}
    result.update(_front_matter_title_authors(lines))

    citation = _PORTUGUESE_CITATION.search(front) or _ELSEVIER_CITATION.search(front)
    if citation:
        journal = _clean_journal(citation.groupdict().get("journal"))
        if journal:
            result["journal"] = journal
        for field in ("volume", "issue", "year", "article"):
            value = citation.groupdict().get(field)
            if value:
                result["article_number" if field == "article" else field] = value
        start = citation.groupdict().get("start")
        end = citation.groupdict().get("end")
        if start and end:
            result["pages"] = f"{start}-{end}"

    if "journal" not in result:
        explicit = _EXPLICIT_JOURNAL.search(front)
        if explicit:
            journal = _clean_journal(explicit.group("journal"))
            if journal:
                result["journal"] = journal

    if "journal" not in result:
        result.update(_journal_near_issn(lines))

    volume_issue = _VOLUME_ISSUE.search(front)
    if volume_issue:
        result.setdefault("volume", volume_issue.group("volume"))
        if volume_issue.group("issue"):
            result.setdefault("issue", volume_issue.group("issue"))

    page_range = _PAGE_RANGE.search(front)
    if page_range:
        result.setdefault(
            "pages",
            f"{page_range.group('start')}-{page_range.group('end')}",
        )

    article_number = _ARTICLE_NUMBER.search(front)
    if article_number:
        result.setdefault("article_number", article_number.group("number"))

    published = _PUBLISHED_YEAR.search(front)
    copyright_year = _COPYRIGHT_YEAR.search(front)
    if published:
        result.setdefault("year", published.group("year"))
    elif copyright_year:
        result.setdefault("year", copyright_year.group("year"))
    else:
        year = _year_from_front_lines(lines)
        if year:
            result.setdefault("year", year)

    source_url = _first_non_doi_url(front, doi)
    if source_url:
        result["source_url"] = source_url

    if any(key in result for key in ("journal", "volume", "issue", "pages", "article_number")):
        result["extractor"] = "generic_periodical_structure"
    return result


def normalize_for_matching(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def _front_matter_title_authors(lines: list[str]) -> dict[str, str | bool]:
    """Read title and authors from visible lines before Abstract/front-matter metadata."""
    candidates = lines[:50]
    stop = next(
        (
            index
            for index, line in enumerate(candidates)
            if normalize_for_matching(line) in {"abstract", "resumo"}
        ),
        len(candidates),
    )
    front_lines = candidates[:stop]
    author_index = next(
        (index for index, line in enumerate(front_lines) if _looks_like_author_line(line)),
        None,
    )
    if author_index is None:
        return {}

    title_lines = [
        line
        for line in front_lines[max(0, author_index - 4) : author_index]
        if _looks_like_title_line(line)
    ]
    if not title_lines:
        return {}
    title = " ".join(title_lines[-3:])
    return {
        "title": title,
        "authors": front_lines[author_index],
        "extractor": "generic_periodical_structure",
    }


def _looks_like_author_line(value: str) -> bool:
    cleaned = _clean_line(value)
    if not 5 <= len(cleaned) <= 240 or _AUTHOR_NOISE.search(cleaned):
        return False
    if re.search(r"https?://|10\.\d{4,9}/|\b(?:19|20)\d{2}\b", cleaned, re.IGNORECASE):
        return False
    parts = [part.strip(" ,.*†‡0123456789") for part in _AUTHOR_SEPARATOR.split(cleaned)]
    parts = [part for part in parts if part]
    if len(parts) < 2 and "," in cleaned:
        parts = [part.strip(" ,.*†‡0123456789") for part in cleaned.split(",") if part.strip()]
    if not 1 <= len(parts) <= 20:
        return False
    return all(
        1 <= len(part.split()) <= 6
        and all(
            token[:1].isupper()
            or token.casefold() in {"de", "da", "do", "dos", "das", "van", "von"}
            for token in part.split()
            if token
        )
        for part in parts
    )


def _looks_like_title_line(value: str) -> bool:
    cleaned = _clean_line(value)
    matching = normalize_for_matching(cleaned)
    if not 5 <= len(cleaned) <= 260:
        return False
    if _AUTHOR_NOISE.search(cleaned) or _ISSN.search(cleaned):
        return False
    if re.search(r"https?://|10\.\d{4,9}/", cleaned, re.IGNORECASE):
        return False
    if _PORTUGUESE_CITATION.fullmatch(cleaned) or _ELSEVIER_CITATION.fullmatch(cleaned):
        return False
    if matching in {"research article", "review article", "original article", "article"}:
        return False
    if _VOLUME_ISSUE.search(cleaned) and _YEAR.search(cleaned):
        return False
    return len(cleaned.split()) >= 3


def _journal_near_issn(lines: list[str]) -> dict[str, str | bool]:
    for index, line in enumerate(lines[:80]):
        if not _ISSN.search(line):
            continue
        candidates = lines[max(0, index - 3) : index]
        for candidate in reversed(candidates):
            journal = _clean_journal(candidate)
            if journal:
                return {
                    "journal": journal,
                    "extractor": "generic_periodical_structure",
                }
    return {}


def _clean_journal(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = _clean_line(value).strip(" ,;:.-")
    matching = normalize_for_matching(cleaned)
    if not 3 <= len(cleaned) <= 140:
        return None
    rejected = (
        "abstract",
        "resumo",
        "keywords",
        "palavras chave",
        "research article",
        "review article",
        "original article",
        "received",
        "accepted",
        "doi",
        "http",
        "issn",
    )
    if any(marker in matching for marker in rejected):
        return None
    if len(cleaned.split()) > 18:
        return None
    if not re.search(r"[A-Za-zÀ-ÿ]", cleaned):
        return None
    return cleaned


def _year_from_front_lines(lines: list[str]) -> str | None:
    for line in lines[:60]:
        matching = normalize_for_matching(line)
        if any(marker in matching for marker in ("received", "accepted", "references")):
            continue
        years = _YEAR.findall(line)
        if years:
            return str(years[-1])
    return None


def _first_non_doi_url(text: str, doi: str | None) -> str | None:
    normalized_doi = _normalize_doi(doi)
    for match in _URL.finditer(text):
        candidate = match.group(0).rstrip(".,;:)")
        candidate_doi = _normalize_doi(candidate) if "doi.org/" in candidate.casefold() else None
        if candidate_doi and candidate_doi == normalized_doi:
            continue
        return candidate
    return None


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(
        r"^(?:doi\s*:\s*)?https?://(?:dx\.)?doi\.org/",
        "",
        value.strip(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^doi\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.rstrip(".,;:)").casefold()
    return cleaned or None


def _bounded_text(pages: list[PageText], limit: int) -> str:
    return _bounded_string("\n".join(page.text for page in pages if page.text), limit)


def _bounded_string(value: str, limit: int) -> str:
    return value[:limit]


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()

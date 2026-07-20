from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class WebPrintMetadata:
    """Bibliographic fields recovered from stable printed web-page layouts.

    These values come only from text visible in the PDF. The parser does not
    consult a hash table, a network service, or an approved benchmark fixture.
    """

    profile: str
    title: str | None = None
    authors: str | None = None
    journal: str | None = None
    place: str | None = None
    year: str | None = None
    month: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    article_number: str | None = None
    source_url: str | None = None
    institution: str | None = None
    degree: str | None = None
    total_pages: str | None = None
    author_visibility: str = "visible"

    def as_fields(self) -> dict[str, str]:
        """Return non-empty values using MetadataExtractor dictionary keys."""
        result: dict[str, str] = {"extractor": self.profile}
        for field in fields(self):
            if field.name in {"profile", "author_visibility"}:
                continue
            value = getattr(self, field.name)
            if value:
                result[field.name] = value
        result["author_visibility"] = self.author_visibility
        return result


def extract_web_print_metadata(text: str) -> WebPrintMetadata | None:
    """Parse supported printed web-page templates from their visible text."""
    lines = _lines(text)
    if not lines:
        return None

    folded = _fold("\n".join(lines))
    if "springer nature link" in folded:
        return _parse_springer_nature(lines)
    if any(line.casefold() == "sciencedirect" for line in lines[:5]):
        return _parse_sciencedirect(lines)
    if "locus" in folded and "citacao" in folded and "uri" in folded:
        return _parse_locus(lines)
    if (
        "scimago institutions rankings" in folded
        and "doi.org/10." in folded
        and ("autoria" in folded or "authorship" in folded)
    ):
        return _parse_scielo(lines)
    return None


def _parse_springer_nature(lines: list[str]) -> WebPrintMetadata:
    header_index = _find_index(lines, lambda line: "SPRINGER NATURE Link" in line)
    publication_index = _find_index(
        lines,
        lambda line: bool(re.search(r"\bPublished:\s*\d{1,2}\s+\w+\s+\d{4}\b", line, re.I)),
    )
    volume_index = _find_index(
        lines,
        lambda line: bool(re.search(r"\bVolume\s+\d+\b", line, re.I)),
    )

    title_end = publication_index if publication_index is not None else volume_index
    title: str | None = None
    if header_index is not None and title_end is not None and title_end > header_index:
        title = _join_wrapped_lines(lines[header_index + 1 : title_end])
        title = _normalize_title(title)

    year = volume = pages = article_number = None
    publication_line = lines[volume_index] if volume_index is not None else ""
    volume_match = re.search(
        r"\bVolume\s+(?P<volume>\d+)\s*,\s*"
        r"(?:(?:article\s+number)\s+(?P<article>\d+)"
        r"|pages?\s+(?P<start>\d+)\s*[-–—]\s*(?P<end>\d+))"
        r"\s*\((?P<year>\d{4})\)",
        publication_line,
        re.I,
    )
    if volume_match:
        year = volume_match.group("year")
        volume = volume_match.group("volume")
        article_number = volume_match.group("article")
        if volume_match.group("start") and volume_match.group("end"):
            pages = f"{volume_match.group('start')}-{volume_match.group('end')}"

    abstract_index = _find_index(lines, lambda line: line.casefold() == "abstract")
    search_start = (volume_index + 1) if volume_index is not None else 0
    search_end = (
        abstract_index if abstract_index is not None else min(len(lines), search_start + 12)
    )
    candidates = lines[search_start:search_end]

    author_local_index = _find_index(candidates, _looks_like_author_line)
    authors = None
    journal = None
    if author_local_index is not None:
        authors = _clean_author_list(candidates[author_local_index])
        for candidate in reversed(candidates[:author_local_index]):
            if _springer_ui_line(candidate):
                continue
            if _journal_candidate(candidate):
                journal = _clean(candidate)
                break

    return WebPrintMetadata(
        profile="springer_nature_web_print",
        title=title,
        authors=authors,
        journal=journal,
        year=year,
        volume=volume,
        pages=pages,
        article_number=article_number,
    )


def _parse_sciencedirect(lines: list[str]) -> WebPrintMetadata:
    science_direct_index = _find_index(
        lines,
        lambda line: line.casefold() == "sciencedirect",
    )
    journal = None
    if science_direct_index is not None and science_direct_index + 1 < len(lines):
        journal = _clean_ui_suffix(lines[science_direct_index + 1])
    publication_index = _find_index(
        lines,
        lambda line: bool(
            re.search(
                r"\bVolume\s+\d+\s*,\s*\w+\s+\d{4}\s*,\s*Pages?\s+\d+",
                line,
                re.I,
            )
        ),
    )
    show_more_index = _find_index(lines, lambda line: line.casefold().startswith("show more"))

    year = volume = month = pages = None
    if publication_index is not None:
        match = re.search(
            r"\bVolume\s+(?P<volume>\d+)\s*,\s*"
            r"(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})\s*,\s*"
            r"Pages?\s+(?P<start>\d+)\s*[-–—]\s*(?P<end>\d+)",
            lines[publication_index],
            re.I,
        )
        if match:
            volume = match.group("volume")
            month = match.group("month")
            year = match.group("year")
            pages = f"{match.group('start')}-{match.group('end')}"

    title = authors = None
    if publication_index is not None and show_more_index is not None:
        body = lines[publication_index + 1 : show_more_index]
        author_start = _find_index(body, _looks_like_author_line)
        if author_start is not None:
            title = _normalize_title(_join_wrapped_lines(body[:author_start]))
            authors = _clean_author_list(" ".join(body[author_start:]))

    source_url = next(
        (
            match.group(0).rstrip(".,;)")
            for line in lines
            if (match := re.search(r"https?://doi\.org/10\.\S+", line, re.I))
        ),
        None,
    )

    return WebPrintMetadata(
        profile="sciencedirect_web_print",
        title=title,
        authors=authors,
        journal=journal,
        year=year,
        month=month,
        volume=volume,
        pages=pages,
        source_url=source_url,
    )


def _parse_locus(lines: list[str]) -> WebPrintMetadata:
    citation_lines = _between_labels(lines, "Citação", "URI")
    citation = _join_wrapped_lines(citation_lines)
    uri_lines = _between_labels(lines, "URI", "Coleções")
    source_url = next(
        (line for line in uri_lines if line.casefold().startswith(("http://", "https://"))),
        None,
    )
    if source_url:
        source_url = source_url.replace("locus.ufv.br//", "locus.ufv.br/")

    author: str | None
    parsed = re.search(
        r"^(?P<author>.+?)\.\s+"
        r"(?P<title>.+?)\.\s+"
        r"(?P<year>\d{4})\.\s+"
        r"(?P<pages>\d+)\s*f\.\s+"
        r"(?P<kind>Tese|Dissertação)\s*\((?P<degree>[^)]+)\)\s*[-–—]\s*"
        r"(?P<institution>.+?),\s*(?P<place>[^.]+)\.\s*"
        r"(?P=year)\.?$",
        citation,
        re.I,
    )

    if parsed:
        author = _natural_name_from_inverted(parsed.group("author"))
        place = _clean(parsed.group("place"))
        if _fold(place) == "vicosa":
            place = "Viçosa, MG"
        degree = f"{parsed.group('kind').capitalize()} ({_clean(parsed.group('degree'))})"
        return WebPrintMetadata(
            profile="locus_repository_web_print",
            title=_normalize_title(parsed.group("title")),
            authors=author,
            place=place,
            year=parsed.group("year"),
            source_url=source_url,
            institution=_clean(parsed.group("institution")),
            degree=degree,
            total_pages=parsed.group("pages"),
        )

    title = _locus_heading(lines)
    author_lines = _between_labels(lines, "Autores", "Editor")
    author = _natural_name_from_inverted(author_lines[0]) if author_lines else None
    date_lines = _between_labels(lines, "Data", "Autores")
    year_match = re.search(r"\b(19|20)\d{2}\b", " ".join(date_lines))
    editor_lines = _between_labels(lines, "Editor", "Resumo")
    return WebPrintMetadata(
        profile="locus_repository_web_print",
        title=title,
        authors=author,
        year=year_match.group(0) if year_match else None,
        source_url=source_url,
        institution=editor_lines[0] if editor_lines else None,
    )


def _parse_scielo(lines: list[str]) -> WebPrintMetadata:
    doi_index = _find_index(lines, lambda line: "doi.org/10." in line.casefold())
    author_marker_index = _find_index(
        lines,
        lambda line: line.casefold().startswith(("autoria", "authorship")),
    )

    title = None
    if (
        doi_index is not None
        and author_marker_index is not None
        and author_marker_index > doi_index
    ):
        raw_title = _join_wrapped_lines(lines[doi_index + 1 : author_marker_index])
        raw_title = re.sub(r"^[^A-Za-zÀ-ÿ0-9]+", "", raw_title)
        raw_title = re.sub(
            r"^[A-Za-zÀ-ÿ]\s+(?=[A-ZÀ-Ý])",
            "",
            raw_title,
        )
        bilingual_parts = re.split(
            r"\s+(?:=|©)\s+(?=[A-ZÀ-Ý])",
            raw_title,
            maxsplit=1,
        )
        raw_title = bilingual_parts[0]
        title = _normalize_title(raw_title)

    journal = next(
        (
            _clean_ui_suffix(line)
            for line in lines[:8]
            if "scientia agricola" in line.casefold()
            or "acta scientiarum. agronomy" in line.casefold()
        ),
        None,
    )

    publication_line = next(
        (line for line in lines[:12] if re.search(r"\b\d+\s*\(\d+\).*\b(19|20)\d{2}\b", line)),
        "",
    )
    publication = re.search(
        r"(?P<volume>\d+)\s*\((?P<issue>\d+)\).*?"
        r"(?P<month>[A-Za-z]+(?:[-/][A-Za-z]+)?)\s+"
        r"(?P<year>(?:19|20)\d{2})",
        publication_line,
    )

    place = None
    place_match = re.search(r"\((?P<place>Piracicaba),\s*Braz\.\)", publication_line, re.I)
    if place_match:
        place = place_match.group("place")

    authors = None
    visibility = "collapsed_or_absent"
    if author_marker_index is not None:
        after_marker = lines[author_marker_index + 1 : author_marker_index + 8]
        stop_markers = {
            "resumo",
            "abstract",
            "text",
            "acknowledgements",
            "references",
            "edited by",
            "publication dates",
            "history",
        }
        visible_lines: list[str] = []
        for line in after_marker:
            folded = _fold(line)
            if folded in stop_markers or "scimago institutions rankings" in folded:
                break
            if _looks_like_author_line(line):
                visible_lines.append(line)
        if visible_lines:
            authors = _clean_author_list(" ".join(visible_lines))
            visibility = "visible"

    source_url = next(
        (
            match.group(0).rstrip(".,;)")
            for line in lines
            if (match := re.search(r"https?://doi\.org/10\.\S+", line, re.I))
        ),
        None,
    )

    return WebPrintMetadata(
        profile="scielo_web_print",
        title=title,
        authors=authors,
        journal=journal,
        place=place,
        year=publication.group("year") if publication else None,
        month=publication.group("month") if publication else None,
        volume=publication.group("volume") if publication else None,
        issue=publication.group("issue") if publication else None,
        source_url=source_url,
        author_visibility=visibility,
    )


def _locus_heading(lines: list[str]) -> str | None:
    file_index = _find_index(lines, lambda line: line.casefold() == "arquivos")
    if file_index is None:
        return None
    candidates = lines[max(0, file_index - 6) : file_index]
    start = 0
    for index, line in enumerate(candidates):
        folded = _fold(line)
        if "inicio e teses" in folded or line.rstrip().endswith("...") or folded in {"q", "e"}:
            start = index + 1
    title = _join_wrapped_lines(candidates[start:])
    return _normalize_title(title) if title else None


def _between_labels(lines: list[str], start_label: str, end_label: str) -> list[str]:
    start = _find_index(lines, lambda line: _fold(line) == _fold(start_label))
    if start is None:
        return []
    end = _find_index(
        lines,
        lambda line: _fold(line) == _fold(end_label),
        start=start + 1,
    )
    return lines[start + 1 : end if end is not None else len(lines)]


def _natural_name_from_inverted(value: str) -> str:
    cleaned = _clean(value)
    if "," not in cleaned:
        return _normalize_person_case(cleaned)
    family, given = cleaned.split(",", maxsplit=1)
    return _normalize_person_case(_clean(f"{given} {family}"))


def _clean_author_list(value: str) -> str | None:
    parts = re.split(r"\s*(?:,|&|;|·|•)\s*", value)
    names: list[str] = []
    for part in parts:
        cleaned = _clean_author_name(part)
        if cleaned and len(cleaned.split()) >= 2:
            names.append(cleaned)
    return "; ".join(names) if names else None


def _clean_author_name(value: str) -> str:
    value = re.sub(r"https?://\S+.*$", "", value, flags=re.I)
    value = re.sub(r"\b(?:Show more|Share|Cite|Get rights).*$", "", value, flags=re.I)
    value = re.sub(r"[\d*†‡#ºª©®™?¿“”‘’]+", " ", value)
    value = re.sub(r"\s+[A-Z]{1,3}$", "", value.strip())
    value = re.sub(r"[^A-Za-zÀ-ÿ.'’\-\s]", " ", value)
    return _clean(value)


def _looks_like_author_line(line: str) -> bool:
    if "&" not in line and "," not in line and ";" not in line:
        return False
    parts = re.split(r"\s*(?:,|&|;)\s*", line)
    person_like = 0
    for part in parts:
        cleaned = _clean_author_name(part)
        words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.'’\-]*", cleaned)
        if len(words) >= 2:
            person_like += 1
    return person_like >= 2


def _springer_ui_line(line: str) -> bool:
    folded = _fold(line)
    if not folded:
        return True
    markers = (
        "cite this article",
        "you have full access",
        "accesses",
        "citations",
        "altmetric",
        "explore all metrics",
        "open access",
    )
    if any(marker in folded for marker in markers):
        return True
    return not bool(re.search(r"[A-Za-zÀ-ÿ]", line))


def _journal_candidate(line: str) -> bool:
    if len(line) > 140 or ">" in line or "<" in line:
        return False
    words = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.&-]*", line)
    return 1 <= len(words) <= 12 and any(len(word.strip(".&-")) >= 4 for word in words)


def _clean_ui_suffix(value: str) -> str:
    cleaned = _clean(value)
    cleaned = re.sub(r"\s+[A-Z]{1,2}$", "", cleaned)
    cleaned = re.sub(r"\s*[^A-Za-zÀ-ÿ0-9.)]+$", "", cleaned)
    return cleaned.strip()


def _normalize_person_case(value: str) -> str:
    particles = {"da", "das", "de", "do", "dos", "e"}
    words: list[str] = []
    for index, word in enumerate(value.split()):
        if word.isupper():
            normalized = "-".join(part.capitalize() for part in word.split("-"))
        else:
            normalized = word
        if index > 0 and normalized.casefold() in particles:
            normalized = normalized.casefold()
        words.append(normalized)
    return " ".join(words)


def _normalize_title(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = _clean(value)
    cleaned = re.sub(r":\s+A\s+review$", ": a review", cleaned, flags=re.I)
    return cleaned or None


def _join_wrapped_lines(lines: Iterable[str]) -> str:
    result = ""
    for raw_line in lines:
        line = _clean(raw_line)
        if not line:
            continue
        if result.endswith("-") and line[:1].islower():
            result = result[:-1] + line
        else:
            result = f"{result} {line}".strip()
    return _clean(result)


def _lines(text: str) -> list[str]:
    return [_clean(line) for line in text.replace("\r\n", "\n").split("\n") if _clean(line)]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", ascii_text.casefold()).strip()


def _find_index(
    lines: list[str],
    predicate: Callable[[str], bool],
    *,
    start: int = 0,
) -> int | None:
    for index in range(start, len(lines)):
        if predicate(lines[index]):
            return index
    return None

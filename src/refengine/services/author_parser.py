from __future__ import annotations

import re

from refengine.domain.models import Author

_AUTHOR_MARKERS = re.compile(r"(?:\d+(?:,\d+)*)|[*†‡#]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+", re.IGNORECASE)
_AFFILIATION_LETTERS = re.compile(r"\s+[a-d](?:,[a-d])*(?=\s*[,;]|\s*$)", re.IGNORECASE)
_SEPARATOR = re.compile(r"\s+(?:and|e)\s+|\s*&\s*|\s*[;·•]\s*", re.IGNORECASE)


def parse_authors(raw: str | None) -> list[Author]:
    """Parse a publisher author line without inventing people absent from the PDF."""
    if not raw:
        return []

    cleaned = raw.replace(" ", " ").replace(" ", " ")
    cleaned = _AUTHOR_MARKERS.sub("", cleaned)
    cleaned = _AFFILIATION_LETTERS.sub("", cleaned)
    cleaned = _SEPARATOR.sub(", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")

    names = [part.strip(" ,") for part in cleaned.split(",") if part.strip(" ,")]
    authors: list[Author] = []
    for name in names:
        if _looks_like_affiliation(name):
            continue
        normalized = _normalize_case(name)
        tokens = normalized.split()
        if len(tokens) < 2:
            continue
        family_tokens = _family_name_tokens(tokens)
        given_tokens = tokens[: len(tokens) - len(family_tokens)]
        authors.append(
            Author(
                full_name=normalized,
                family_name=" ".join(family_tokens),
                given_names=" ".join(given_tokens),
            )
        )
    return authors


def _looks_like_affiliation(value: str) -> bool:
    lowered = value.casefold()
    markers = ("universidade", "department", "departamento", "faculdade", "institute", "laboratory")
    return any(marker in lowered for marker in markers) or "@" in value


def _family_name_tokens(tokens: list[str]) -> list[str]:
    """Return the entry surname without moving Portuguese particles to the front.

    Names such as ``Edmar Soares de Vasconcelos`` are entered under
    ``VASCONCELOS``. French and Dutch particles may be integral to the family name,
    while generational suffixes stay attached to the preceding surname.
    """
    suffixes = {"filho", "júnior", "junior", "neto", "sobrinho"}
    integral_particles = {"le", "la", "lo", "van", "von"}
    if len(tokens) >= 2 and tokens[-1].casefold() in suffixes:
        return tokens[-2:]
    if len(tokens) >= 2 and tokens[-2].casefold() in integral_particles:
        return tokens[-2:]
    return tokens[-1:]


def _normalize_case(name: str) -> str:
    if not name.isupper():
        return name
    particles = {"da", "das", "de", "do", "dos", "e"}
    words: list[str] = []
    for index, word in enumerate(name.split()):
        normalized = "-".join(part.capitalize() for part in word.split("-"))
        if index > 0 and normalized.casefold() in particles:
            normalized = normalized.casefold()
        words.append(normalized)
    return " ".join(words)


def parse_review_authors(raw: str | None) -> list[Author]:
    """Parse semicolon-separated reviewed names in natural or ABNT entry form.

    Accepted examples:
    - ``Julio Marcos Filho``
    - ``MARCOS FILHO, J.``
    - ``Carlo Ingrao; LO GIUDICE, Agata``
    """
    if not raw:
        return []
    authors: list[Author] = []
    for segment in raw.split(";"):
        name = re.sub(r"\s+", " ", segment).strip(" ,")
        if not name:
            continue
        if "," in name:
            family, given = [part.strip() for part in name.split(",", maxsplit=1)]
            if not family or not given:
                raise ValueError(f"Invalid reviewed author: {segment!r}")
            authors.append(
                Author(
                    full_name=f"{given} {family}".strip(),
                    family_name=family,
                    given_names=given,
                )
            )
            continue
        parsed = parse_authors(name)
        if len(parsed) != 1:
            raise ValueError(f"Invalid reviewed author: {segment!r}")
        authors.append(parsed[0])
    return authors

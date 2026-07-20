from __future__ import annotations

import difflib
from dataclasses import dataclass

from refengine.domain.models import ProcessedDocument
from refengine.services.bibtex import normalize_doi, normalized_title
from refengine.services.ris import RisEntry


@dataclass(frozen=True)
class RisMatch:
    entry: RisEntry
    score: float
    method: str


def match_ris_entry(document: ProcessedDocument, entries: list[RisEntry]) -> RisMatch | None:
    """Match a RIS record to a PDF without selecting any RIS field value yet."""
    document_doi = normalize_doi(document.metadata.doi.value)
    if document_doi:
        for entry in entries:
            if entry.doi and entry.doi.casefold() == document_doi.casefold():
                return RisMatch(entry=entry, score=1.0, method="doi")

    title = normalized_title(document.metadata.title.value)
    if not title:
        return None
    best: RisMatch | None = None
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
            best = RisMatch(entry=entry, score=score, method="title")
    return best

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from pathlib import Path

from refengine.domain.enums import ProcessingStatus, VariantType, WarningCode
from refengine.domain.models import ProcessedDocument
from refengine.services.bibliographic_record import merge_records
from refengine.services.document_classifier import normalize, normalize_doi

_STATUS_SCORE = {
    ProcessingStatus.PROCESSED: 4,
    ProcessingStatus.PROCESSED_WITH_WARNINGS: 3,
    ProcessingStatus.REVIEW_REQUIRED: 2,
    ProcessingStatus.FAILED: 1,
}
_VARIANT_SCORE = {
    VariantType.PUBLISHER_ORIGINAL: 5,
    VariantType.INSTITUTIONAL_REPOSITORY: 4,
    VariantType.SCANNED: 3,
    VariantType.BROWSER_PRINT: 2,
    VariantType.BIBTEX: 4,
    VariantType.UNKNOWN: 1,
}
_SECONDARY_VARIANTS = {
    VariantType.BROWSER_PRINT,
    VariantType.SCANNED,
}


def resolve_variants(documents: list[ProcessedDocument]) -> list[ProcessedDocument]:
    """Select one output record per work while retaining every physical file.

    Exact canonical keys and DOI equality are deterministic matches. Copies whose
    filenames differ only by representation markers such as ``original`` and
    ``impresso`` are also matched when the year agrees and one side is a secondary
    representation. A fuzzy title match remains restricted to matching year and
    first-author family name.
    """
    if not documents:
        return []

    parents = list(range(len(documents)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left in range(len(documents)):
        for right in range(left + 1, len(documents)):
            if _same_bibliographic_work(documents[left], documents[right]):
                union(left, right)

    groups: defaultdict[int, list[ProcessedDocument]] = defaultdict(list)
    for index, document in enumerate(documents):
        groups[find(index)].append(document)

    resolved: list[ProcessedDocument] = []
    for group in groups.values():
        if len(group) == 1:
            resolved.append(group[0])
            continue

        winner = max(group, key=_score)
        shared_key = winner.canonical_key
        merged_record = merge_records(*(item.bibliographic_record for item in group))
        for source in group:
            item = source.model_copy(deep=True)
            item.canonical_key = shared_key
            item.bibliographic_record = merged_record
            if source.sha256 != winner.sha256:
                item.include_in_output = False
                if WarningCode.DUPLICATE_VARIANT not in item.warnings:
                    item.warnings.append(WarningCode.DUPLICATE_VARIANT)
            resolved.append(item)
    return resolved


def _same_bibliographic_work(
    left: ProcessedDocument,
    right: ProcessedDocument,
) -> bool:
    if left.sha256 == right.sha256:
        return True

    if (
        left.canonical_key
        and right.canonical_key
        and left.canonical_key == right.canonical_key
        and left.canonical_key != "unknown"
    ):
        return True

    left_doi = normalize_doi(left.metadata.doi.value)
    right_doi = normalize_doi(right.metadata.doi.value)
    if left_doi and right_doi and left_doi == right_doi:
        return True

    left_title = normalize(left.metadata.title.value or "")
    right_title = normalize(right.metadata.title.value or "")
    left_year = normalize(left.metadata.year.value or "")
    right_year = normalize(right.metadata.year.value or "")
    if not left_title or not right_title or not left_year or left_year != right_year:
        return False
    if left_title == right_title:
        return True

    if not (left.variant_type in _SECONDARY_VARIANTS or right.variant_type in _SECONDARY_VARIANTS):
        return False

    if left_year == right_year and _normalized_source_stem(left) == _normalized_source_stem(right):
        return True

    left_family = _first_author_family(left)
    right_family = _first_author_family(right)
    if not left_family or left_family != right_family:
        return False

    similarity = difflib.SequenceMatcher(
        None,
        left_title,
        right_title,
    ).ratio()
    return similarity >= 0.96


def _normalized_source_stem(document: ProcessedDocument) -> str:
    stem = normalize(Path(document.source_path).stem)
    stem = re.sub(
        r"\b(pdf|original|impresso|imprimido|browser|site|scaneado|escaneado|ocr)\b",
        " ",
        stem,
    )
    return re.sub(r"\s+", " ", stem).strip()


def _first_author_family(document: ProcessedDocument) -> str:
    if not document.metadata.authors:
        return ""
    return normalize(document.metadata.authors[0].family_name)


def _score(document: ProcessedDocument) -> tuple[int, int, int, int]:
    metadata = document.metadata
    complete = sum(
        bool(value)
        for value in (
            metadata.title.value,
            metadata.year.value,
            metadata.doi.value,
            metadata.journal.value,
            metadata.institution.value,
        )
    )
    return (
        _STATUS_SCORE[document.status],
        _VARIANT_SCORE[document.variant_type],
        complete,
        document.native_page_count,
    )

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from refengine.domain.enums import DocumentType
from refengine.domain.models import ProcessedDocument

MEMORY_SCHEMA_VERSION = 1

# Exact, field-scoped suggestions are intentionally limited to bibliographic
# text fields. Generic numeric replacements (for example 2023 -> 2024) would
# be unsafe to reuse across unrelated works.
MEMORABLE_FIELDS = frozenset(
    {
        "authors",
        "title",
        "journal",
        "place",
        "institution",
        "degree",
        "program",
        "department",
        "publisher",
        "corporate_author",
    }
)

FIELD_LABELS = {
    "authors": "Autores",
    "title": "Título",
    "journal": "Periódico",
    "place": "Local",
    "institution": "Instituição",
    "degree": "Grau e curso",
    "program": "Programa",
    "department": "Departamento",
    "publisher": "Editora",
    "corporate_author": "Autor institucional",
}


@dataclass(frozen=True)
class CorrectionCandidate:
    field_name: str
    field_label: str
    source_value: str
    replacement_value: str
    document_type: DocumentType


def normalize_correction_value(value: str) -> str:
    """Normalize only representation differences, not bibliographic meaning."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("\u00a0", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.casefold()


def correction_candidate(
    *,
    field_name: str,
    source_value: str | None,
    replacement_value: str | None,
    document_type: DocumentType,
) -> CorrectionCandidate | None:
    """Return a reusable correction only when exact reuse is safe enough."""
    if field_name not in MEMORABLE_FIELDS:
        return None

    source = _clean(source_value)
    replacement = _clean(replacement_value)
    if not source or not replacement:
        return None
    if len(source) < 3:
        return None
    if normalize_correction_value(source) == normalize_correction_value(replacement):
        return None

    return CorrectionCandidate(
        field_name=field_name,
        field_label=FIELD_LABELS[field_name],
        source_value=source,
        replacement_value=replacement,
        document_type=document_type,
    )


def current_field_value(document: ProcessedDocument, field_name: str) -> str | None:
    """Read one supported field from a processed document."""
    if field_name == "authors":
        return document.metadata.authors_evidence.value
    evidence = getattr(document.metadata, field_name, None)
    return getattr(evidence, "value", None)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = unicodedata.normalize("NFKC", value).replace("\u00a0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None

from __future__ import annotations

import hashlib
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from refengine.domain.bibliography import (
    BibliographicFieldCandidate,
    CanonicalBibliographicRecord,
    DocumentTypeCandidate,
    SourceFormat,
)
from refengine.domain.enums import DocumentType
from refengine.domain.models import ArticleMetadata, Evidence
from refengine.rules.catalog import load_ufv_2025_catalog
from refengine.services.bibtex import BibTeXEntry, clean_bibtex_text, metadata_from_bibtex
from refengine.services.ris import RisEntry, metadata_from_ris

_SPACE = re.compile(r"\s+")

_METADATA_FIELD_MAP = {
    "title": "title",
    "journal": "periodical_title",
    "place": "place",
    "year": "publication_year",
    "publication_month": "publication_month",
    "volume": "volume",
    "issue": "issue",
    "pages": "article_pages",
    "article_number": "article_number",
    "doi": "doi",
    "url": "url",
    "degree": "work_type",
    "program": "degree_course",
    "publisher": "publisher",
    "corporate_author": "corporate_author",
    "access_date": "access_date",
}

_BIBTEX_FIELD_MAP = {
    "title": "title",
    "subtitle": "subtitle",
    "editor": "other_responsibility",
    "booktitle": "host_title",
    "journal": "periodical_title",
    "journaltitle": "periodical_title",
    "year": "publication_year",
    "date": "publication_date",
    "month": "publication_month",
    "volume": "volume",
    "number": "issue",
    "issue": "issue",
    "pages": "article_pages",
    "chapter": "chapter",
    "eid": "article_number",
    "articleno": "article_number",
    "doi": "doi",
    "url": "url",
    "isbn": "isbn",
    "issn": "issn",
    "publisher": "publisher",
    "address": "place",
    "location": "place",
    "edition": "edition",
    "series": "series",
    "note": "notes",
    "school": "academic_affiliation",
    "type": "work_type",
    "organization": "corporate_author",
    "pagetotal": "pagination",
}

_RIS_FIELD_MAP = {
    "A2": "other_responsibility",
    "A3": "corporate_author",
    "TI": "title",
    "T1": "title",
    "CT": "title",
    "T2": "host_title",
    "JF": "periodical_title",
    "JO": "periodical_title",
    "JA": "periodical_title",
    "PY": "publication_year",
    "Y1": "publication_date",
    "DA": "publication_date",
    "VL": "volume",
    "IS": "issue",
    "DO": "doi",
    "UR": "url",
    "L1": "url",
    "L2": "url",
    "SN": "issn",
    "PB": "publisher",
    "CY": "place",
    "PP": "place",
    "ET": "edition",
    "N1": "notes",
    "M3": "work_type",
    "NV": "pagination",
    "AD": "academic_affiliation",
    "C2": "degree_course",
    "C3": "degree_course",
}


def record_from_metadata(
    metadata: ArticleMetadata,
    source_path: Path,
    *,
    source_format: SourceFormat = SourceFormat.PDF,
    source_record_id: str | None = None,
) -> CanonicalBibliographicRecord:
    """Convert the current PDF/structured metadata object into a candidate ledger."""
    source_file = source_path.name
    record = CanonicalBibliographicRecord(
        record_id=_record_id(source_file, source_record_id),
        source_files=[source_file],
    )

    for sequence, author in enumerate(metadata.authors, start=1):
        _append_candidate(
            record,
            field_id="authors",
            value=author.full_name,
            source_format=source_format,
            source_file=source_file,
            source_record_id=source_record_id,
            method=metadata.authors_evidence.method,
            confidence=metadata.authors_evidence.confidence,
            page_number=metadata.authors_evidence.page_number,
            sequence=sequence,
        )
    if not metadata.authors and metadata.authors_evidence.value:
        _append_candidate(
            record,
            field_id="authors",
            value=metadata.authors_evidence.value,
            source_format=source_format,
            source_file=source_file,
            source_record_id=source_record_id,
            method=metadata.authors_evidence.method,
            confidence=metadata.authors_evidence.confidence,
            page_number=metadata.authors_evidence.page_number,
        )

    for attribute, field_id in _METADATA_FIELD_MAP.items():
        evidence: Evidence = getattr(metadata, attribute)
        if not evidence.value:
            continue
        _append_candidate(
            record,
            field_id=field_id,
            value=evidence.value,
            source_format=source_format,
            source_file=source_file,
            source_record_id=source_record_id,
            method=evidence.method,
            confidence=evidence.confidence,
            page_number=evidence.page_number,
            raw_field_name=attribute,
        )

    _append_academic_affiliation_candidate(
        record,
        metadata=metadata,
        source_format=source_format,
        source_file=source_file,
        source_record_id=source_record_id,
    )
    _append_degree_course_from_work_type(
        record,
        metadata=metadata,
        source_format=source_format,
        source_file=source_file,
        source_record_id=source_record_id,
    )
    _append_physical_extent_candidate(
        record,
        metadata=metadata,
        source_format=source_format,
        source_file=source_file,
        source_record_id=source_record_id,
    )

    type_candidate = _type_candidate_from_document_type(
        metadata.document_type,
        source_format=source_format,
        source_file=source_file,
        source_record_id=source_record_id,
        online=bool(metadata.url.value or metadata.doi.value),
    )
    if type_candidate is not None:
        record.document_type_candidates.append(type_candidate)
    return record


def _append_academic_affiliation_candidate(
    record: CanonicalBibliographicRecord,
    *,
    metadata: ArticleMetadata,
    source_format: SourceFormat,
    source_file: str,
    source_record_id: str | None,
) -> None:
    """Store the complete source-backed academic affiliation when available."""
    institution = metadata.institution.value
    department = metadata.department.value
    if not institution:
        return
    value = f"{department}, {institution}" if department else institution
    confidence = metadata.institution.confidence
    page_number = metadata.institution.page_number
    method = metadata.institution.method
    if department:
        confidence = min(1.0, max(confidence, metadata.department.confidence) + 0.03)
        page_number = metadata.department.page_number or page_number
        method = "academic_affiliation_combined"
    _append_candidate(
        record,
        field_id="academic_affiliation",
        value=value,
        source_format=source_format,
        source_file=source_file,
        source_record_id=source_record_id,
        method=method,
        confidence=confidence,
        page_number=page_number,
        raw_field_name="department+institution" if department else "institution",
    )


def _append_degree_course_from_work_type(
    record: CanonicalBibliographicRecord,
    *,
    metadata: ArticleMetadata,
    source_format: SourceFormat,
    source_file: str,
    source_record_id: str | None,
) -> None:
    """Derive the degree/course only from an explicit academic work-type phrase."""
    value = metadata.degree.value
    if not value:
        return
    match = re.search(
        r"\((?:Doutorado|Mestrado|Especializa(?:ç|c)[aãa]o|Bacharelado|Licenciatura)"
        r"\s+em\s+([^)]+)\)",
        value,
        re.IGNORECASE,
    )
    if not match:
        return
    level = match.group(0).strip("()")
    # The catalog field represents the full degree/course wording used inside
    # parentheses, e.g. "Doutorado em Fitotecnia".
    _append_candidate(
        record,
        field_id="degree_course",
        value=level,
        source_format=source_format,
        source_file=source_file,
        source_record_id=source_record_id,
        method="derived_from_work_type",
        confidence=max(0.0, metadata.degree.confidence - 0.02),
        page_number=metadata.degree.page_number,
        raw_field_name="degree",
    )


def _append_physical_extent_candidate(
    record: CanonicalBibliographicRecord,
    *,
    metadata: ArticleMetadata,
    source_format: SourceFormat,
    source_file: str,
    source_record_id: str | None,
) -> None:
    """Map total extent to the field required by the identified document family."""
    value = metadata.total_pages.value
    if not value:
        return
    if metadata.document_type in {DocumentType.THESIS, DocumentType.DISSERTATION}:
        field_id = "pagination"
        rendered = value
    elif metadata.document_type is DocumentType.BOOK_MANUAL:
        field_id = "physical_description"
        rendered = value if re.search(r"\b(?:p|f|v)\.$", value) else f"{value} p."
    else:
        return
    _append_candidate(
        record,
        field_id=field_id,
        value=rendered,
        source_format=source_format,
        source_file=source_file,
        source_record_id=source_record_id,
        method=metadata.total_pages.method,
        confidence=metadata.total_pages.confidence,
        page_number=metadata.total_pages.page_number,
        raw_field_name="total_pages",
    )


def record_from_bibtex(entry: BibTeXEntry) -> CanonicalBibliographicRecord:
    record = record_from_metadata(
        metadata_from_bibtex(entry),
        entry.source_path,
        source_format=SourceFormat.BIBTEX,
        source_record_id=entry.key,
    )
    _append_structured_fields(
        record,
        fields={name: [value] for name, value in entry.fields.items()},
        mapping=_BIBTEX_FIELD_MAP,
        source_format=SourceFormat.BIBTEX,
        source_file=entry.source_path.name,
        source_record_id=entry.key,
        method="bibtex_raw_field",
    )
    candidate = _type_candidate_from_bibtex(entry)
    if candidate is not None:
        record.document_type_candidates.append(candidate)
    return deduplicate_record(record)


def record_from_ris(entry: RisEntry) -> CanonicalBibliographicRecord:
    record = record_from_metadata(
        metadata_from_ris(entry),
        entry.source_path,
        source_format=SourceFormat.RIS,
        source_record_id=entry.key,
    )
    _append_structured_fields(
        record,
        fields=entry.fields,
        mapping=_RIS_FIELD_MAP,
        source_format=SourceFormat.RIS,
        source_file=entry.source_path.name,
        source_record_id=entry.key,
        method="ris_raw_field",
    )
    start_pages = entry.fields.get("SP", [])
    end_pages = entry.fields.get("EP", [])
    if start_pages:
        page_value = start_pages[0]
        if end_pages and end_pages[0] and end_pages[0] != page_value:
            page_value = f"{page_value}-{end_pages[0]}"
        _append_candidate(
            record,
            field_id="article_pages",
            value=page_value,
            source_format=SourceFormat.RIS,
            source_file=entry.source_path.name,
            source_record_id=entry.key,
            method="ris_page_range",
            confidence=0.99,
            raw_field_name="SP/EP",
        )
    candidate = _type_candidate_from_ris(entry)
    if candidate is not None:
        record.document_type_candidates.append(candidate)
    return deduplicate_record(record)


def merge_records(
    *records: CanonicalBibliographicRecord | None,
) -> CanonicalBibliographicRecord | None:
    available = [record for record in records if record is not None]
    if not available:
        return None
    merged = CanonicalBibliographicRecord(record_id=available[0].record_id)
    for record in available:
        for source_file in record.source_files:
            if source_file not in merged.source_files:
                merged.source_files.append(source_file)
        merged.field_candidates.extend(record.field_candidates)
        merged.document_type_candidates.extend(record.document_type_candidates)
        if record.schema_override is not None:
            merged.schema_override = record.schema_override
            merged.schema_override_source = record.schema_override_source
        for field_id in record.excluded_field_ids:
            if field_id not in merged.excluded_field_ids:
                merged.excluded_field_ids.append(field_id)
    return deduplicate_record(merged)


def deduplicate_record(record: CanonicalBibliographicRecord) -> CanonicalBibliographicRecord:
    updated = record.model_copy(deep=True)
    field_seen: set[tuple[object, ...]] = set()
    unique_fields: list[BibliographicFieldCandidate] = []
    for candidate in updated.field_candidates:
        key = (
            candidate.field_id,
            candidate.normalized_value,
            candidate.source_format,
            candidate.source_file,
            candidate.source_record_id,
            candidate.sequence,
        )
        if key in field_seen:
            continue
        field_seen.add(key)
        unique_fields.append(candidate)
    updated.field_candidates = unique_fields

    type_seen: set[tuple[object, ...]] = set()
    unique_types: list[DocumentTypeCandidate] = []
    for type_candidate in updated.document_type_candidates:
        type_key = (
            type_candidate.schema_id,
            type_candidate.family,
            type_candidate.medium,
            type_candidate.source_format,
            type_candidate.source_file,
            type_candidate.source_record_id,
        )
        if type_key in type_seen:
            continue
        type_seen.add(type_key)
        unique_types.append(type_candidate)
    updated.document_type_candidates = unique_types
    updated.excluded_field_ids = list(dict.fromkeys(updated.excluded_field_ids))

    return updated


def set_reviewed_field(
    record: CanonicalBibliographicRecord,
    *,
    field_id: str,
    values: list[str],
    source_file: str,
    method: str = "api_review",
) -> CanonicalBibliographicRecord:
    """Replace a field with explicit local review candidates while preserving provenance."""
    if field_id not in _known_field_ids():
        raise ValueError(f"Field {field_id!r} is not registered in the UFV catalog")
    updated = record.model_copy(deep=True)
    updated.field_candidates = [
        candidate
        for candidate in updated.field_candidates
        if not (
            candidate.field_id == field_id
            and candidate.method in {"api_review", "review_memory_exact"}
        )
    ]
    updated.excluded_field_ids = [
        current for current in updated.excluded_field_ids if current != field_id
    ]
    for sequence, value in enumerate(values, start=1):
        _append_candidate(
            updated,
            field_id=field_id,
            value=value,
            source_format=SourceFormat.CATALOG,
            source_file=source_file,
            source_record_id=updated.record_id,
            method=method,
            confidence=1.0,
            raw_field_name=field_id,
            sequence=sequence if _field_is_repeatable(field_id) else None,
        )
    return deduplicate_record(updated)


def clear_reviewed_field(
    record: CanonicalBibliographicRecord,
    *,
    field_id: str,
) -> CanonicalBibliographicRecord:
    """Suppress extracted values for one field so validation can expose a true absence."""
    if field_id not in _known_field_ids():
        raise ValueError(f"Field {field_id!r} is not registered in the UFV catalog")
    updated = record.model_copy(deep=True)
    updated.field_candidates = [
        candidate
        for candidate in updated.field_candidates
        if not (
            candidate.field_id == field_id
            and candidate.method in {"api_review", "review_memory_exact"}
        )
    ]
    if field_id not in updated.excluded_field_ids:
        updated.excluded_field_ids.append(field_id)
    return deduplicate_record(updated)


def set_reviewed_schema(
    record: CanonicalBibliographicRecord,
    *,
    schema_id: str | None,
    source: str,
) -> CanonicalBibliographicRecord:
    """Store an explicit local schema decision used before automatic classification."""
    if schema_id is not None:
        known = {schema.id for schema in load_ufv_2025_catalog().schemas}
        if schema_id not in known:
            raise ValueError(f"Unknown UFV schema: {schema_id}")
    updated = record.model_copy(deep=True)
    updated.schema_override = schema_id
    updated.schema_override_source = source if schema_id is not None else None
    return updated


@lru_cache(maxsize=1)
def _repeatable_field_ids() -> frozenset[str]:
    return frozenset(field.id for field in load_ufv_2025_catalog().fields if field.repeatable)


def _field_is_repeatable(field_id: str) -> bool:
    return field_id in _repeatable_field_ids()


def _append_structured_fields(
    record: CanonicalBibliographicRecord,
    *,
    fields: dict[str, list[str]],
    mapping: dict[str, str],
    source_format: SourceFormat,
    source_file: str,
    source_record_id: str,
    method: str,
) -> None:
    for raw_name, values in fields.items():
        field_id = mapping.get(raw_name)
        if field_id is None:
            continue
        for sequence, raw_value in enumerate(values, start=1):
            value = (
                clean_bibtex_text(raw_value) if source_format is SourceFormat.BIBTEX else raw_value
            )
            if not value:
                continue
            _append_candidate(
                record,
                field_id=field_id,
                value=value,
                source_format=source_format,
                source_file=source_file,
                source_record_id=source_record_id,
                method=method,
                confidence=0.99,
                raw_field_name=raw_name,
                sequence=sequence if field_id in {"authors", "host_authors", "notes"} else None,
            )


def _append_candidate(
    record: CanonicalBibliographicRecord,
    *,
    field_id: str,
    value: str,
    source_format: SourceFormat,
    source_file: str,
    source_record_id: str | None,
    method: str,
    confidence: float,
    page_number: int | None = None,
    raw_field_name: str | None = None,
    sequence: int | None = None,
) -> None:
    if field_id not in _known_field_ids():
        raise ValueError(f"Field {field_id!r} is not registered in the UFV catalog")
    cleaned = _clean(value)
    if not cleaned:
        return
    record.field_candidates.append(
        BibliographicFieldCandidate(
            field_id=field_id,
            value=cleaned,
            normalized_value=_normalize(cleaned),
            source_format=source_format,
            source_file=source_file,
            source_record_id=source_record_id,
            method=method,
            confidence=confidence,
            page_number=page_number,
            raw_field_name=raw_field_name,
            sequence=sequence,
        )
    )


@lru_cache(maxsize=1)
def _known_field_ids() -> frozenset[str]:
    return frozenset(field.id for field in load_ufv_2025_catalog().fields)


def _type_candidate_from_document_type(
    document_type: DocumentType,
    *,
    source_format: SourceFormat,
    source_file: str,
    source_record_id: str | None,
    online: bool,
) -> DocumentTypeCandidate | None:
    mapping = {
        DocumentType.JOURNAL_ARTICLE: ("ufv.22" if online else "ufv.21", "periodical_article"),
        DocumentType.THESIS: ("ufv.2", "academic_work"),
        DocumentType.DISSERTATION: ("ufv.2", "academic_work"),
        DocumentType.BOOK_MANUAL: ("ufv.3" if online else "ufv.1", "monograph"),
        DocumentType.WEB_ARTICLE: ("ufv.34", "exclusive_electronic"),
    }
    selected = mapping.get(document_type)
    if selected is None:
        return None
    schema_id, family = selected
    return DocumentTypeCandidate(
        schema_id=schema_id,
        family=family,
        medium="electronic" if online else "print",
        source_format=source_format,
        source_file=source_file,
        source_record_id=source_record_id,
        confidence=0.92,
        reason=f"Existing classifier identified {document_type.value}",
    )


def _type_candidate_from_bibtex(entry: BibTeXEntry) -> DocumentTypeCandidate | None:
    normalized = entry.entry_type.casefold()
    online = bool(entry.fields.get("url") or entry.fields.get("doi"))
    mapping = {
        "article": ("ufv.22" if online else "ufv.21", "periodical_article"),
        "book": ("ufv.3" if online else "ufv.1", "monograph"),
        "manual": ("ufv.3" if online else "ufv.1", "monograph"),
        "inbook": ("ufv.5" if online else "ufv.4", "monograph_part"),
        "incollection": ("ufv.5" if online else "ufv.4", "monograph_part"),
        "inproceedings": ("ufv.13" if online else "ufv.11", "event_part"),
        "conference": ("ufv.13" if online else "ufv.11", "event_part"),
        "proceedings": ("ufv.10" if online else "ufv.8", "event_whole"),
        "phdthesis": ("ufv.2", "academic_work"),
        "mastersthesis": ("ufv.2", "academic_work"),
        "thesis": ("ufv.2", "academic_work"),
        "online": ("ufv.34", "exclusive_electronic"),
        "webpage": ("ufv.34", "exclusive_electronic"),
    }
    selected = mapping.get(normalized)
    if selected is None:
        return None
    schema_id, family = selected
    return DocumentTypeCandidate(
        schema_id=schema_id,
        family=family,
        medium="electronic" if online else "print",
        source_format=SourceFormat.BIBTEX,
        source_file=entry.source_path.name,
        source_record_id=entry.key,
        confidence=0.99,
        reason=f"BibTeX entry type @{entry.entry_type}",
    )


def _type_candidate_from_ris(entry: RisEntry) -> DocumentTypeCandidate | None:
    normalized = entry.entry_type.upper()
    online = bool(entry.fields.get("UR") or entry.fields.get("DO"))
    mapping = {
        "JOUR": ("ufv.22" if online else "ufv.21", "periodical_article"),
        "BOOK": ("ufv.3" if online else "ufv.1", "monograph"),
        "CHAP": ("ufv.5" if online else "ufv.4", "monograph_part"),
        "THES": ("ufv.2", "academic_work"),
        "CONF": ("ufv.13" if online else "ufv.11", "event_part"),
        "CPAPER": ("ufv.13" if online else "ufv.11", "event_part"),
        "ELEC": ("ufv.34", "exclusive_electronic"),
        "WEB": ("ufv.34", "exclusive_electronic"),
        "NEWS": ("ufv.24" if online else "ufv.23", "newspaper_article"),
    }
    selected = mapping.get(normalized)
    if selected is None:
        return None
    schema_id, family = selected
    return DocumentTypeCandidate(
        schema_id=schema_id,
        family=family,
        medium="electronic" if online else "print",
        source_format=SourceFormat.RIS,
        source_file=entry.source_path.name,
        source_record_id=entry.key,
        confidence=0.99,
        reason=f"RIS type TY - {entry.entry_type}",
    )


def _record_id(source_file: str, source_record_id: str | None) -> str:
    payload = f"{source_file}\0{source_record_id or ''}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def _clean(value: str) -> str:
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()

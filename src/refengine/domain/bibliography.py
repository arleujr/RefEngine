from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SourceFormat(StrEnum):
    """Physical or structured source that contributed bibliographic data."""

    PDF = "pdf"
    BIBTEX = "bibtex"
    RIS = "ris"
    CATALOG = "catalog"


class BibliographicFieldCandidate(BaseModel):
    """One auditable candidate value for a field registered in the UFV catalog."""

    field_id: str
    value: str
    normalized_value: str
    source_format: SourceFormat
    source_file: str
    source_record_id: str | None = None
    method: str
    confidence: float = Field(ge=0, le=1)
    page_number: int | None = Field(default=None, ge=1)
    raw_field_name: str | None = None
    sequence: int | None = Field(default=None, ge=1)

    @field_validator("field_id", "value", "normalized_value", "source_file", "method")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Candidate text fields cannot be blank")
        return cleaned


class DocumentTypeCandidate(BaseModel):
    """One source-backed suggestion for the applicable UFV reference schema."""

    schema_id: str | None = None
    family: str
    medium: str | None = None
    source_format: SourceFormat
    source_file: str
    source_record_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    reason: str


class CanonicalBibliographicRecord(BaseModel):
    """Source-neutral candidate ledger used before choosing final field values."""

    record_id: str
    source_files: list[str] = Field(default_factory=list)
    field_candidates: list[BibliographicFieldCandidate] = Field(default_factory=list)
    document_type_candidates: list[DocumentTypeCandidate] = Field(default_factory=list)
    schema_override: str | None = None
    schema_override_source: str | None = None
    excluded_field_ids: list[str] = Field(default_factory=list)

    def candidates_for(self, field_id: str) -> list[BibliographicFieldCandidate]:
        return [candidate for candidate in self.field_candidates if candidate.field_id == field_id]


class ResolutionStatus(StrEnum):
    """Outcome of choosing one canonical value for a catalog field."""

    SELECTED = "selected"
    CONFLICT = "conflict"
    MISSING = "missing"


class ResolutionAlternative(BaseModel):
    """One normalized candidate group considered during field resolution."""

    values: list[str]
    normalized_values: list[str]
    score: float = Field(ge=0)
    sources: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)


class ResolvedBibliographicField(BaseModel):
    """Selected field value plus auditable alternatives."""

    field_id: str
    values: list[str] = Field(default_factory=list)
    status: ResolutionStatus
    confidence: float = Field(ge=0, le=1)
    reason: str
    selected_sources: list[str] = Field(default_factory=list)
    alternatives: list[ResolutionAlternative] = Field(default_factory=list)

    @property
    def value(self) -> str | None:
        return self.values[0] if self.values else None


class ResolvedBibliographicRecord(BaseModel):
    """Catalog-backed result used by validation and reference formatting."""

    record_id: str
    schema_id: str | None = None
    family: str | None = None
    medium: str | None = None
    schema_confidence: float = Field(default=0, ge=0, le=1)
    schema_reason: str = ""
    fields: dict[str, ResolvedBibliographicField] = Field(default_factory=dict)
    missing_required_fields: list[str] = Field(default_factory=list)
    conflicting_fields: list[str] = Field(default_factory=list)
    ready_for_formatting: bool = False

    def field(self, field_id: str) -> ResolvedBibliographicField | None:
        return self.fields.get(field_id)

    def value_for(self, field_id: str) -> str | None:
        resolved = self.field(field_id)
        return resolved.value if resolved is not None else None

    def values_for(self, field_id: str) -> list[str]:
        resolved = self.field(field_id)
        return list(resolved.values) if resolved is not None else []

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from refengine.domain.bibliography import (
    CanonicalBibliographicRecord,
    ResolvedBibliographicRecord,
)
from refengine.domain.enums import (
    DocumentType,
    ErrorCode,
    ExtractionMethod,
    ProcessingStatus,
    QualityIssueCode,
    ReferenceReadiness,
    ReviewState,
    VariantType,
    WarningCode,
)


def empty_evidence(method: str = "not_extracted") -> Evidence:
    return Evidence(value=None, confidence=0, method=method)


class PageText(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    method: ExtractionMethod
    character_count: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    diagnostic_code: str | None = None


class Evidence(BaseModel):
    value: str | None
    confidence: float = Field(ge=0, le=1)
    page_number: int | None = Field(default=None, ge=1)
    excerpt: str | None = None
    method: str


class Author(BaseModel):
    full_name: str
    family_name: str
    given_names: str


class ArticleMetadata(BaseModel):
    title: Evidence
    authors: list[Author]
    authors_evidence: Evidence
    journal: Evidence
    place: Evidence
    year: Evidence
    publication_month: Evidence
    volume: Evidence
    issue: Evidence
    pages: Evidence
    article_number: Evidence
    doi: Evidence
    url: Evidence
    extractor: str
    document_type: DocumentType = DocumentType.JOURNAL_ARTICLE
    institution: Evidence = Field(default_factory=lambda: empty_evidence("not_extracted"))
    degree: Evidence = Field(default_factory=lambda: empty_evidence("not_extracted"))
    program: Evidence = Field(default_factory=lambda: empty_evidence("not_extracted"))
    publisher: Evidence = Field(default_factory=lambda: empty_evidence("not_extracted"))
    total_pages: Evidence = Field(default_factory=lambda: empty_evidence("not_extracted"))
    corporate_author: Evidence = Field(default_factory=lambda: empty_evidence("not_extracted"))
    department: Evidence = Field(default_factory=lambda: empty_evidence("not_extracted"))
    access_date: Evidence = Field(default_factory=lambda: empty_evidence("not_provided"))


class CorrectionSuggestion(BaseModel):
    field_name: str
    field_label: str
    source_value: str
    replacement_value: str
    confirmation_count: int = Field(default=1, ge=1)


class ProcessingIncident(BaseModel):
    """Sanitized diagnostic attached to a recoverable source failure."""

    incident_id: str
    phase: str
    exception_type: str
    message: str
    recoverable: bool = True


class ProcessedDocument(BaseModel):
    source_path: Path
    source_relative_paths: list[str] = Field(default_factory=list)
    sha256: str
    pages: list[PageText]
    metadata: ArticleMetadata
    status: ProcessingStatus
    errors: list[ErrorCode] = Field(default_factory=list)
    warnings: list[WarningCode] = Field(default_factory=list)
    generated_reference: str | None = None
    variant_type: VariantType = VariantType.UNKNOWN
    canonical_key: str | None = None
    review_state: ReviewState = ReviewState.PENDING
    include_in_output: bool = True
    correction_suggestions: list[CorrectionSuggestion] = Field(default_factory=list)
    incident: ProcessingIncident | None = None
    bibliographic_record: CanonicalBibliographicRecord | None = None
    resolved_bibliography: ResolvedBibliographicRecord | None = None

    @property
    def native_page_count(self) -> int:
        return sum(page.method is ExtractionMethod.NATIVE for page in self.pages)

    @property
    def ocr_page_count(self) -> int:
        return sum(page.method is ExtractionMethod.OCR for page in self.pages)

    @property
    def skipped_page_count(self) -> int:
        return sum(page.method is ExtractionMethod.SKIPPED for page in self.pages)

    @property
    def unavailable_page_count(self) -> int:
        return sum(page.method is ExtractionMethod.UNAVAILABLE for page in self.pages)


class ReferenceQualityAssessment(BaseModel):
    """Quality-gate decision for one physical document."""

    source_file: str
    sha256: str
    canonical_key: str | None = None
    variant_type: VariantType
    readiness: ReferenceReadiness
    issues: list[QualityIssueCode] = Field(default_factory=list)
    review_state: ReviewState
    reference_generated: bool
    generated_reference: str | None = None

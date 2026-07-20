from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from refengine.domain.enums import ApiRunStatus, ReferenceReadiness, ReviewState


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    local_only: bool = True
    input_mode: Literal["folder"] = "folder"
    input_directory: str
    api_database: str
    frontend_available: bool


class InputFileResponse(BaseModel):
    relative_path: str
    source_type: str
    size_bytes: int
    sha256: str


class InputInventoryResponse(BaseModel):
    input_directory: str
    files: list[InputFileResponse]
    fingerprint: str
    total_bytes: int
    counts: dict[str, int]


class InputFileChangeResponse(BaseModel):
    relative_path: str
    change: Literal["added", "removed", "modified"]


class RunInputStatusResponse(BaseModel):
    run_id: str
    changed: bool
    expected_fingerprint: str
    current_fingerprint: str
    checked_at: str
    changes: list[InputFileChangeResponse]


class RunCreateRequest(BaseModel):
    access_date: date | None = None
    recursive: bool = True
    ocr_page_limit: int = Field(default=2, ge=0, le=20)
    first_author_et_al: bool = False
    cache: bool = True


class RunResponse(BaseModel):
    run_id: str
    status: ApiRunStatus
    created_at: str
    started_at: str | None
    finished_at: str | None
    published_at: str | None
    access_date: str
    physical_sources: int
    selected_works: int
    ready_references: int
    review_required_references: int
    blocked_references: int
    excluded_works: int
    revision: int
    error_message: str | None


class WorkSummaryResponse(BaseModel):
    work_id: str
    source_file: str
    source_files: list[str]
    source_relative_path: str
    source_relative_paths: list[str]
    schema_id: str | None
    schema_label: str | None
    schema_family: str | None
    manual_section: str | None
    title: str | None
    readiness: ReferenceReadiness
    review_state: ReviewState
    included: bool
    reference: str | None
    issues: list[str]
    source_types: list[str]


class AttentionItemResponse(BaseModel):
    code: str
    severity: Literal["warning", "error"]
    message: str
    field_id: str | None = None
    field_label: str | None = None


class CandidateResponse(BaseModel):
    values: list[str]
    score: float
    sources: list[str]
    methods: list[str]


class FieldDetailResponse(BaseModel):
    field_id: str
    label: str
    repeatable: bool
    value_type: str
    requirement: Literal["required", "conditional"]
    selected_values: list[str]
    resolution_status: str
    confidence: float
    reason: str
    selected_sources: list[str]
    alternatives: list[CandidateResponse]
    rule_summary: str
    rule_details: str


class CatalogFieldResponse(BaseModel):
    id: str
    label: str
    repeatable: bool
    value_type: str


class SchemaResponse(BaseModel):
    id: str
    section: str
    printed_page: int
    label: str
    family: str
    medium: str
    required_fields: list[str]
    conditional_fields: list[str]
    ordered_fields: list[str]
    pattern: str
    notes: list[str]


class WorkDetailResponse(WorkSummaryResponse):
    schema_definition: SchemaResponse | None = Field(alias="schema", serialization_alias="schema")
    fields: list[FieldDetailResponse]
    missing_required_fields: list[str]
    conflicting_fields: list[str]
    can_approve: bool
    correction_suggestions: list[dict[str, object]]
    attention_items: list[AttentionItemResponse]
    processing_error: str | None


ReviewFieldValue = str | list[str] | None


class WorkPatchRequest(BaseModel):
    schema_id: str | None = None
    fields: dict[str, ReviewFieldValue] = Field(default_factory=dict)
    included: bool | None = None


class WorkActionResponse(BaseModel):
    run: RunResponse
    work: WorkDetailResponse


class PublishResponse(BaseModel):
    run: RunResponse
    references: int
    exports: dict[str, str]


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)

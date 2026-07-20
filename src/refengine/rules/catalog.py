from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class ManualSource(BaseModel):
    title: str
    institution: str
    year: int
    norms: list[str]
    manual_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    covered_printed_pages: tuple[int, int]
    covered_sections: list[str]


class OutputPolicy(BaseModel):
    ordering: str
    access_date: str
    network_access: bool
    typographic_emphasis: str
    line_spacing: str
    alignment: str
    blank_line_between_references: bool
    doi_url_deduplication: bool
    distinct_url_with_doi: bool


class CatalogField(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    repeatable: bool
    value_type: str


class SourceRule(BaseModel):
    id: str = Field(pattern=r"^[A-Z]{3}-\d{3}$")
    category: str
    statement: str
    section: str
    page: int = Field(ge=54, le=106)


class FieldCondition(BaseModel):
    description: str
    any_of: list[str] = Field(default_factory=list)
    when_field_present: str | None = None
    then_required: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_shape(self) -> FieldCondition:
        has_any = bool(self.any_of)
        has_when = self.when_field_present is not None
        if has_any == has_when:
            raise ValueError("A condition must define exactly one of any_of or when_field_present")
        if has_when and not self.then_required:
            raise ValueError("when_field_present requires then_required")
        return self


class ReferenceSchema(BaseModel):
    id: str = Field(pattern=r"^ufv\.\d+(?:_\d+)?$")
    section: str = Field(pattern=r"^5\.12\.\d+(?:\.\d+)?$")
    main_section: int = Field(ge=1, le=34)
    printed_page: int = Field(ge=80, le=106)
    label: str
    family: str
    medium: str
    required_fields: list[str]
    conditional_fields: list[str] = Field(default_factory=list)
    ordered_fields: list[str]
    pattern: str
    conditions: list[FieldCondition] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_fields_are_unique(self) -> ReferenceSchema:
        if len(self.required_fields) != len(set(self.required_fields)):
            raise ValueError(f"Duplicate required field in {self.section}")
        if len(self.conditional_fields) != len(set(self.conditional_fields)):
            raise ValueError(f"Duplicate conditional field in {self.section}")
        overlap = set(self.required_fields) & set(self.conditional_fields)
        if overlap:
            raise ValueError(
                f"Fields cannot be required and conditional in {self.section}: {overlap}"
            )
        if len(self.ordered_fields) != len(set(self.ordered_fields)):
            raise ValueError(f"Duplicate ordered field in {self.section}")
        declared = set(self.required_fields) | set(self.conditional_fields)
        if set(self.ordered_fields) != declared:
            missing = declared - set(self.ordered_fields)
            extra = set(self.ordered_fields) - declared
            raise ValueError(
                f"Ordered fields must match declared fields in {self.section}; missing={missing}, extra={extra}"
            )
        expected_main = int(self.section.removeprefix("5.12.").split(".")[0])
        if self.main_section != expected_main:
            raise ValueError(f"Incorrect main_section for {self.section}")
        return self


class NormativeCatalog(BaseModel):
    catalog_id: str
    catalog_version: str
    scope: str
    source: ManualSource
    output_policy: OutputPolicy
    fields: list[CatalogField]
    general_rules: list[SourceRule]
    schemas: list[ReferenceSchema]

    @model_validator(mode="after")
    def check_catalog_integrity(self) -> NormativeCatalog:
        field_ids = [field.id for field in self.fields]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("Catalog field IDs must be unique")
        known_fields = set(field_ids)

        schema_ids = [schema.id for schema in self.schemas]
        sections = [schema.section for schema in self.schemas]
        if len(schema_ids) != len(set(schema_ids)):
            raise ValueError("Schema IDs must be unique")
        if len(sections) != len(set(sections)):
            raise ValueError("Schema sections must be unique")

        rule_ids = [rule.id for rule in self.general_rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("General rule IDs must be unique")

        for schema in self.schemas:
            referenced = set(schema.required_fields) | set(schema.conditional_fields)
            for condition in schema.conditions:
                referenced.update(condition.any_of)
                if condition.when_field_present is not None:
                    referenced.add(condition.when_field_present)
                referenced.update(condition.then_required)
            unknown = referenced - known_fields
            if unknown:
                raise ValueError(f"Unknown fields in {schema.section}: {sorted(unknown)}")

        concrete_sections = expected_concrete_sections()
        actual_sections = set(sections)
        if actual_sections != concrete_sections:
            missing = sorted(concrete_sections - actual_sections, key=section_sort_key)
            extra = sorted(actual_sections - concrete_sections, key=section_sort_key)
            raise ValueError(f"Manual coverage mismatch; missing={missing}, extra={extra}")

        if {schema.main_section for schema in self.schemas} != set(range(1, 35)):
            raise ValueError("Every main section from 5.12.1 to 5.12.34 must be represented")

        if self.output_policy.network_access:
            raise ValueError("The frozen RefEngine scope requires local-only processing")
        return self


class CatalogValidationReport(BaseModel):
    catalog_id: str
    catalog_version: str
    fields: int
    general_rules: int
    renderable_schemas: int
    main_sections: int
    electronic_schemas: int
    local_only: bool
    valid: bool
    errors: list[str] = Field(default_factory=list)


def section_sort_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".")[2:])


def expected_concrete_sections() -> set[str]:
    sections = {f"5.12.{number}" for number in range(1, 16)}
    sections.update(f"5.12.16.{number}" for number in range(1, 8))
    sections.update(f"5.12.{number}" for number in range(17, 25))
    sections.update({"5.12.25.1", "5.12.25.2"})
    sections.update({"5.12.26", "5.12.26.1", "5.12.26.2"})
    sections.update(f"5.12.{number}" for number in range(27, 35))
    return sections


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "ufv_2025_reference_catalog.yaml"


def load_ufv_2025_catalog(path: Path | None = None) -> NormativeCatalog:
    catalog_path = path or default_catalog_path()
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid catalog root in {catalog_path}")
    return NormativeCatalog.model_validate(payload)


def validate_catalog(path: Path | None = None) -> CatalogValidationReport:
    try:
        catalog = load_ufv_2025_catalog(path)
    except Exception as exc:  # validation command must return a compact report
        return CatalogValidationReport(
            catalog_id="unknown",
            catalog_version="unknown",
            fields=0,
            general_rules=0,
            renderable_schemas=0,
            main_sections=0,
            electronic_schemas=0,
            local_only=True,
            valid=False,
            errors=[f"{type(exc).__name__}: {exc}"],
        )

    return CatalogValidationReport(
        catalog_id=catalog.catalog_id,
        catalog_version=catalog.catalog_version,
        fields=len(catalog.fields),
        general_rules=len(catalog.general_rules),
        renderable_schemas=len(catalog.schemas),
        main_sections=len({schema.main_section for schema in catalog.schemas}),
        electronic_schemas=sum(schema.medium == "electronic" for schema in catalog.schemas),
        local_only=not catalog.output_policy.network_access,
        valid=True,
    )

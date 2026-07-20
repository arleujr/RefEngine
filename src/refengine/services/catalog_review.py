from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from refengine.rules.catalog import (
    CatalogField,
    NormativeCatalog,
    ReferenceSchema,
    SourceRule,
    load_ufv_2025_catalog,
)

_REPEATABLE_SEPARATOR = "\n"

_FIELD_RULE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "authors": ("authorship",),
    "host_authors": ("authorship",),
    "advisor": ("authorship",),
    "inventors": ("authorship",),
    "corporate_author": ("corporate_author",),
    "jurisdiction": ("corporate_author",),
    "entity_heading": ("corporate_author",),
    "event_name": ("event_entry",),
    "event_number": ("event_entry",),
    "event_year": ("event_entry", "date"),
    "event_place": ("event_entry", "place"),
    "title": ("title",),
    "subtitle": ("title",),
    "part_title": ("title",),
    "part_subtitle": ("title",),
    "host_title": ("title",),
    "host_subtitle": ("title",),
    "periodical_title": ("title",),
    "newspaper_title": ("title",),
    "service_title": ("title",),
    "edition": ("edition",),
    "host_edition": ("edition",),
    "version": ("edition",),
    "place": ("place",),
    "academic_place": ("place",),
    "publisher": ("publisher",),
    "publication_year": ("date",),
    "publication_date": ("date",),
    "publication_month": ("date",),
    "presentation_year": ("date",),
    "defense_year": ("date",),
    "start_year": ("date",),
    "end_year": ("date",),
    "newspaper_date": ("date",),
    "physical_description": ("physical_description",),
    "pagination": ("physical_description",),
    "part_pages": ("physical_description",),
    "article_pages": ("physical_description",),
    "url": ("online", "electronic"),
    "access_date": ("online",),
    "access_time": ("online",),
    "support": ("electronic",),
    "media_support": ("electronic",),
    "electronic_description": ("electronic",),
}


@lru_cache(maxsize=1)
def catalog() -> NormativeCatalog:
    return load_ufv_2025_catalog()


@lru_cache(maxsize=1)
def field_map() -> dict[str, CatalogField]:
    return {field.id: field for field in catalog().fields}


@lru_cache(maxsize=1)
def schema_map() -> dict[str, ReferenceSchema]:
    return {schema.id: schema for schema in catalog().schemas}


@lru_cache(maxsize=1)
def rule_map() -> dict[str, SourceRule]:
    return {rule.id: rule for rule in catalog().general_rules}


def field_label(field_id: str) -> str:
    field = field_map().get(field_id)
    return field.label if field is not None else field_id


def field_is_repeatable(field_id: str) -> bool:
    field = field_map().get(field_id)
    return bool(field and field.repeatable)


def schema_for(schema_id: str | None) -> ReferenceSchema | None:
    return schema_map().get(schema_id or "")


def requirement_for(schema: ReferenceSchema, field_id: str) -> Literal["required", "conditional"]:
    if field_id in schema.required_fields:
        return "required"
    return "conditional"


def condition_texts(schema: ReferenceSchema, field_id: str) -> list[str]:
    texts: list[str] = []
    for condition in schema.conditions:
        referenced = set(condition.any_of)
        if condition.when_field_present is not None:
            referenced.add(condition.when_field_present)
        referenced.update(condition.then_required)
        if field_id in referenced:
            texts.append(condition.description)
    return texts


def rule_ids_for(field_id: str) -> list[str]:
    categories = _FIELD_RULE_CATEGORIES.get(field_id, ())
    selected = [rule.id for rule in catalog().general_rules if rule.category in categories]
    if "GEN-001" not in selected:
        selected.insert(0, "GEN-001")
    return selected


def rule_summary(schema: ReferenceSchema, field_id: str) -> str:
    requirement = "obrigatório" if field_id in schema.required_fields else "condicional"
    condition_suffix = ""
    conditions = condition_texts(schema, field_id)
    if conditions:
        condition_suffix = " " + " ".join(conditions)
    return (
        f"{schema.section}, p. {schema.printed_page}: campo {requirement} do modelo "
        f"{schema.label}.{condition_suffix}"
    ).strip()


def rule_details(field_id: str) -> str:
    rules = [rule_map()[rule_id] for rule_id in rule_ids_for(field_id)]
    return " | ".join(
        f"{rule.id} ({rule.section}, p. {rule.page}): {rule.statement}" for rule in rules
    )


def serialize_values(values: list[str]) -> str:
    return _REPEATABLE_SEPARATOR.join(value.strip() for value in values if value.strip())


def parse_reviewed_values(value: object, *, repeatable: bool) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    if not repeatable:
        return [text]
    # New lines are the official separator; semicolons remain accepted for convenience.
    parts = re.split(r"(?:\r?\n)+|\s*;\s*", text)
    return [part.strip() for part in parts if part.strip()]

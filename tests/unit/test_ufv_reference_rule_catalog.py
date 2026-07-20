from pathlib import Path

import yaml

from refengine.rules.catalog import (
    expected_concrete_sections,
    load_ufv_2025_catalog,
    validate_catalog,
)
from refengine.services.reference_formatter import ReferenceFormatter


def test_catalog_covers_every_concrete_manual_model() -> None:
    catalog = load_ufv_2025_catalog()

    assert len(catalog.schemas) == 43
    assert {schema.section for schema in catalog.schemas} == expected_concrete_sections()
    assert {schema.main_section for schema in catalog.schemas} == set(range(1, 35))


def test_formatter_contract_matches_yaml_catalog_exactly() -> None:
    catalog = load_ufv_2025_catalog()

    assert ReferenceFormatter.supported_schema_ids() == frozenset(
        schema.id for schema in catalog.schemas
    )


def test_catalog_is_local_and_uses_processing_date() -> None:
    catalog = load_ufv_2025_catalog()

    assert catalog.output_policy.network_access is False
    assert catalog.output_policy.access_date == "processing_date"
    assert catalog.output_policy.ordering == "alphabetical"


def test_every_schema_uses_only_registered_fields() -> None:
    catalog = load_ufv_2025_catalog()
    fields = {field.id for field in catalog.fields}

    for schema in catalog.schemas:
        assert set(schema.required_fields) <= fields
        assert set(schema.conditional_fields) <= fields
        assert set(schema.ordered_fields) == (
            set(schema.required_fields) | set(schema.conditional_fields)
        )


def test_online_reference_requires_access_date_when_url_exists() -> None:
    catalog = load_ufv_2025_catalog()
    online_article = next(schema for schema in catalog.schemas if schema.section == "5.12.22")

    assert "url" in online_article.conditional_fields
    assert "access_date" in online_article.conditional_fields
    assert any(
        condition.when_field_present == "url" and condition.then_required == ["access_date"]
        for condition in online_article.conditions
    )


def test_article_and_academic_work_targets_are_explicit() -> None:
    catalog = load_ufv_2025_catalog()
    article = next(schema for schema in catalog.schemas if schema.section == "5.12.22")
    academic = next(schema for schema in catalog.schemas if schema.section == "5.12.2")

    assert {"authors", "title", "periodical_title", "publication_year"} <= set(
        article.required_fields
    )
    assert {
        "authors",
        "title",
        "presentation_year",
        "work_type",
        "degree_course",
        "academic_affiliation",
        "academic_place",
        "defense_year",
    } <= set(academic.required_fields)


def test_broken_catalog_is_rejected(tmp_path: Path) -> None:
    catalog = load_ufv_2025_catalog()
    payload = catalog.model_dump(mode="json")
    payload["schemas"] = payload["schemas"][:-1]
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    report = validate_catalog(broken)

    assert report.valid is False
    assert report.errors


def test_rules_check_report_is_complete() -> None:
    report = validate_catalog()

    assert report.valid is True
    assert report.main_sections == 34
    assert report.renderable_schemas == 43
    assert report.fields >= 100
    assert report.general_rules >= 30

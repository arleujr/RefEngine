from __future__ import annotations

from refengine.domain.enums import DocumentType
from refengine.services.correction_memory import (
    correction_candidate,
    normalize_correction_value,
)


def test_normalization_preserves_meaning_and_removes_representation_noise() -> None:
    assert normalize_correction_value("  Tuneo\u00a0Sedyiama  ") == "tuneo sedyiama"


def test_numeric_fields_are_not_reused_as_global_corrections() -> None:
    candidate = correction_candidate(
        field_name="year",
        source_value="2023",
        replacement_value="2024",
        document_type=DocumentType.JOURNAL_ARTICLE,
    )

    assert candidate is None


def test_approved_text_correction_can_be_memorized() -> None:
    candidate = correction_candidate(
        field_name="authors",
        source_value="Tuneo Sedyiama",
        replacement_value="Tuneo Sediyama",
        document_type=DocumentType.JOURNAL_ARTICLE,
    )

    assert candidate is not None
    assert candidate.field_label == "Autores"
    assert candidate.replacement_value == "Tuneo Sediyama"


def test_case_only_change_is_not_reused_automatically() -> None:
    candidate = correction_candidate(
        field_name="title",
        source_value="Cultivadas no brasil",
        replacement_value="Cultivadas no Brasil",
        document_type=DocumentType.DISSERTATION,
    )

    assert candidate is None

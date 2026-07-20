from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from refengine.domain.bibliography import (
    BibliographicFieldCandidate,
    CanonicalBibliographicRecord,
    ResolutionAlternative,
    ResolutionStatus,
    ResolvedBibliographicField,
    ResolvedBibliographicRecord,
    SourceFormat,
)
from refengine.rules.catalog import NormativeCatalog, ReferenceSchema, load_ufv_2025_catalog

_SOURCE_BONUS = {
    SourceFormat.PDF: 0.00,
    SourceFormat.BIBTEX: 0.06,
    SourceFormat.RIS: 0.06,
    SourceFormat.CATALOG: 0.00,
}
_METHOD_BONUS = {
    "api_review": 0.30,
    "review_memory_exact": 0.28,
    "bibtex_raw_field": 0.10,
    "ris_raw_field": 0.10,
    "bibtex_metadata": 0.08,
    "ris_metadata": 0.08,
    "doi_regex": 0.08,
    "web_print_profile": 0.05,
    "publisher_profile": 0.05,
}


@dataclass(frozen=True)
class _GroupedAlternative:
    values: tuple[str, ...]
    normalized_values: tuple[str, ...]
    score: float
    candidates: tuple[BibliographicFieldCandidate, ...]


class CandidateResolver:
    """Resolve source candidates field by field under the UFV catalog.

    The resolver never deletes provenance. It selects one value group for formatting,
    preserves alternatives, and marks close high-confidence disagreements for review.
    """

    def __init__(self, catalog: NormativeCatalog | None = None) -> None:
        self._catalog = catalog or load_ufv_2025_catalog()
        self._schemas = {schema.id: schema for schema in self._catalog.schemas}
        self._repeatable = {field.id: field.repeatable for field in self._catalog.fields}

    def resolve(
        self,
        record: CanonicalBibliographicRecord,
        *,
        access_date: date,
    ) -> ResolvedBibliographicRecord:
        schema, schema_confidence, schema_reason = self._resolve_schema(record)
        resolved = ResolvedBibliographicRecord(
            record_id=record.record_id,
            schema_id=schema.id if schema is not None else None,
            family=schema.family if schema is not None else None,
            medium=schema.medium if schema is not None else None,
            schema_confidence=schema_confidence,
            schema_reason=schema_reason,
        )
        if schema is None:
            resolved.ready_for_formatting = False
            return resolved

        relevant_fields = list(schema.ordered_fields)
        for field_id in relevant_fields:
            candidates = self._candidates_with_aliases(record, schema, field_id)
            if field_id == "access_date" and not candidates:
                candidates = [
                    BibliographicFieldCandidate(
                        field_id="access_date",
                        value=access_date.isoformat(),
                        normalized_value=access_date.isoformat(),
                        source_format=SourceFormat.CATALOG,
                        source_file="<execution>",
                        method="execution_date",
                        confidence=1.0,
                    )
                ]
            elif field_id == "place" and not candidates:
                candidates = [self._unknown_place_candidate()]
            resolved.fields[field_id] = self._resolve_field(field_id, candidates)

        self._cohere_doi_and_url(record, resolved)
        missing = self._missing_required(schema, resolved)
        conflicts = [
            field_id
            for field_id, field in resolved.fields.items()
            if field.status is ResolutionStatus.CONFLICT
        ]
        resolved.missing_required_fields = missing
        resolved.conflicting_fields = conflicts
        resolved.ready_for_formatting = not missing
        return resolved

    @staticmethod
    def _unknown_place_candidate() -> BibliographicFieldCandidate:
        return BibliographicFieldCandidate(
            field_id="place",
            value="[S. l.]",
            normalized_value="[s. l.]",
            source_format=SourceFormat.CATALOG,
            source_file="<ufv-2025:5.4.3>",
            method="normative_unknown_place",
            confidence=1.0,
        )

    def _cohere_doi_and_url(
        self,
        record: CanonicalBibliographicRecord,
        resolved: ResolvedBibliographicRecord,
    ) -> None:
        """Keep the selected DOI and DOI-based availability URL internally consistent."""
        doi_field = resolved.fields.get("doi")
        url_field = resolved.fields.get("url")
        if doi_field is None or not doi_field.value or url_field is None:
            return

        selected_doi = self._normalize_doi(doi_field.value)
        if not selected_doi:
            return

        matching_candidates = [
            candidate
            for candidate in record.candidates_for("url")
            if self._doi_from_url(candidate.value) == selected_doi
        ]
        if matching_candidates:
            coherent = self._resolve_field("url", matching_candidates)
            coherent.alternatives = url_field.alternatives
            if url_field.status is ResolutionStatus.CONFLICT:
                coherent.status = ResolutionStatus.CONFLICT
                coherent.reason = (
                    "URL draft aligned with the selected DOI; high-confidence source URLs disagree."
                )
            else:
                coherent.reason = "URL selected because it matches the selected DOI."
            resolved.fields["url"] = coherent
            return

        current_url = url_field.value
        current_url_doi = self._doi_from_url(current_url) if current_url else None
        if current_url_doi and current_url_doi != selected_doi:
            derived_url = f"https://doi.org/{selected_doi}"
            derived_alternative = ResolutionAlternative(
                values=[derived_url],
                normalized_values=[derived_url.casefold()],
                score=round(doi_field.confidence, 4),
                sources=list(doi_field.selected_sources),
                methods=["doi_url_from_selected_doi"],
            )
            alternatives = list(url_field.alternatives)
            if not any(item.values == [derived_url] for item in alternatives):
                alternatives.insert(0, derived_alternative)
            resolved.fields["url"] = ResolvedBibliographicField(
                field_id="url",
                values=[derived_url],
                status=(
                    ResolutionStatus.CONFLICT
                    if url_field.status is ResolutionStatus.CONFLICT
                    else ResolutionStatus.SELECTED
                ),
                confidence=doi_field.confidence,
                reason=(
                    "DOI-based URL derived locally from the selected DOI to avoid a mismatched identifier."
                ),
                selected_sources=list(doi_field.selected_sources),
                alternatives=alternatives,
            )

    @staticmethod
    def _normalize_doi(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = re.sub(
            r"^(?:doi\s*:\s*)?https?://(?:dx\.)?doi\.org/",
            "",
            value.strip(),
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^doi\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip().rstrip(".;, ").casefold()
        return cleaned or None

    @classmethod
    def _doi_from_url(cls, value: str | None) -> str | None:
        if not value or not re.match(
            r"^https?://(?:dx\.)?doi\.org/",
            value.strip(),
            flags=re.IGNORECASE,
        ):
            return None
        return cls._normalize_doi(value)

    def _resolve_schema(
        self,
        record: CanonicalBibliographicRecord,
    ) -> tuple[ReferenceSchema | None, float, str]:
        if record.schema_override is not None:
            schema = self._schemas.get(record.schema_override)
            if schema is None:
                return None, 0.0, f"Unknown reviewed schema: {record.schema_override}."
            source = record.schema_override_source or "local review"
            return schema, 1.0, f"Explicit local schema review from {source}."

        grouped: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for candidate in record.document_type_candidates:
            if candidate.schema_id is None or candidate.schema_id not in self._schemas:
                continue
            score = min(
                1.0,
                candidate.confidence + _SOURCE_BONUS[candidate.source_format],
            )
            grouped[candidate.schema_id].append((score, candidate.reason))
        if not grouped:
            return None, 0.0, "No source identified a UFV reference schema."

        ranked: list[tuple[float, str, str]] = []
        for schema_id, values in grouped.items():
            scores = [score for score, _ in values]
            support_bonus = min(0.08, 0.025 * (len(values) - 1))
            aggregate = min(1.0, max(scores) + support_bonus)
            reasons = "; ".join(dict.fromkeys(reason for _, reason in values))
            ranked.append((aggregate, schema_id, reasons))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        score, schema_id, reasons = ranked[0]
        if len(ranked) > 1 and ranked[1][0] >= 0.90 and score - ranked[1][0] <= 0.04:
            reasons += f"; close alternative schema={ranked[1][1]} score={ranked[1][0]:.2f}"
        return self._schemas[schema_id], min(score, 1.0), reasons

    def _resolve_field(
        self,
        field_id: str,
        candidates: list[BibliographicFieldCandidate],
    ) -> ResolvedBibliographicField:
        if not candidates:
            return ResolvedBibliographicField(
                field_id=field_id,
                values=[],
                status=ResolutionStatus.MISSING,
                confidence=0.0,
                reason="No candidate value was found.",
            )

        alternatives = (
            self._repeatable_alternatives(candidates)
            if self._repeatable.get(field_id, False)
            else self._scalar_alternatives(candidates)
        )
        alternatives.sort(
            key=lambda item: (item.score, len(item.values), item.normalized_values),
            reverse=True,
        )
        human_alternatives = [
            item
            for item in alternatives
            if any(
                candidate.method in {"api_review", "review_memory_exact"}
                for candidate in item.candidates
            )
        ]
        if human_alternatives:
            selected = max(
                human_alternatives,
                key=lambda item: (item.score, len(item.values), item.normalized_values),
            )
            alternatives = [selected, *[item for item in alternatives if item is not selected]]
        else:
            selected = alternatives[0]
        status = ResolutionStatus.SELECTED
        reason = "Highest source-backed score."
        selected_is_human = any(
            candidate.method in {"api_review", "review_memory_exact"}
            for candidate in selected.candidates
        )
        if len(alternatives) > 1 and not selected_is_human:
            second = alternatives[1]
            if (
                second.normalized_values != selected.normalized_values
                and selected.score >= 0.84
                and second.score >= 0.84
                and selected.score - second.score <= 0.12
            ):
                status = ResolutionStatus.CONFLICT
                reason = "High-confidence sources disagree; the top value is a draft selection."
        elif selected_is_human:
            reason = "Explicit local human review overrides automatic candidates."

        selected_sources = sorted(
            {self._source_label(candidate) for candidate in selected.candidates}
        )
        return ResolvedBibliographicField(
            field_id=field_id,
            values=list(selected.values),
            status=status,
            confidence=min(selected.score, 1.0),
            reason=reason,
            selected_sources=selected_sources,
            alternatives=[
                ResolutionAlternative(
                    values=list(item.values),
                    normalized_values=list(item.normalized_values),
                    score=round(item.score, 4),
                    sources=sorted(
                        {self._source_label(candidate) for candidate in item.candidates}
                    ),
                    methods=sorted({candidate.method for candidate in item.candidates}),
                )
                for item in alternatives
            ],
        )

    def _scalar_alternatives(
        self,
        candidates: list[BibliographicFieldCandidate],
    ) -> list[_GroupedAlternative]:
        groups: dict[str, list[BibliographicFieldCandidate]] = defaultdict(list)
        for candidate in candidates:
            groups[candidate.normalized_value].append(candidate)
        alternatives: list[_GroupedAlternative] = []
        for normalized, group in groups.items():
            best = max(group, key=self._candidate_score)
            score = self._aggregate_score(group)
            alternatives.append(
                _GroupedAlternative(
                    values=(best.value,),
                    normalized_values=(normalized,),
                    score=score,
                    candidates=tuple(group),
                )
            )
        return alternatives

    def _repeatable_alternatives(
        self,
        candidates: list[BibliographicFieldCandidate],
    ) -> list[_GroupedAlternative]:
        by_provenance: dict[tuple[object, ...], list[BibliographicFieldCandidate]] = defaultdict(
            list
        )
        for candidate in candidates:
            key = (
                candidate.source_format,
                candidate.source_file,
                candidate.source_record_id,
                candidate.method,
            )
            by_provenance[key].append(candidate)

        by_value_tuple: dict[tuple[str, ...], list[BibliographicFieldCandidate]] = defaultdict(list)
        representative_values: dict[tuple[str, ...], tuple[str, ...]] = {}
        for group in by_provenance.values():
            ordered = sorted(group, key=lambda item: (item.sequence or 10_000, item.value))
            normalized = tuple(item.normalized_value for item in ordered)
            values = tuple(item.value for item in ordered)
            if not normalized:
                continue
            by_value_tuple[normalized].extend(ordered)
            representative_values.setdefault(normalized, values)

        alternatives: list[_GroupedAlternative] = []
        for normalized, group in by_value_tuple.items():
            alternatives.append(
                _GroupedAlternative(
                    values=representative_values[normalized],
                    normalized_values=normalized,
                    score=self._aggregate_score(group),
                    candidates=tuple(group),
                )
            )
        return alternatives

    def _aggregate_score(self, candidates: list[BibliographicFieldCandidate]) -> float:
        base = max(self._candidate_score(candidate) for candidate in candidates)
        distinct_sources = {
            (candidate.source_format, candidate.source_file, candidate.source_record_id)
            for candidate in candidates
        }
        support_bonus = min(0.10, 0.03 * (len(distinct_sources) - 1))
        return min(1.0, base + support_bonus)

    @staticmethod
    def _candidate_score(candidate: BibliographicFieldCandidate) -> float:
        score = candidate.confidence
        score += _SOURCE_BONUS[candidate.source_format]
        score += _METHOD_BONUS.get(candidate.method, 0.0)
        if candidate.method.startswith("pdf_metadata"):
            score -= 0.08
        return max(0.0, min(1.0, score))

    @staticmethod
    def _source_label(candidate: BibliographicFieldCandidate) -> str:
        suffix = f"#{candidate.source_record_id}" if candidate.source_record_id else ""
        return f"{candidate.source_format.value}:{candidate.source_file}{suffix}"

    def _candidates_with_aliases(
        self,
        record: CanonicalBibliographicRecord,
        schema: ReferenceSchema,
        field_id: str,
    ) -> list[BibliographicFieldCandidate]:
        if field_id in record.excluded_field_ids:
            return []
        direct = list(record.candidates_for(field_id))
        if direct:
            return direct

        aliases: dict[str, tuple[str, ...]] = {
            "academic_place": ("place",),
            "presentation_year": ("publication_year",),
            "defense_year": ("publication_year",),
            "part_title": ("title",),
            "service_title": ("title",),
            "newspaper_title": ("periodical_title",),
            "newspaper_date": ("publication_date", "publication_year"),
            "media_support": ("support",),
            "electronic_description": ("support",),
        }
        source_fields = aliases.get(field_id, ())
        derived: list[BibliographicFieldCandidate] = []
        for source_field in source_fields:
            for candidate in record.candidates_for(source_field):
                derived.append(
                    candidate.model_copy(
                        update={
                            "field_id": field_id,
                            "method": f"alias:{source_field}:{candidate.method}",
                            "confidence": max(0.0, candidate.confidence - 0.03),
                        }
                    )
                )
        return derived

    @staticmethod
    def _missing_required(
        schema: ReferenceSchema,
        resolved: ResolvedBibliographicRecord,
    ) -> list[str]:
        missing: list[str] = []
        for field_id in schema.required_fields:
            field = resolved.fields.get(field_id)
            if field is None or not field.values:
                missing.append(field_id)

        for condition in schema.conditions:
            if condition.any_of:
                if not any(
                    resolved.fields.get(field_id) and resolved.fields[field_id].values
                    for field_id in condition.any_of
                ):
                    missing.append("any_of:" + "|".join(condition.any_of))
            elif condition.when_field_present is not None:
                trigger = resolved.fields.get(condition.when_field_present)
                if trigger is not None and trigger.values:
                    for field_id in condition.then_required:
                        field = resolved.fields.get(field_id)
                        if field is None or not field.values:
                            missing.append(field_id)
        return list(dict.fromkeys(missing))

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import date
from urllib.parse import unquote, urlsplit

from refengine.domain.bibliography import ResolvedBibliographicRecord
from refengine.domain.models import Author
from refengine.rules.catalog import OutputPolicy, load_ufv_2025_catalog
from refengine.services.author_parser import parse_review_authors

_MONTHS_PT = {
    1: "jan.",
    2: "fev.",
    3: "mar.",
    4: "abr.",
    5: "maio",
    6: "jun.",
    7: "jul.",
    8: "ago.",
    9: "set.",
    10: "out.",
    11: "nov.",
    12: "dez.",
}
_MONTH_ALIASES = {
    "january": 1,
    "jan": 1,
    "janeiro": 1,
    "february": 2,
    "feb": 2,
    "fevereiro": 2,
    "march": 3,
    "mar": 3,
    "março": 3,
    "marco": 3,
    "april": 4,
    "apr": 4,
    "abril": 4,
    "may": 5,
    "maio": 5,
    "june": 6,
    "jun": 6,
    "junho": 6,
    "july": 7,
    "jul": 7,
    "julho": 7,
    "august": 8,
    "aug": 8,
    "agosto": 8,
    "september": 9,
    "sep": 9,
    "setembro": 9,
    "october": 10,
    "oct": 10,
    "outubro": 10,
    "november": 11,
    "nov": 11,
    "novembro": 11,
    "december": 12,
    "dec": 12,
    "dezembro": 12,
}

_ALL_SCHEMA_IDS = frozenset(
    {
        "ufv.1",
        "ufv.2",
        "ufv.3",
        "ufv.4",
        "ufv.5",
        "ufv.6",
        "ufv.7",
        "ufv.8",
        "ufv.9",
        "ufv.10",
        "ufv.11",
        "ufv.12",
        "ufv.13",
        "ufv.14",
        "ufv.15",
        "ufv.16_1",
        "ufv.16_2",
        "ufv.16_3",
        "ufv.16_4",
        "ufv.16_5",
        "ufv.16_6",
        "ufv.16_7",
        "ufv.17",
        "ufv.18",
        "ufv.19",
        "ufv.20",
        "ufv.21",
        "ufv.22",
        "ufv.23",
        "ufv.24",
        "ufv.25_1",
        "ufv.25_2",
        "ufv.26",
        "ufv.26_1",
        "ufv.26_2",
        "ufv.27",
        "ufv.28",
        "ufv.29",
        "ufv.30",
        "ufv.31",
        "ufv.32",
        "ufv.33",
        "ufv.34",
    }
)

_EMPHASIS_FIELDS: dict[str, tuple[str, ...]] = {
    "ufv.1": ("title",),
    "ufv.2": ("title",),
    "ufv.3": ("title",),
    "ufv.4": ("host_title",),
    "ufv.5": ("host_title",),
    "ufv.6": ("title",),
    "ufv.7": ("title",),
    "ufv.8": ("event_document_title",),
    "ufv.9": ("periodical_title",),
    "ufv.10": ("event_document_title",),
    "ufv.11": ("event_document_title",),
    "ufv.12": ("periodical_title",),
    "ufv.13": ("event_document_title",),
    "ufv.14": ("title",),
    "ufv.15": ("title",),
    "ufv.16_1": ("legal_document_name", "publication_source"),
    "ufv.16_2": ("legal_document_name",),
    "ufv.16_3": ("legal_document_type", "publication_source"),
    "ufv.16_4": ("legal_document_type",),
    "ufv.16_5": ("administrative_act_type", "publication_source"),
    "ufv.16_6": ("administrative_act_type",),
    "ufv.16_7": ("registry_document_type",),
    "ufv.17": ("periodical_title",),
    "ufv.18": ("periodical_title",),
    "ufv.19": ("periodical_title",),
    "ufv.20": ("periodical_title",),
    "ufv.21": ("periodical_title",),
    "ufv.22": ("periodical_title",),
    "ufv.23": ("newspaper_title",),
    "ufv.24": ("newspaper_title",),
    "ufv.25_1": ("title",),
    "ufv.25_2": ("title",),
    "ufv.26": ("title",),
    "ufv.26_1": ("host_title",),
    "ufv.26_2": ("title",),
    "ufv.27": ("title",),
    "ufv.28": ("title",),
    "ufv.29": ("title",),
    "ufv.30": ("title",),
    "ufv.31": ("title",),
    "ufv.32": ("title",),
    "ufv.33": ("title",),
    "ufv.34": ("service_title", "title"),
}


class ReferenceFormatter:
    """Generate deterministic references under the versioned UFV 2025 profile."""

    def __init__(
        self,
        include_all_authors: bool = True,
        output_policy: OutputPolicy | None = None,
    ) -> None:
        self._include_all_authors = include_all_authors
        self._output_policy = output_policy or load_ufv_2025_catalog().output_policy

    @staticmethod
    def supported_schema_ids() -> frozenset[str]:
        """Return every concrete reference schema formalized by the UFV catalog."""
        return _ALL_SCHEMA_IDS

    def format_resolved(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str = "",
    ) -> str | None:
        """Format a resolved catalog record without consulting legacy metadata."""
        if record.schema_id not in _ALL_SCHEMA_IDS or not record.ready_for_formatting:
            return None

        schema_id = record.schema_id
        if schema_id in {"ufv.1", "ufv.3"}:
            return self._format_monograph(record, access_date, year_suffix)
        if schema_id == "ufv.2":
            return self._format_academic_work(record, access_date, year_suffix)
        if schema_id in {"ufv.4", "ufv.5"}:
            return self._format_monograph_part(record, access_date, year_suffix)
        if schema_id in {"ufv.6", "ufv.7"}:
            return self._format_correspondence(record, access_date)
        if schema_id in {"ufv.8", "ufv.9", "ufv.10"}:
            return self._format_event_whole(record, access_date, year_suffix)
        if schema_id in {"ufv.11", "ufv.12", "ufv.13"}:
            return self._format_event_part(record, access_date, year_suffix)
        if schema_id in {"ufv.14", "ufv.15"}:
            return self._format_patent(record, access_date)
        if schema_id in {"ufv.16_1", "ufv.16_2"}:
            return self._format_legislation(record, access_date)
        if schema_id in {"ufv.16_3", "ufv.16_4"}:
            return self._format_jurisprudence(record, access_date)
        if schema_id in {"ufv.16_5", "ufv.16_6"}:
            return self._format_administrative_act(record, access_date)
        if schema_id == "ufv.16_7":
            return self._format_registry_document(record)
        if schema_id in {"ufv.17", "ufv.18", "ufv.19", "ufv.20"}:
            return self._format_periodical_collection(record, access_date, year_suffix)
        if schema_id in {"ufv.21", "ufv.22"}:
            return self._format_article(record, access_date, year_suffix)
        if schema_id in {"ufv.23", "ufv.24"}:
            return self._format_newspaper_article(record, access_date)
        if schema_id in {"ufv.25_1", "ufv.25_2"}:
            return self._format_audiovisual(record, access_date, year_suffix)
        if schema_id in {"ufv.26", "ufv.26_2"}:
            return self._format_sound_document(record, access_date, year_suffix)
        if schema_id == "ufv.26_1":
            return self._format_sound_part(record, year_suffix)
        if schema_id in {"ufv.27", "ufv.28"}:
            return self._format_score(record, access_date, year_suffix)
        if schema_id in {"ufv.29", "ufv.30"}:
            return self._format_iconographic(record, access_date, year_suffix)
        if schema_id in {"ufv.31", "ufv.32"}:
            return self._format_cartographic(record, access_date, year_suffix)
        if schema_id == "ufv.33":
            return self._format_three_dimensional(record, year_suffix)
        if schema_id == "ufv.34":
            return self._format_exclusive_electronic(record, access_date, year_suffix)
        return None

    def emphasis_values(self, record: ResolvedBibliographicRecord) -> list[str]:
        """Return title values that receive the catalog's uniform typographic emphasis."""
        values: list[str] = []
        for field_id in _EMPHASIS_FIELDS.get(record.schema_id or "", ()):
            value = record.value_for(field_id)
            if value and value not in values:
                values.append(value)
        return sorted(values, key=len, reverse=True)

    def resolved_authorship_key(
        self,
        record: ResolvedBibliographicRecord,
    ) -> tuple[tuple[str, str], ...]:
        for field_id in ("authors", "composer", "creator", "host_authors"):
            values = record.values_for(field_id)
            if not values:
                continue
            parsed = self._parse_people(values)
            if parsed:
                return tuple(
                    (
                        self._normalize_token(author.family_name),
                        self._normalize_token(author.given_names),
                    )
                    for author in parsed
                )
        corporate = (
            record.value_for("corporate_author")
            or record.value_for("jurisdiction")
            or record.value_for("event_name")
            or record.value_for("title")
            or record.value_for("service_title")
            or record.value_for("creator")
        )
        return ((self._normalize_token(corporate), ""),) if corporate else tuple()

    def resolved_sort_key(self, record: ResolvedBibliographicRecord) -> tuple[str, str, str]:
        """Return a locale-stable alphabetical key for the final UFV list."""
        responsibility = self._sort_token(self._sort_responsibility(record))
        title = self._sort_token(
            record.value_for("title")
            or record.value_for("part_title")
            or record.value_for("event_name")
            or record.value_for("periodical_title")
            or record.value_for("service_title")
            or record.value_for("legal_document_name")
            or record.value_for("legal_document_type")
            or record.value_for("registry_document_type")
            or ""
        )
        year = self.year_value(record)
        return responsibility, title, year

    @staticmethod
    def year_value(record: ResolvedBibliographicRecord) -> str:
        """Return the year-like value used for alphabetical same-author disambiguation."""
        for field_id in (
            "publication_year",
            "defense_year",
            "presentation_year",
            "event_year",
            "start_year",
            "correspondence_date",
            "legal_document_date",
            "judgment_date",
            "signature_date",
            "registry_date",
            "deposit_date",
            "publication_date",
            "newspaper_date",
        ):
            value = record.value_for(field_id)
            if value:
                match = re.search(r"\b(?:18|19|20|21)\d{2}\b", value)
                return match.group(0) if match else value
        return "s.d."

    def _format_monograph(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        responsibility = self._format_responsibility(record)
        title = self._title_with_subtitle(record, "title", "subtitle")
        parts = [f"{responsibility}. {title}."]
        self._append_sentences(parts, record.values_for("other_responsibility"))
        self._append_sentence(parts, record.value_for("edition"))
        place = record.value_for("place") or "[S. l.]"
        publisher = record.value_for("publisher") or "[s. n.]"
        year = self._year(record, "publication_year", year_suffix)
        parts.append(f"{place}: {publisher}, {year}.")
        for field_id in (
            "support",
            "physical_description",
            "illustrations",
            "dimensions",
            "series",
        ):
            self._append_sentence(parts, record.value_for(field_id))
        self._append_sentences(parts, record.values_for("notes"))
        if record.value_for("isbn"):
            parts.append(f"ISBN {self._strip_terminal(record.value_for('isbn'))}.")
        return self._append_online(parts, record, access_date)

    def _format_academic_work(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        responsibility = self._format_responsibility(record)
        title = self._title_with_subtitle(record, "title", "subtitle")
        parts = [f"{responsibility}. {title}."]
        advisor = record.value_for("advisor")
        if advisor:
            parts.append(f"Orientador: {self._strip_terminal(advisor)}.")
        presentation_year = self._year(record, "presentation_year", year_suffix)
        parts.append(f"{presentation_year}.")
        pagination = record.value_for("pagination")
        if pagination:
            normalized = self._strip_terminal(pagination)
            parts.append(f"{normalized if self._has_unit(normalized) else normalized + ' f.'}")
        work_type = record.value_for("work_type") or "Trabalho acadêmico"
        course = record.value_for("degree_course")
        type_text = work_type
        if course and self._normalize_token(course) not in self._normalize_token(work_type):
            type_text += f" ({course})"
        affiliation = record.value_for("academic_affiliation") or "[Instituição não identificada]"
        place = record.value_for("academic_place") or "[S. l.]"
        defense_year = self._year(record, "defense_year", year_suffix)
        parts.append(f"{type_text} – {affiliation}, {place}, {defense_year}.")
        return self._append_online(parts, record, access_date)

    def _format_monograph_part(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        responsibility = self._format_people_field(record, "authors")
        part_title = self._title_with_subtitle(record, "part_title", "part_subtitle")
        host_responsibility = self._format_people_field(record, "host_authors", fallback="")
        host_title = self._title_with_subtitle(record, "host_title", "host_subtitle")
        in_segment = "In: "
        if host_responsibility:
            in_segment += f"{host_responsibility}. "
        in_segment += f"{host_title}."
        parts = [f"{responsibility}. {part_title}.", in_segment]
        self._append_sentence(parts, record.value_for("host_edition"))
        place = record.value_for("place") or "[S. l.]"
        publisher = record.value_for("publisher") or "[s. n.]"
        year = self._year(record, "publication_year", year_suffix)
        parts.append(f"{place}: {publisher}, {year}.")
        extent: list[str] = []
        if record.value_for("volume"):
            extent.append(f"v. {self._strip_terminal(record.value_for('volume'))}")
        if record.value_for("chapter"):
            extent.append(f"cap. {self._strip_terminal(record.value_for('chapter'))}")
        if part_pages := record.value_for("part_pages"):
            extent.append(f"p. {self._normalize_page_range(part_pages)}")
        if extent:
            parts.append(", ".join(extent) + ".")
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_correspondence(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
    ) -> str:
        responsibility = self._format_people_field(record, "authors")
        title = record.value_for("title") or "[Correspondência]"
        parts = [f"{responsibility}. {self._strip_terminal(title)}."]
        recipient = record.value_for("recipient")
        if recipient:
            parts.append(f"Destinatário: {self._strip_terminal(recipient)}.")
        location_and_date = ", ".join(
            value
            for value in (record.value_for("place"), record.value_for("correspondence_date"))
            if value
        )
        if location_and_date:
            parts.append(f"{self._strip_terminal(location_and_date)}.")
        self._append_sentence(parts, record.value_for("correspondence_description"))
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_event_whole(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        heading = self._event_heading(record)
        document_title = record.value_for("event_document_title") or "[Documento do evento]"
        parts = [f"{heading} {self._strip_terminal(document_title)}."]
        if record.schema_id == "ufv.9":
            periodical = self._title_with_subtitle(
                record,
                "periodical_title",
                "periodical_subtitle",
            )
            parts.append(f"{periodical}.")
            place = record.value_for("place") or "[S. l.]"
            publisher = record.value_for("publisher") or "[s. n.]"
            serial = self._serial_details(record)
            publication_date = record.value_for("publication_date") or self._year(
                record, "publication_year", year_suffix
            )
            segment = f"{place}: {publisher}"
            if serial:
                segment += f", {serial}"
            segment += f", {self._strip_terminal(publication_date)}."
            parts.append(segment)
        else:
            place = record.value_for("place") or "[S. l.]"
            publisher = record.value_for("publisher") or "[s. n.]"
            year = self._year(record, "publication_year", year_suffix)
            parts.append(f"{place}: {publisher}, {year}.")
        self._append_sentence(parts, record.value_for("event_pagination"))
        self._append_sentences(parts, record.values_for("event_notes"))
        self._append_sentence(parts, record.value_for("supplement_designation"))
        if record.value_for("isbn"):
            parts.append(f"ISBN {self._strip_terminal(record.value_for('isbn'))}.")
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_event_part(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        responsibility = self._format_people_field(record, "authors")
        title = self._title_with_subtitle(record, "part_title", "part_subtitle")
        parts = [f"{responsibility}. {title}."]
        if record.schema_id == "ufv.12":
            periodical = self._title_with_subtitle(
                record,
                "periodical_title",
                "periodical_subtitle",
            )
            place = self._embedded_place(record.value_for("place"))
            segment = f"{periodical}, {place}"
            serial = self._serial_details(record)
            if serial:
                segment += f", {serial}"
            if part_pages := record.value_for("part_pages"):
                segment += f", p. {self._normalize_page_range(part_pages)}"
            publication_date = record.value_for("publication_date") or self._year(
                record, "publication_year", year_suffix
            )
            segment += f", {self._strip_terminal(publication_date)}."
            parts.append(segment)
            self._append_sentence(parts, record.value_for("supplement_designation"))
            parts.append(f"Trabalho apresentado no {self._event_heading(record, terminal=False)}.")
        else:
            parts.append(f"In: {self._event_heading(record)}")
            document_title = record.value_for("event_document_title") or "[Documento do evento]"
            parts.append(f"{self._strip_terminal(document_title)}.")
            place = record.value_for("place") or "[S. l.]"
            publisher = record.value_for("publisher") or "[s. n.]"
            year = self._year(record, "publication_year", year_suffix)
            parts.append(f"{place}: {publisher}, {year}.")
            if part_pages := record.value_for("part_pages"):
                parts.append(f"p. {self._normalize_page_range(part_pages)}.")
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_patent(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
    ) -> str:
        responsibility = self._format_people_field(record, "authors")
        title = record.value_for("title") or "[Título não identificado]"
        parts = [f"{responsibility}. {self._strip_terminal(title)}."]
        self._append_labeled_values(parts, "Depositante", record.values_for("patent_depositor"))
        self._append_labeled_values(parts, "Titular", record.values_for("patent_holder"))
        self._append_labeled_values(parts, "Procurador", record.values_for("patent_attorney"))
        self._append_sentence(parts, record.value_for("patent_number"))
        if record.value_for("deposit_date"):
            parts.append(f"Depósito: {self._strip_terminal(record.value_for('deposit_date'))}.")
        if record.value_for("grant_date"):
            parts.append(f"Concessão: {self._strip_terminal(record.value_for('grant_date'))}.")
        self._append_sentence(parts, record.value_for("patent_classification"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_legislation(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
    ) -> str:
        jurisdiction = record.value_for("jurisdiction") or record.value_for("entity_heading") or ""
        name = record.value_for("legal_document_name") or "[Documento legal]"
        number = record.value_for("legal_document_number")
        document_date = record.value_for("legal_document_date")
        heading = name
        if number:
            heading += f" n. {self._strip_terminal(number)}"
        if document_date:
            heading += f", de {self._strip_terminal(document_date)}"
        parts = [f"{jurisdiction}. {heading}."]
        self._append_sentence(parts, record.value_for("ementa"))
        self._append_sentence(parts, record.value_for("publication_source"))
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_jurisprudence(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
    ) -> str:
        jurisdiction = record.value_for("jurisdiction") or ""
        court = record.value_for("court") or "[Tribunal não identificado]"
        division = record.value_for("court_division")
        court_text = f"{court} ({division})" if division else court
        document_type = record.value_for("legal_document_type") or "[Decisão judicial]"
        process_number = record.value_for("process_number")
        heading = document_type
        if process_number:
            heading += f" {self._strip_terminal(process_number)}"
        parts = [f"{jurisdiction}. {court_text}. {heading}."]
        self._append_sentence(parts, record.value_for("ementa"))
        self._append_sentence(parts, record.value_for("judicial_unit"))
        if record.value_for("relator"):
            parts.append(f"Relator: {self._strip_terminal(record.value_for('relator'))}.")
        self._append_sentence(parts, record.value_for("judgment_date"))
        self._append_sentence(parts, record.value_for("publication_source"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_administrative_act(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
    ) -> str:
        jurisdiction = record.value_for("jurisdiction") or record.value_for("entity_heading") or ""
        entity = record.value_for("entity_heading")
        prefix = jurisdiction
        if entity and self._normalize_token(entity) not in self._normalize_token(jurisdiction):
            prefix = f"{jurisdiction}. {entity}" if jurisdiction else entity
        act_type = record.value_for("administrative_act_type") or "[Ato administrativo]"
        number = record.value_for("administrative_act_number")
        signature_date = record.value_for("signature_date")
        heading = act_type
        if number:
            heading += f" n. {self._strip_terminal(number)}"
        if signature_date:
            heading += f", de {self._strip_terminal(signature_date)}"
        parts = [f"{prefix}. {heading}."]
        self._append_sentence(parts, record.value_for("ementa"))
        self._append_sentence(parts, record.value_for("publication_source"))
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_registry_document(self, record: ResolvedBibliographicRecord) -> str:
        jurisdiction = record.value_for("jurisdiction") or ""
        office = record.value_for("registry_office") or "[Cartório não identificado]"
        document_type = record.value_for("registry_document_type") or "[Documento civil]"
        registry_date = record.value_for("registry_date") or "[data não identificada]"
        parts = [f"{jurisdiction}. {office}. {document_type}. {registry_date}."]
        self._append_sentences(parts, record.values_for("notes"))
        return self._join(parts)

    def _format_periodical_collection(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        title = self._title_with_subtitle(record, "periodical_title", "periodical_subtitle")
        place = record.value_for("place") or "[S. l.]"
        publisher = record.value_for("publisher") or "[s. n.]"
        parts = [f"{title}. {place}: {publisher},"]
        if record.schema_id == "ufv.20":
            serial = self._serial_details(record)
            publication_date = record.value_for("publication_date") or self._year(
                record, "publication_year", year_suffix
            )
            body = ", ".join(value for value in (serial, publication_date) if value)
            parts[-1] += f" {self._strip_terminal(body)}."
            self._append_sentence(parts, record.value_for("supplement_designation"))
        else:
            start = self._year(record, "start_year", year_suffix)
            end = record.value_for("end_year")
            chronology = f"{start}-{end}" if end else start
            parts[-1] += f" {chronology}."
            if record.schema_id == "ufv.19":
                self._append_sentence(parts, record.value_for("consulted_period"))
        if record.value_for("issn"):
            parts.append(f"ISSN {self._strip_terminal(record.value_for('issn'))}.")
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_article(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        authors = self._format_responsibility(record)
        title = self._title_with_subtitle(record, "title", "subtitle")
        periodical = self._title_with_subtitle(
            record,
            "periodical_title",
            "periodical_subtitle",
        )
        place = self._embedded_place(record.value_for("place"))
        publication = f"{periodical}, {place}"
        serial = self._serial_details(record)
        if serial:
            publication += f", {serial}"
        pages = record.value_for("article_pages")
        article_number = record.value_for("article_number")
        if pages:
            publication += f", p. {self._normalize_page_range(pages)}"
        elif article_number:
            publication += f", art. {self._strip_terminal(article_number)}"
        month = self.normalize_month(
            record.value_for("publication_month") or record.value_for("publication_period")
        )
        year = self._year(record, "publication_year", year_suffix)
        publication += f", {month} {year}." if month else f", {year}."
        parts = [f"{authors}. {title}.", publication]
        self._append_sentence(parts, record.value_for("supplement_designation"))
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_newspaper_article(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
    ) -> str:
        authors = self._format_responsibility(record)
        title = self._title_with_subtitle(record, "title", "subtitle")
        newspaper = self._title_with_subtitle(
            record,
            "newspaper_title",
            "newspaper_subtitle",
        )
        place = self._embedded_place(record.value_for("place"))
        segment = f"{newspaper}, {place}"
        serial = self._serial_details(record)
        if serial:
            segment += f", {serial}"
        section = record.value_for("newspaper_section")
        pages = record.value_for("newspaper_pages")
        newspaper_date = record.value_for("newspaper_date") or "[data não identificada]"
        if pages and not section:
            segment += f", p. {self._normalize_page_range(pages)}"
        segment += f", {self._strip_terminal(newspaper_date)}."
        parts = [f"{authors}. {title}.", segment]
        if section:
            section_text = self._strip_terminal(section)
            if pages:
                section_text += f", p. {self._normalize_page_range(pages)}"
            parts.append(section_text + ".")
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_audiovisual(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        title = record.value_for("title") or "[Título não identificado]"
        parts = [f"{self._strip_terminal(title)}."]
        self._append_labeled_values(parts, "Direção", record.values_for("director"))
        self._append_labeled_values(parts, "Produção", record.values_for("producer"))
        self._append_sentences(parts, record.values_for("audiovisual_responsibilities"))
        place = record.value_for("place") or "[S. l.]"
        publisher = record.value_for("publisher")
        year = self._year(record, "publication_year", year_suffix)
        if publisher:
            parts.append(f"{place}: {publisher}, {year}.")
        else:
            parts.append(f"{place}, {year}.")
        self._append_sentence(parts, record.value_for("media_support"))
        self._append_sentence(parts, record.value_for("physical_description"))
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_sound_document(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        authors = self._format_people_field(record, "authors", fallback="")
        title = record.value_for("title") or "[Título não identificado]"
        first = f"{authors}. {title}." if authors else f"{title}."
        parts = [first]
        self._append_sentences(parts, record.values_for("sound_responsibility"))
        self._append_labeled_values(parts, "Compositor", record.values_for("composer"))
        self._append_labeled_values(parts, "Intérprete", record.values_for("performer"))
        self._append_labeled_values(parts, "Ledor", record.values_for("narrator"))
        place = record.value_for("place") or "[S. l.]"
        label = record.value_for("recording_label") or "[s. n.]"
        publication = (
            record.value_for("publication_date")
            if record.schema_id == "ufv.26_2"
            else self._year(record, "publication_year", year_suffix)
        )
        parts.append(f"{place}: {label}, {self._strip_terminal(publication)}.")
        self._append_sentence(parts, record.value_for("media_support"))
        self._append_sentence(parts, record.value_for("physical_description"))
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_sound_part(
        self,
        record: ResolvedBibliographicRecord,
        year_suffix: str,
    ) -> str:
        part_title = record.value_for("part_title") or "[Título da parte não identificado]"
        parts = [f"{self._strip_terminal(part_title)}."]
        self._append_labeled_values(parts, "Intérprete", record.values_for("performer"))
        self._append_labeled_values(parts, "Compositor", record.values_for("composer"))
        host_title = record.value_for("host_title") or "[Título do documento sonoro]"
        parts.append(f"In: {self._strip_terminal(host_title)}.")
        self._append_sentences(parts, record.values_for("sound_responsibility"))
        place = record.value_for("place") or "[S. l.]"
        label = record.value_for("recording_label") or "[s. n.]"
        year = self._year(record, "publication_year", year_suffix)
        parts.append(f"{place}: {label}, {year}.")
        support = record.value_for("media_support")
        track = record.value_for("track")
        if support and track:
            parts.append(f"{self._strip_terminal(support)}, {self._strip_terminal(track)}.")
        else:
            self._append_sentence(parts, support)
            self._append_sentence(parts, track)
        self._append_sentence(parts, record.value_for("physical_description"))
        return self._join(parts)

    def _format_score(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        composer = self._format_people_field(record, "composer")
        title = self._title_with_subtitle(record, "title", "subtitle")
        parts = [f"{composer}. {title}."]
        self._append_sentence(parts, record.value_for("instrument"))
        place = record.value_for("place")
        publisher = record.value_for("publisher")
        year = self._year(record, "publication_year", year_suffix)
        if place or publisher or record.schema_id == "ufv.27":
            parts.append(f"{place or '[S. l.]'}: {publisher or '[s. n.]'}, {year}.")
        else:
            parts.append(f"{year}.")
        self._append_sentence(parts, record.value_for("physical_description"))
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_iconographic(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        authors = self._format_people_field(record, "authors")
        title = record.value_for("title") or "[Sem título]"
        year = self._year(record, "publication_year", year_suffix)
        support = record.value_for("iconographic_support") or "[Suporte não identificado]"
        parts = [
            f"{authors}. {self._strip_terminal(title)}. {year}. {self._strip_terminal(support)}."
        ]
        for field_id in ("physical_description", "illustrations", "dimensions"):
            self._append_sentence(parts, record.value_for(field_id))
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_cartographic(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        authors = self._format_people_field(record, "authors")
        title = self._title_with_subtitle(record, "title", "subtitle")
        place = record.value_for("place") or "[S. l.]"
        publisher = record.value_for("publisher") or "[s. n.]"
        year = self._year(record, "publication_year", year_suffix)
        parts = [f"{authors}. {title}. {place}: {publisher}, {year}."]
        self._append_sentence(parts, record.value_for("map_description"))
        for field_id in ("physical_description", "illustrations", "dimensions"):
            self._append_sentence(parts, record.value_for(field_id))
        if record.value_for("scale"):
            parts.append(f"Escala {self._strip_terminal(record.value_for('scale'))}.")
        self._append_sentences(parts, record.values_for("notes"))
        self._append_sentence(parts, record.value_for("support"))
        return self._append_online(parts, record, access_date)

    def _format_three_dimensional(
        self,
        record: ResolvedBibliographicRecord,
        year_suffix: str,
    ) -> str:
        creator = self._format_creator(record.values_for("creator"))
        title = record.value_for("title") or "[Sem título]"
        year = self._year(record, "publication_year", year_suffix)
        parts = [f"{creator}. {self._strip_terminal(title)}."]
        place = record.value_for("place")
        manufacturer = record.value_for("manufacturer")
        if place and manufacturer:
            parts.append(f"{place}: {manufacturer}, {year}.")
        elif manufacturer:
            parts.append(f"{manufacturer}, {year}.")
        else:
            parts.append(f"{year}.")
        self._append_sentence(parts, record.value_for("physical_description"))
        self._append_sentence(parts, record.value_for("dimensions"))
        self._append_sentences(parts, record.values_for("notes"))
        return self._join(parts)

    def _format_exclusive_electronic(
        self,
        record: ResolvedBibliographicRecord,
        access_date: date,
        year_suffix: str,
    ) -> str:
        responsibility = self._format_responsibility(record)
        title = (
            record.value_for("service_title")
            or record.value_for("title")
            or "[Título não identificado]"
        )
        parts = [f"{responsibility}. {self._strip_terminal(title)}."]
        self._append_sentence(parts, record.value_for("software_version"))
        place = record.value_for("place")
        year = self._year(record, "publication_year", year_suffix)
        parts.append(f"{place}, {year}." if place else f"{year}.")
        self._append_sentence(
            parts,
            record.value_for("electronic_description") or record.value_for("support"),
        )
        self._append_sentences(parts, record.values_for("notes"))
        return self._append_online(parts, record, access_date)

    def _sort_responsibility(self, record: ResolvedBibliographicRecord) -> str:
        for field_id in ("authors", "composer", "host_authors"):
            if record.values_for(field_id):
                return self._format_people_field(record, field_id)
        corporate_author = record.value_for("corporate_author")
        return (
            self._format_corporate_author(corporate_author)
            if corporate_author
            else record.value_for("jurisdiction")
            or record.value_for("event_name")
            or record.value_for("creator")
            or record.value_for("title")
            or record.value_for("service_title")
            or ""
        )

    def _format_responsibility(self, record: ResolvedBibliographicRecord) -> str:
        authors = record.values_for("authors")
        if authors:
            return self._format_people(authors)
        corporate_author = record.value_for("corporate_author")
        return (
            self._format_corporate_author(corporate_author)
            if corporate_author
            else record.value_for("creator")
            or record.value_for("jurisdiction")
            or "[AUTORIA NÃO IDENTIFICADA]"
        )

    @staticmethod
    def _format_corporate_author(value: str) -> str:
        """Normalize a jurisdiction-led corporate heading without guessing entities."""
        cleaned = value.strip().rstrip(".")
        if "." not in cleaned:
            return cleaned
        jurisdiction, remainder = cleaned.split(".", 1)
        return f"{jurisdiction.upper()}.{remainder}"

    def _format_people_field(
        self,
        record: ResolvedBibliographicRecord,
        field_id: str,
        fallback: str = "[AUTORIA NÃO IDENTIFICADA]",
    ) -> str:
        values = record.values_for(field_id)
        return self._format_people(values) if values else fallback

    def _format_people(self, values: list[str]) -> str:
        parsed = self._parse_people(values)
        if not parsed:
            return "; ".join(self._strip_terminal(value) for value in values)
        selected = parsed
        suffix = ""
        if len(parsed) >= 4 and not self._include_all_authors:
            selected = parsed[:1]
            suffix = " et al."
        rendered = "; ".join(
            f"{author.family_name.upper()}, {author.given_names}".rstrip(", ")
            for author in selected
        )
        return (rendered + suffix).rstrip(".")

    @staticmethod
    def _parse_people(values: list[str]) -> list[Author]:
        parsed: list[Author] = []
        for value in values:
            try:
                parsed.extend(parse_review_authors(value))
            except ValueError:
                continue
        return parsed

    def _format_creator(self, values: list[str]) -> str:
        if not values:
            return "[CRIADOR NÃO IDENTIFICADO]"
        if all(value == value.upper() for value in values if value):
            return "; ".join(self._strip_terminal(value) for value in values)
        return self._format_people(values)

    @staticmethod
    def _title_with_subtitle(
        record: ResolvedBibliographicRecord,
        title_field: str,
        subtitle_field: str,
    ) -> str:
        title = record.value_for(title_field) or "[Título não identificado]"
        subtitle = record.value_for(subtitle_field)
        return f"{title}: {subtitle}" if subtitle else title

    def _event_heading(
        self,
        record: ResolvedBibliographicRecord,
        *,
        terminal: bool = True,
    ) -> str:
        name = record.value_for("event_name") or "[EVENTO NÃO IDENTIFICADO]"
        number = record.value_for("event_number")
        year = record.value_for("event_year") or "[ano não identificado]"
        place = record.value_for("event_place") or "[S. l.]"
        if number:
            heading = f"{name}, {self._strip_terminal(number)}., {year}, {place}"
        else:
            heading = f"{name}, {year}, {place}"
        return heading + "." if terminal else heading

    def _serial_details(self, record: ResolvedBibliographicRecord) -> str:
        details: list[str] = []
        if record.value_for("year_designation"):
            details.append(f"ano {self._strip_terminal(record.value_for('year_designation'))}")
        if record.value_for("volume"):
            details.append(f"v. {self._strip_terminal(record.value_for('volume'))}")
        if record.value_for("issue"):
            details.append(f"n. {self._strip_terminal(record.value_for('issue'))}")
        if record.value_for("fascicle"):
            details.append(f"fasc. {self._strip_terminal(record.value_for('fascicle'))}")
        return ", ".join(details)

    def _append_online(
        self,
        parts: list[str],
        record: ResolvedBibliographicRecord,
        access_date: date,
    ) -> str:
        """Append DOI and online location without repeating the DOI resolver as URL."""
        doi_url = self._doi_url(record.value_for("doi"))
        if doi_url:
            parts.append(f"DOI: {doi_url}.")

        raw_url = record.value_for("url")
        url = self._strip_terminal(raw_url)
        url_repeats_doi = bool(url and self._url_matches_doi(url, doi_url))
        should_suppress_duplicate = (
            self._output_policy.doi_url_deduplication and url_repeats_doi
        )
        should_keep_distinct = (
            not doi_url or self._output_policy.distinct_url_with_doi
        )
        if url and not should_suppress_duplicate and should_keep_distinct:
            parts.append(f"Disponível em: {url}.")
            raw_access = record.value_for("access_date")
            formatted_access = self._format_access_date(raw_access, access_date)
            access_time = record.value_for("access_time")
            if access_time:
                formatted_access += f", {self._strip_terminal(access_time)}"
            parts.append(f"Acesso em: {formatted_access}.")
        return self._join(parts)

    @staticmethod
    def _format_access_date(raw_access: str | None, fallback: date) -> str:
        if raw_access:
            try:
                parsed = date.fromisoformat(raw_access)
            except ValueError:
                return raw_access.rstrip(".")
            return ReferenceFormatter._format_date(parsed)
        return ReferenceFormatter._format_date(fallback)

    @classmethod
    def normalize_month(cls, value: str | None) -> str | None:
        if not value:
            return None
        tokens = [
            re.sub(r"[^A-Za-zÀ-ÿ]", "", item).casefold() for item in re.split(r"[/–-]", value)
        ]
        month_numbers = [
            month for token in tokens if token and (month := _MONTH_ALIASES.get(token)) is not None
        ]
        if not month_numbers:
            return value.strip()
        if len(month_numbers) == 1:
            return _MONTHS_PT[month_numbers[0]]
        return f"{_MONTHS_PT[month_numbers[0]]}/{_MONTHS_PT[month_numbers[-1]]}"

    @staticmethod
    def _doi_url(value: str | None) -> str | None:
        if not value:
            return None
        normalized = re.sub(
            r"^https?://(?:dx\.)?doi\.org/",
            "",
            value.strip().rstrip("."),
            flags=re.IGNORECASE,
        )
        return f"https://doi.org/{normalized}"

    @classmethod
    def _url_matches_doi(cls, url: str, doi_url: str | None) -> bool:
        """Return whether an URL is only another spelling of the selected DOI."""
        if not doi_url:
            return False
        return cls._doi_identifier(url) == cls._doi_identifier(doi_url)

    @staticmethod
    def _doi_identifier(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = unquote(value.strip().rstrip(".;, "))
        parsed = urlsplit(cleaned if "://" in cleaned else f"https://doi.org/{cleaned}")
        host = parsed.netloc.casefold().removeprefix("www.")
        if host not in {"doi.org", "dx.doi.org"}:
            return None
        identifier = parsed.path.lstrip("/").strip().casefold()
        return identifier or None

    @staticmethod
    def _sort_token(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
        return re.sub(r"\s+", " ", unaccented).strip()

    @staticmethod
    def _normalize_token(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()

    @staticmethod
    def _normalize_page_range(value: str) -> str:
        return re.sub(r"\s*(?:--+|[–—])\s*", "-", value.strip().rstrip("."))

    @staticmethod
    def _format_date(value: date) -> str:
        return f"{value.day} {_MONTHS_PT[value.month]} {value.year}"

    @staticmethod
    def _strip_terminal(value: str | None) -> str:
        return value.strip().rstrip(".;, ") if value else ""

    @staticmethod
    def _embedded_place(value: str | None) -> str:
        if not value:
            return "[s. l.]"
        if value.casefold() == "[s. l.]":
            return "[s. l.]"
        return value

    @staticmethod
    def _has_unit(value: str) -> bool:
        return bool(re.search(r"\b(?:p|f|v|vol)\.?$", value, flags=re.IGNORECASE))

    @staticmethod
    def _join(parts: Iterable[str]) -> str:
        return " ".join(part.strip() for part in parts if part and part.strip())

    @classmethod
    def _append_sentence(cls, parts: list[str], value: str | None) -> None:
        cleaned = cls._strip_terminal(value)
        if cleaned:
            parts.append(cleaned + ".")

    @classmethod
    def _append_sentences(cls, parts: list[str], values: Iterable[str]) -> None:
        for value in values:
            cls._append_sentence(parts, value)

    @classmethod
    def _append_labeled_values(
        cls,
        parts: list[str],
        label: str,
        values: list[str],
    ) -> None:
        cleaned = [cls._strip_terminal(value) for value in values if cls._strip_terminal(value)]
        if cleaned:
            parts.append(f"{label}: {'; '.join(cleaned)}.")

    @staticmethod
    def _year(
        record: ResolvedBibliographicRecord,
        field_id: str,
        suffix: str,
    ) -> str:
        value = record.value_for(field_id) or "[s. d.]"
        if suffix and re.search(r"\b(?:18|19|20|21)\d{2}$", value):
            return value + suffix
        return value

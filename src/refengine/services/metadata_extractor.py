from __future__ import annotations

import difflib
import re
import unicodedata
from pathlib import Path
from typing import Any

import fitz

from refengine.domain.enums import DocumentType
from refengine.domain.models import ArticleMetadata, Evidence, PageText
from refengine.services.author_parser import parse_authors
from refengine.services.document_classifier import classify_document_type
from refengine.services.generic_pdf import generic_periodical_fields
from refengine.services.web_print_metadata import extract_web_print_metadata

DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


class MetadataExtractor:
    """Extract auditable metadata, preferring page evidence over unreliable PDF tags."""

    CACHE_SIGNATURE = "metadata-extractor:generic-periodical-v2"

    def cache_signature(self) -> str:
        """Invalidate cached PDF metadata whenever extraction rules change."""
        return self.CACHE_SIGNATURE

    def extract(self, pdf_path: Path, pages: list[PageText]) -> ArticleMetadata:
        with fitz.open(pdf_path) as document:
            internal = document.metadata
            first_page = document.load_page(0)
            last_page = document.load_page(document.page_count - 1)
            blocks = sorted(
                first_page.get_text("blocks"),
                key=lambda block: (block[1], block[0]),
            )
            native_first_text = first_page.get_text("text")
            native_last_text = last_page.get_text("text")

        searchable_pages = [page for page in pages[:8] if page.text]
        searchable_text = "\n".join(page.text for page in searchable_pages)
        first_text = pages[0].text if pages and pages[0].text else native_first_text
        last_text = pages[-1].text if pages and pages[-1].text else native_last_text

        document_type = classify_document_type(pages)
        doi = self._doi(internal, pages)
        bibliographic = self._bibliographic_fields(
            first_text,
            last_text,
            searchable_text,
            doi.value,
            page_count=len(pages),
        )
        web_print = extract_web_print_metadata(searchable_text)
        if web_print is not None:
            bibliographic.update(web_print.as_fields())
        title = self._title(
            internal.get("title"),
            blocks,
            searchable_text,
            document_type,
            bibliographic,
        )
        authors_evidence = self._authors_block(
            title.value,
            blocks,
            internal.get("author"),
            searchable_text,
            bibliographic,
            document_type,
        )
        authors = parse_authors(authors_evidence.value)

        extractor_name = str(bibliographic.get("extractor", "generic"))
        is_generic_periodical = extractor_name == "generic_periodical_structure"
        header_method = (
            "web_print_profile"
            if extractor_name.endswith("_web_print")
            else "generic_periodical_pattern"
            if is_generic_periodical
            else "publisher_header"
        )
        journal = self._evidence(
            bibliographic.get("journal"),
            0.84 if is_generic_periodical else 0.97,
            header_method,
            1,
        )
        year = self._evidence(
            bibliographic.get("year"),
            0.82 if is_generic_periodical else 0.97,
            header_method,
            1,
        )
        volume = self._evidence(
            bibliographic.get("volume"),
            0.84 if is_generic_periodical else 0.96,
            header_method,
            1,
        )
        issue_inferred = bool(bibliographic.get("issue_inferred"))
        issue = self._evidence(
            bibliographic.get("issue"),
            0.85 if issue_inferred else 0.83 if is_generic_periodical else 0.95,
            "doi_structure" if issue_inferred else header_method,
            1,
        )
        pages_field = self._evidence(
            bibliographic.get("pages"),
            0.84 if is_generic_periodical else 0.95,
            header_method,
            1,
        )
        article_number = self._evidence(
            bibliographic.get("article_number"),
            0.84 if is_generic_periodical else 0.96,
            header_method,
            1,
        )
        month = self._publication_month(
            searchable_text,
            bibliographic.get("year"),
            bibliographic.get("month"),
        )
        academic = self._academic_fields(
            searchable_text,
            document_type,
            page_count=len(pages),
        )
        for field_name in (
            "institution",
            "degree",
            "program",
            "publisher",
            "total_pages",
            "corporate_author",
            "department",
            "place",
        ):
            value = bibliographic.get(field_name)
            if isinstance(value, str) and value:
                academic[field_name] = value
        place = self._place(
            searchable_text + "\n" + last_text,
            academic.get("place") or bibliographic.get("place"),
        )
        source_url = self._source_url(
            bibliographic=bibliographic,
            doi=doi.value,
        )
        visible_source_url = bool(bibliographic.get("source_url"))
        url = self._evidence(
            source_url,
            0.97 if visible_source_url else (0.92 if source_url else 0),
            (
                "web_print_profile"
                if visible_source_url
                else "publisher_url_pattern"
                if source_url
                else "url_not_found"
            ),
            1 if visible_source_url else doi.page_number if source_url else None,
        )
        return ArticleMetadata(
            title=title,
            authors=authors,
            authors_evidence=authors_evidence,
            journal=journal,
            place=place,
            year=year,
            publication_month=month,
            volume=volume,
            issue=issue,
            pages=pages_field,
            article_number=article_number,
            doi=doi,
            url=url,
            extractor=extractor_name,
            document_type=document_type,
            institution=self._evidence(
                academic.get("institution"),
                0.97 if bibliographic.get("institution") else 0.9,
                "web_print_profile"
                if bibliographic.get("institution")
                else "academic_front_matter",
                1,
            ),
            degree=self._evidence(
                academic.get("degree"),
                0.97 if bibliographic.get("degree") else 0.9,
                "web_print_profile" if bibliographic.get("degree") else "academic_front_matter",
                1,
            ),
            program=self._evidence(academic.get("program"), 0.8, "academic_front_matter", 1),
            publisher=self._evidence(academic.get("publisher"), 0.8, "publisher_profile", 1),
            total_pages=self._evidence(
                academic.get("total_pages"),
                0.97 if bibliographic.get("total_pages") else 0.85,
                "web_print_profile" if bibliographic.get("total_pages") else "physical_description",
                1,
            ),
            corporate_author=self._evidence(
                academic.get("corporate_author"), 0.85, "institutional_heading", 1
            ),
            department=self._evidence(academic.get("department"), 0.9, "academic_front_matter", 2),
            access_date=self._evidence(None, 0, "not_provided", None),
        )

    def _title(
        self,
        internal_title: str | None,
        blocks: list[tuple[Any, ...]],
        searchable_text: str,
        document_type: DocumentType,
        bibliographic: dict[str, str | bool],
    ) -> Evidence:
        visible_title = bibliographic.get("title")
        if isinstance(visible_title, str) and visible_title:
            generic = bibliographic.get("extractor") == "generic_periodical_structure"
            return Evidence(
                value=visible_title,
                confidence=0.88 if generic else 0.97,
                page_number=1,
                excerpt=visible_title,
                method="generic_front_matter" if generic else "web_print_profile",
            )
        if document_type in {DocumentType.THESIS, DocumentType.DISSERTATION}:
            academic_record = self._academic_catalog_record(searchable_text)
            catalog_title = academic_record.get("title")
            cover_title = self._academic_cover_title(searchable_text)
            # The UFV manual requires the title to be reproduced as it appears in the
            # consulted document. Prefer the cataloging record when it is available;
            # unlike an all-caps cover, it normally preserves the document's own case.
            selected_title = catalog_title or cover_title
            if selected_title:
                return Evidence(
                    value=selected_title,
                    confidence=0.98 if catalog_title else 0.94,
                    page_number=2 if catalog_title else 1,
                    excerpt=selected_title,
                    method=("academic_catalog_record" if catalog_title else "academic_cover"),
                )

        profile_title = self._profile_title(
            searchable_text,
            internal_title,
            str(bibliographic.get("extractor", "")),
            blocks,
        )
        if profile_title:
            return Evidence(
                value=profile_title,
                confidence=0.98,
                page_number=1,
                excerpt=profile_title,
                method="publisher_profile",
            )
        if self._trustworthy_internal_title(internal_title):
            value = self._clean(internal_title or "")
            return Evidence(
                value=value,
                confidence=0.9,
                page_number=1,
                excerpt=value,
                method="pdf_metadata",
            )

        scielo_title = self._scielo_title(searchable_text)
        if scielo_title:
            return Evidence(
                value=scielo_title,
                confidence=0.98,
                page_number=1,
                excerpt=scielo_title,
                method="scielo_content",
            )

        candidates: list[tuple[float, str]] = []
        for index, block in enumerate(blocks[:8]):
            value = self._deduplicate_block(str(block[4]))
            if self._title_candidate(value):
                score = 1.0 - index * 0.08 + min(len(value), 180) / 1000
                candidates.append((score, value))
        if candidates:
            value = max(candidates, key=lambda item: item[0])[1]
            return Evidence(
                value=value,
                confidence=0.82,
                page_number=1,
                excerpt=value,
                method="first_page_layout",
            )

        lines = [
            self._clean(line)
            for line in searchable_text.splitlines()
            if self._title_candidate(line)
        ]
        fallback_value = max(lines[:30], key=len, default=None)
        return Evidence(
            value=fallback_value,
            confidence=0.55 if fallback_value else 0,
            page_number=1 if fallback_value else None,
            excerpt=fallback_value,
            method="text_heading_heuristic",
        )

    def _authors_block(
        self,
        title: str | None,
        blocks: list[tuple[Any, ...]],
        internal_author: str | None,
        searchable_text: str,
        bibliographic: dict[str, str | bool],
        document_type: DocumentType,
    ) -> Evidence:
        visible_authors = bibliographic.get("authors")
        if isinstance(visible_authors, str) and visible_authors:
            generic = bibliographic.get("extractor") == "generic_periodical_structure"
            return Evidence(
                value=visible_authors,
                confidence=0.88 if generic else 0.97,
                page_number=1,
                excerpt=visible_authors,
                method="generic_front_matter" if generic else "web_print_profile",
            )
        if bibliographic.get("author_visibility") == "collapsed_or_absent":
            return Evidence(
                value=None,
                confidence=0,
                page_number=1,
                excerpt="Author section is collapsed or absent in the printed source.",
                method="not_visible_in_print",
            )
        if document_type in {DocumentType.THESIS, DocumentType.DISSERTATION}:
            academic_record = self._academic_catalog_record(searchable_text)
            cover_author = self._academic_cover_author(searchable_text)
            catalog_author = academic_record.get("author")
            academic_author = cover_author or catalog_author
            if cover_author and catalog_author:
                same_person = self._normalize(cover_author) == self._normalize(catalog_author)
                if not same_person:
                    academic_author = catalog_author
            if academic_author:
                return Evidence(
                    value=academic_author,
                    confidence=0.98,
                    page_number=1,
                    excerpt=academic_author,
                    method=(
                        "academic_cover"
                        if academic_author == cover_author
                        else "academic_catalog_record"
                    ),
                )

        extractor_name = str(bibliographic.get("extractor", ""))

        if extractor_name == "mdpi" and self._trustworthy_internal_author(internal_author):
            value = self._clean(internal_author or "")
            return Evidence(
                value=value,
                confidence=0.97,
                page_number=1,
                excerpt=value,
                method="publisher_pdf_metadata",
            )

        profile_authors = self._profile_authors(
            searchable_text,
            title,
            extractor_name,
        )
        if profile_authors:
            return Evidence(
                value=profile_authors,
                confidence=0.98,
                page_number=1,
                excerpt=profile_authors,
                method="publisher_profile",
            )

        text_author = self._text_authors_after_title(title, searchable_text)
        if text_author:
            return Evidence(
                value=text_author,
                confidence=0.9,
                page_number=1,
                excerpt=text_author,
                method="text_after_title",
            )

        if title:
            normalized_title = self._normalize(title)
            best: tuple[int, float] | None = None
            for index, block in enumerate(blocks):
                text = self._normalize(str(block[4]))
                ratio = difflib.SequenceMatcher(
                    None,
                    normalized_title,
                    text,
                ).ratio()
                if normalized_title in text or text in normalized_title:
                    ratio = max(ratio, 0.95)
                if best is None or ratio > best[1]:
                    best = (index, ratio)
            if best and best[1] >= 0.55:
                for block in blocks[best[0] + 1 : best[0] + 5]:
                    candidate = self._clean(str(block[4]))
                    if self._author_candidate(candidate):
                        return Evidence(
                            value=candidate,
                            confidence=0.92,
                            page_number=1,
                            excerpt=candidate,
                            method="layout_block_after_title",
                        )

        if self._trustworthy_internal_author(internal_author):
            value = self._clean(internal_author or "")
            return Evidence(
                value=value,
                confidence=0.75,
                page_number=1,
                excerpt=value,
                method="pdf_metadata_fallback",
            )

        if internal_author and internal_author.strip():
            value = self._clean(internal_author)
            return Evidence(
                value=None,
                confidence=0,
                page_number=1,
                excerpt=value,
                method="untrusted_pdf_metadata_rejected",
            )
        return Evidence(value=None, confidence=0, method="authors_not_found")

    def _profile_title(
        self,
        searchable_text: str,
        internal_title: str | None,
        extractor: str,
        blocks: list[tuple[Any, ...]],
    ) -> str | None:
        """Extract titles from stable publisher layouts without file-specific hashes."""
        lines = [self._clean(line) for line in searchable_text.splitlines() if self._clean(line)]

        if extractor == "global_sustainability_research":
            for index, line in enumerate(lines):
                if line.casefold() == "review article" and index + 1 < len(lines):
                    return lines[index + 1]

        if extractor == "elsevier_rser" and internal_title:
            value = self._clean(internal_title.replace("_", ":"))
            value = re.sub(
                r":\s*A\s+review$",
                ": a review",
                value,
                flags=re.IGNORECASE,
            )
            if len(value) >= 25:
                return value

        if extractor in {
            "springer_environmental_chemistry_letters",
            "bmc_medicine",
        } and self._trustworthy_internal_title(internal_title):
            return self._clean(internal_title or "")

        if extractor == "scielo_scientia_agricola":
            for index, block in enumerate(blocks):
                value = self._deduplicate_block(str(block[4]))
                if value.casefold() == "review":
                    for following in blocks[index + 1 : index + 4]:
                        candidate = self._deduplicate_block(str(following[4]))
                        if self._title_candidate(candidate):
                            return candidate

        if extractor == "scielo_original":
            return self._scielo_title_from_layout(searchable_text)

        return None

    def _profile_authors(
        self,
        searchable_text: str,
        title: str | None,
        extractor: str,
    ) -> str | None:
        """Extract visible author segments from stable publisher layout markers."""
        clean_text = self._clean(searchable_text)
        lines = [self._clean(line) for line in searchable_text.splitlines() if self._clean(line)]

        if extractor == "global_sustainability_research":
            for index, line in enumerate(lines):
                if line.casefold() == "review article" and index + 2 < len(lines):
                    return lines[index + 2]

        if not title:
            return None

        end_markers: dict[str, tuple[str, ...]] = {
            "springer_environmental_chemistry_letters": ("Received:",),
            "bmc_medicine": ("Abstract",),
            "elsevier_rser": (
                " a Department",
                " Department of",
                " a r t i c l e i n f o",
            ),
            "scielo_scientia_agricola": ("Received",),
            "legacy_periodical": ("Received",),
        }
        markers = end_markers.get(extractor)
        if not markers:
            return None

        normalized_title = self._clean(title)
        start = clean_text.casefold().find(normalized_title.casefold())
        if start < 0:
            return None

        tail = clean_text[start + len(normalized_title) :].strip()
        positions = [
            tail.casefold().find(marker.casefold())
            for marker in markers
            if tail.casefold().find(marker.casefold()) >= 0
        ]
        if not positions:
            return None

        candidate = tail[: min(positions)].strip(" .,-")
        candidate = re.sub(r"^REVIEW\s+", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(
            r"\s+[a-e](?:,[a-e])*(?:,n)?(?=\s*[,;]|$)",
            "",
            candidate,
        )
        if extractor == "legacy_periodical":
            candidate = re.split(
                r"\s+\d+(?=[A-ZÀ-Ý])",
                candidate,
                maxsplit=1,
            )[0]
        candidate = self._clean(candidate)
        return candidate if self._author_candidate(candidate) else None

    @staticmethod
    def _source_url(
        bibliographic: dict[str, str | bool],
        doi: str | None,
    ) -> str | None:
        """Derive only publisher URLs that are deterministic from visible metadata."""
        visible_url = bibliographic.get("source_url")
        if isinstance(visible_url, str) and visible_url:
            return visible_url
        if not doi:
            return None
        extractor = str(bibliographic.get("extractor", ""))
        normalized = re.sub(
            r"^https?://(?:dx\.)?doi\.org/",
            "",
            doi.strip(),
            flags=re.IGNORECASE,
        )
        if extractor == "bmc_medicine":
            return f"https://bmcmedicine.biomedcentral.com/articles/{normalized}"
        return f"https://doi.org/{normalized}"

    def _bibliographic_fields(
        self,
        first_text: str,
        last_text: str,
        searchable_text: str,
        doi: str | None,
        page_count: int,
    ) -> dict[str, str | bool]:
        normalized = self._clean(first_text)
        combined = self._clean(searchable_text)

        monograph_record = self._monograph_catalog_record(searchable_text)
        if monograph_record:
            return {**monograph_record, "extractor": "monograph_catalog_record"}

        match = re.search(
            r"Global Sustainability Research.*?(?:Published:\s*\d{1,2}\s+\w+,\s*)?(?P<year>20\d{2})",
            combined,
            re.IGNORECASE,
        )
        if match and doi and "gssr.v" in doi.casefold():
            doi_parts = re.search(r"\.v(?P<volume>\d+)i(?P<issue>\d+)\.", doi, re.IGNORECASE)
            return {
                "journal": "Global Sustainability Research",
                "year": match.group("year"),
                "volume": doi_parts.group("volume") if doi_parts else "",
                "issue": doi_parts.group("issue") if doi_parts else "",
                "pages": f"1-{page_count}",
                "extractor": "global_sustainability_research",
            }

        match = re.search(
            r"BMC Medicine\s*\((?P<year>\d{4})\)\s*(?P<volume>\d+):(?P<article>\d+)",
            combined,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "BMC Medicine",
                "year": match.group("year"),
                "volume": match.group("volume"),
                "article_number": match.group("article"),
                "extractor": "bmc_medicine",
            }

        match = re.search(
            r"Environmental Chemistry Letters\s*\((?P<year>\d{4})\)\s*"
            r"(?P<volume>\d+):(?P<start>\d+)\s*[–-]\s*(?P<end>\d+)",
            combined,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "Environmental Chemistry Letters",
                "year": match.group("year"),
                "volume": match.group("volume"),
                "pages": f"{match.group('start')}-{match.group('end')}",
                "extractor": "springer_environmental_chemistry_letters",
            }

        match = re.search(
            r"Renewable and Sustainable Energy Reviews\s+(?P<volume>\d+)\s*"
            r"\((?P<year>\d{4})\)\s*(?P<start>\d+)\s*[–-]\s*(?P<end>\d+)",
            combined,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "Renewable and Sustainable Energy Reviews",
                "year": match.group("year"),
                "volume": match.group("volume"),
                "pages": f"{match.group('start')}-{match.group('end')}",
                "extractor": "elsevier_rser",
            }

        match = re.search(
            r"Sci\.\s*Agric\.\s*v\.?\s*(?P<volume>\d+),\s*n\.?\s*(?P<issue>\d+),\s*"
            r"p\.?\s*(?P<start>\d+)\s*[–-]\s*(?P<end>\d+),\s*"
            r"(?P<month>[A-Za-z]+(?:/[A-Za-z]+)?)\s*(?P<year>\d{4})",
            combined,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "Scientia Agricola",
                "place": "Piracicaba",
                "year": match.group("year"),
                "volume": match.group("volume"),
                "issue": match.group("issue"),
                "pages": f"{match.group('start')}-{match.group('end')}",
                "month": match.group("month"),
                "extractor": "scielo_scientia_agricola",
            }

        match = re.search(
            r"Acta Scientiarum\.\s*Agronomy\s+Maringá,?\s*v\.\s*"
            r"(?P<volume>\d+),\s*n\.\s*(?P<issue>\d+),\s*p\.\s*"
            r"(?P<start>\d+)\s*[–-]\s*(?P<end>\d+),\s*(?P<year>\d{4})",
            combined,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "Acta Scientiarum. Agronomy",
                "place": "Maringá",
                "volume": match.group("volume"),
                "issue": match.group("issue"),
                "pages": f"{match.group('start')}-{match.group('end')}",
                "year": match.group("year"),
                "extractor": "scielo_original",
            }

        match = re.search(
            r"Acta\s+Sci\.,?\s*Agron\.\s*(?P<volume>\d+)\s*"
            r"\((?P<issue>\d+)\)[^A-Za-zÀ-ÿ0-9]{0,12}"
            r"(?P<month>[A-Za-zÀ-ÿ]+)\s*(?P<year>\d{4})",
            combined,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "Acta Scientiarum. Agronomy",
                "place": "Maringá",
                "volume": match.group("volume"),
                "issue": match.group("issue"),
                "year": match.group("year"),
                "month": match.group("month"),
                "extractor": "scielo_browser_print",
            }

        match = re.search(
            r"Scientific Reports\s*\|\s*\((?P<year>\d{4})\)\s*"
            r"(?P<volume>\d+):(?P<article>\d+)",
            normalized,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "Scientific Reports",
                "year": match.group("year"),
                "volume": match.group("volume"),
                "article_number": match.group("article"),
                "extractor": "scientific_reports",
            }

        match = re.search(
            r"Plant Methods\s*\((?P<year>\d{4})\)\s*"
            r"(?P<volume>\d+):(?P<article>\d+)",
            normalized,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "Plant Methods",
                "year": match.group("year"),
                "volume": match.group("volume"),
                "article_number": match.group("article"),
                "extractor": "bmc_springer",
            }

        match = re.search(
            r"Sensors\s*&\s*Actuators:\s*A\.\s*Physical\s+"
            r"(?P<volume>\d+)\s*\((?P<year>\d{4})\)\s*"
            r"(?P<article>\d+)",
            normalized,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "Sensors & Actuators: A. Physical",
                "year": match.group("year"),
                "volume": match.group("volume"),
                "article_number": match.group("article"),
                "extractor": "elsevier",
            }

        match = re.search(
            r"Sensors\s+(?P<year>\d{4}),\s*(?P<volume>\d+),\s*"
            r"(?P<article>\d+)",
            normalized,
            re.IGNORECASE,
        )
        if match:
            result: dict[str, str | bool] = {
                "journal": "Sensors",
                "year": match.group("year"),
                "volume": match.group("volume"),
                "article_number": match.group("article"),
                "extractor": "mdpi",
            }
            if doi:
                doi_match = re.fullmatch(
                    r"10\.3390/s(?P<volume>\d{2})(?P<issue>\d{2})"
                    r"(?P<article>\d+)",
                    doi,
                )
                if doi_match and doi_match.group("volume") == match.group("volume"):
                    result["issue"] = str(int(doi_match.group("issue")))
                    result["issue_inferred"] = True
            return result

        ieee = re.search(
            r"VOLUME\s+(?P<volume>\d+),\s*(?P<year>\d{4})",
            normalized,
        )
        if ieee and ("IEEE" in normalized.upper() or "Digital Object Identifier" in normalized):
            first_numbers = re.findall(r"\b\d{5}\b", normalized)
            last_numbers = re.findall(r"\b\d{5}\b", self._clean(last_text))
            start = first_numbers[-1] if first_numbers else None
            end = last_numbers[-1] if last_numbers else None
            return {
                "journal": "IEEE Access",
                "year": ieee.group("year"),
                "volume": ieee.group("volume"),
                "pages": f"{start}-{end}" if start and end else start or "",
                "extractor": "ieee_access",
            }

        match = re.search(
            r"Euphytica\s+(?P<volume>\d+):\s*(?P<start>\d+)\s*"
            r"[–-]\s*(?P<end>\d+),\s*(?P<year>\d{4})",
            normalized,
            re.IGNORECASE,
        )
        if match:
            return {
                "journal": "Euphytica",
                "year": match.group("year"),
                "volume": match.group("volume"),
                "pages": f"{match.group('start')}-{match.group('end')}",
                "extractor": "legacy_periodical",
            }

        generic = generic_periodical_fields(
            first_text,
            searchable_text,
            doi=doi,
        )
        if generic:
            return generic

        year_match = YEAR_PATTERN.search(normalized)
        return {
            "year": year_match.group(0) if year_match else "",
            "extractor": "generic",
        }

    def _monograph_catalog_record(self, text: str) -> dict[str, str]:
        """Parse a conventional cataloging-in-publication block for a monograph."""
        lines = [self._clean(line) for line in text.splitlines() if self._clean(line)]
        header_index = next(
            (
                index
                for index, line in enumerate(lines)
                if "catalogacao na fonte" in self._matching_text(line)
            ),
            None,
        )
        if header_index is None:
            return {}

        block_lines = lines[header_index + 1 : header_index + 30]
        if not block_lines:
            return {}
        slash_index = next(
            (index for index, line in enumerate(block_lines) if "/" in line),
            None,
        )
        if slash_index is None:
            return {}

        author_index = None
        for index in range(slash_index - 1, -1, -1):
            line = block_lines[index]
            matching = self._matching_text(line)
            if any(
                marker in matching
                for marker in (
                    "biblioteca",
                    "catalogacao",
                    "ficha catalografica",
                )
            ):
                continue
            if line.endswith(".") and re.search(r"[A-Za-zÀ-ÿ]", line):
                author_index = index
                break
        if author_index is None:
            return {}

        title_lines = block_lines[author_index + 1 : slash_index + 1]
        title_text = " ".join(title_lines).split("/", 1)[0]
        title = re.sub(
            r"^[^A-Za-zÀ-ÿ0-9]{0,3}[A-Z]?\d{2,6}[a-z]?\s+",
            "",
            self._clean(title_text),
            flags=re.IGNORECASE,
        )
        if not title:
            return {}

        block = " ".join(block_lines)
        publication = re.search(
            r"[–—-]\s*(?P<place>[^:.;]{2,80})\s*:\s*"
            r"(?P<publisher>[^,.;]{2,120}),\s*(?P<year>\d{4})\.",
            block,
            re.IGNORECASE,
        )
        if publication is None:
            return {}

        result = {
            "title": title,
            "corporate_author": self._canonicalize_corporate_heading(block_lines[author_index]),
            "place": self._canonicalize_publication_place(publication.group("place")),
            "publisher": self._clean(publication.group("publisher")),
            "year": publication.group("year"),
        }
        pages = re.search(r"\b(?P<count>\d{1,5})\s+p\.", block, re.IGNORECASE)
        if pages:
            result["total_pages"] = pages.group("count")
        return result

    def _canonicalize_corporate_heading(self, value: str) -> str:
        cleaned = self._clean(value).rstrip(".")
        if "." not in cleaned:
            return cleaned
        jurisdiction, remainder = cleaned.split(".", 1)
        return f"{jurisdiction.upper()}.{remainder}"

    def _canonicalize_publication_place(self, value: str) -> str:
        cleaned = self._clean(value)
        match = re.fullmatch(
            r"(?P<city>[A-Za-zÀ-ÿ .'-]+)\s*[-–—]\s*(?P<state>[A-Z]{2})",
            cleaned,
        )
        if match:
            return f"{self._clean(match.group('city'))}, {match.group('state')}"
        return cleaned

    def _academic_fields(
        self,
        text: str,
        document_type: object,
        page_count: int,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        matching_text = self._matching_text(text)
        is_academic = document_type in {DocumentType.THESIS, DocumentType.DISSERTATION}

        # OCR frequently removes accents and may confuse c-cedilla with "g". These
        # patterns repair only the recognition signal; the canonical output remains
        # the official institution/city name, never the OCR spelling.
        mentions_ufv = bool(re.search(r"universidade federal de vi[csçg]osa", matching_text))
        if is_academic and mentions_ufv:
            result["institution"] = "Universidade Federal de Viçosa"

        department = re.search(
            r"Departamento de\s+([A-Za-zÀ-ÿ -]{3,80}?)(?=[.,\n]|\s+Programa|\s+\d{4})",
            text,
            re.IGNORECASE,
        )
        if department:
            department_name = self._clean(department.group(1))
            result["department"] = f"Departamento de {department_name}"

        if document_type is DocumentType.THESIS:
            result["degree"] = "Tese (Doutorado em Fitotecnia)"
        elif document_type is DocumentType.DISSERTATION:
            result["degree"] = "Dissertação (Mestrado em Fitotecnia)"

        degree = re.search(
            r"(Tese|Disserta(?:ç|c|g)[aãa]o)\s*\((Doutorado|Mestrado)\s+em\s+[^)]*\)",
            text,
            re.IGNORECASE,
        )
        if degree:
            result["degree"] = self._clean(degree.group(0))

        program = re.search(
            r"(?:programa de pos[- ]gradu(?:acao|agao)|pos[- ]gradu(?:acao|agao))\s+em\s+"
            r"([a-z ]+)",
            matching_text,
            re.IGNORECASE,
        )
        if program:
            result["program"] = self._clean(program.group(1))

        catalog_record = self._academic_catalog_record(text)
        if catalog_record.get("total_pages"):
            result["total_pages"] = catalog_record["total_pages"]
        else:
            pages = re.search(
                r"\b(?P<count>\d{2,4})\s*[f£](?=\s*[:.;)])",
                text,
                re.IGNORECASE,
            )
            if pages:
                result["total_pages"] = pages.group("count")
            elif is_academic:
                result["total_pages"] = str(page_count)

        catalog_place = catalog_record.get("place")
        if catalog_place:
            result["place"] = catalog_place
        elif is_academic and re.search(
            r"vi[csçg]osa\s*[-–—]\s*minas\s+gerais",
            matching_text,
            re.IGNORECASE,
        ):
            result["place"] = "Viçosa, MG"

        return result

    def _doi(
        self,
        internal: dict[str, str | None],
        pages: list[PageText],
    ) -> Evidence:
        searchable = "\n".join(
            value or "" for value in [internal.get("subject"), internal.get("title")]
        )
        searchable += "\n" + "\n".join(page.text for page in pages[:6])
        match = DOI_PATTERN.search(searchable)
        if not match:
            return Evidence(value=None, confidence=0, method="doi_regex")
        value = match.group(0).rstrip(".,;)")
        return Evidence(
            value=value,
            confidence=0.99,
            page_number=1,
            excerpt=match.group(0),
            method="doi_regex",
        )

    def _publication_month(
        self,
        text: str,
        year: object,
        provided: object = None,
    ) -> Evidence:
        if isinstance(provided, str) and provided:
            return Evidence(
                value=provided,
                confidence=0.9,
                page_number=1,
                excerpt=provided,
                method="publisher_header",
            )
        if not isinstance(year, str) or not year:
            return Evidence(
                value=None,
                confidence=0,
                method="publication_date_regex",
            )
        patterns = [
            r"Published:\s*\d{1,2}\s+(?P<month>[A-Za-z]+)\s+" + re.escape(year),
            r"date of publication\s+\d{1,2}\s+(?P<month>[A-Za-z]+)\s+" + re.escape(year),
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return Evidence(
                    value=match.group("month"),
                    confidence=0.96,
                    page_number=1,
                    excerpt=match.group(0),
                    method="publication_date_regex",
                )
        return Evidence(
            value=None,
            confidence=0,
            method="publication_date_regex",
        )

    def _place(self, text: str, provided: object = None) -> Evidence:
        if isinstance(provided, str) and provided:
            return Evidence(
                value=provided,
                confidence=0.92,
                page_number=1,
                excerpt=provided,
                method="publisher_profile",
            )
        if re.search(r"Brasília\s*[-–—]\s*DF", text, re.IGNORECASE):
            return Evidence(
                value="Brasília, DF",
                confidence=0.98,
                page_number=4,
                excerpt="Brasília - DF",
                method="institutional_imprint",
            )
        match = re.search(
            r"MDPI,\s*(?P<city>[A-Za-zÀ-ÿ -]+),\s*Switzerland",
            text,
        )
        if match:
            return Evidence(
                value=match.group("city").strip(),
                confidence=0.95,
                excerpt=match.group(0),
                method="publisher_footer",
            )
        return Evidence(
            value=None,
            confidence=0,
            method="not_present_in_pdf",
        )

    @staticmethod
    def _looks_mostly_uppercase(value: str) -> bool:
        letters = [character for character in value if character.isalpha()]
        if not letters:
            return False
        uppercase = sum(character.isupper() for character in letters)
        return uppercase / len(letters) >= 0.75

    @staticmethod
    def _matching_text(value: str) -> str:
        """Return accent-insensitive text used only for tolerant OCR matching."""
        normalized = unicodedata.normalize("NFKD", value)
        ascii_text = "".join(
            character for character in normalized if not unicodedata.combining(character)
        )
        return re.sub(r"\s+", " ", ascii_text.casefold()).strip()

    def _academic_catalog_record(self, text: str) -> dict[str, str]:
        """Parse a cataloging-in-publication record without title-specific rules."""
        clean_text = self._clean(text)
        result: dict[str, str] = {}

        slash_match = re.search(
            r"(?P<before>[^/]{20,900}?)\s*/\s*"
            r"(?P<author>[A-ZÀ-ÿ][^.]{4,160}?)\.\s*"
            r"[–—-]\s*(?P<place>[^,.;]{2,80},\s*[A-Z]{2}),\s*"
            r"(?P<year>\d{4})\.",
            clean_text,
            re.IGNORECASE,
        )
        if slash_match:
            title = self._catalog_title_tail(slash_match.group("before"))
            if title:
                result["title"] = title
            result["author"] = self._clean(slash_match.group("author"))
            result["place"] = self._canonicalize_academic_place(slash_match.group("place"))
            result["year"] = slash_match.group("year")

        pages = re.search(
            r"(?:tese|disserta(?:ç|c|g)[aãa]o)\s+eletr[ôo]nica\s*"
            r"\((?P<count>\d{2,4})\s*[f£]\.\)",
            clean_text,
            re.IGNORECASE,
        )
        if not pages:
            pages = re.search(
                r"\b(?P<count>\d{2,4})\s*[f£](?:\s+val)?(?=\s*[:.;)])",
                clean_text,
                re.IGNORECASE,
            )
        if pages:
            result["total_pages"] = pages.group("count")

        return result

    def _catalog_title_tail(self, value: str) -> str:
        """Remove generic catalog headers, author headings, and call numbers."""
        title = self._clean(value)
        title = re.sub(
            r"^Ficha catalogr[aá]fica elaborada pela Biblioteca Central"
            r"(?: da Universidade Federal de Vi(?:ç|c|g)osa"
            r"(?: - Campus Vi(?:ç|c|g)osa)?)?\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )
        author_heading = list(
            re.finditer(
                r"[A-ZÀ-ÿ][A-Za-zÀ-ÿ'’ -]+,\s*"
                r"[A-ZÀ-ÿ][A-Za-zÀ-ÿ'’ -]+[,.;]?\s*\d{4}-\s*",
                title,
            )
        )
        if author_heading:
            title = title[author_heading[-1].end() :]
        title = re.sub(
            r"^[^A-Za-zÀ-ÿ0-9]{0,3}(?:[A-Z]\s+)?[A-Z]?\d{2,6}[a-z]?\s+",
            "",
            title,
            flags=re.IGNORECASE,
        )
        # A cataloging column may inject the publication year between wrapped title
        # lines. Remove a leading/intermediate isolated copy only when the same year
        # is immediately followed by substantial title text.
        title = re.sub(r"^(?:18|19|20|21)\d{2}\s+(?=.{20,})", "", title)
        title = re.sub(
            r"(?<=\S)\s+(?:18|19|20|21)\d{2}\s+(?=[a-zà-ÿ].{15,})",
            " ",
            title,
            count=1,
            flags=re.IGNORECASE,
        )
        return self._clean(title)

    def _canonicalize_academic_place(self, value: str) -> str:
        cleaned = self._clean(value)
        normalized = self._matching_text(cleaned)
        if re.fullmatch(r"vi[csçg]osa,?\s*mg", normalized):
            return "Viçosa, MG"
        return cleaned

    def _academic_cover_title(self, text: str) -> str | None:
        lines = [self._clean(line) for line in text.splitlines() if self._clean(line)]
        if not lines:
            return None
        stop = next(
            (
                index
                for index, line in enumerate(lines)
                if re.match(
                    r"^(?:tese|disserta(?:c|g)ao)\b",
                    self._matching_text(line),
                    re.IGNORECASE,
                )
            ),
            None,
        )
        if stop is None:
            return None
        candidates = [line for line in lines[1:stop] if len(line) > 8]
        if not candidates:
            return None
        return self._clean(" ".join(candidates))

    def _academic_cover_author(self, text: str) -> str | None:
        lines = [self._clean(line) for line in text.splitlines() if self._clean(line)]
        for line in lines[:5]:
            if re.fullmatch(r"[A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s.'’-]{5,}", line):
                return line
        return None

    def _text_authors_after_title(self, title: str | None, text: str) -> str | None:
        if not title:
            return None
        clean_text = self._clean(text)
        normalized_title = self._clean(title)
        start = clean_text.casefold().find(normalized_title.casefold())
        if start < 0:
            return None
        tail = clean_text[start + len(normalized_title) :]
        cutoff_markers = (
            "Abstract",
            "Resumo",
            "Received",
            "Article history",
            "Keywords",
            "Acta Scientiarum",
            "BMC Medicine",
            "Environmental Chemistry Letters",
            "Renewable and Sustainable Energy Reviews",
            "Scientia Agricola",
        )
        cutoff = min(
            (
                tail.casefold().find(marker.casefold())
                for marker in cutoff_markers
                if tail.casefold().find(marker.casefold()) >= 0
            ),
            default=min(len(tail), 700),
        )
        candidate = tail[:cutoff].strip(" .,-")
        candidate = re.split(
            r"\b(?:Department|Universidade|University|Institute|Faculty|Laboratory)\b",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        candidate = re.sub(
            r"\s+[a-e](?:,[a-e])*(?=\s*[,;]|\s*$)",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = self._clean(candidate)
        if self._author_candidate(candidate):
            return candidate
        return None

    @staticmethod
    def _trustworthy_internal_title(value: str | None) -> bool:
        if not value:
            return False
        cleaned = value.strip()
        lowered = cleaned.casefold()
        if (
            len(cleaned) < 25
            or "..." in cleaned
            or "_" in cleaned
            or lowered.startswith("brasil -")
        ):
            return False
        return not (re.match(r"^\d+[_-]", cleaned) or cleaned.lower().endswith(".pdf"))

    @staticmethod
    def _trustworthy_internal_author(value: str | None) -> bool:
        if not value:
            return False
        cleaned = value.strip()
        lowered = cleaned.casefold()
        blocked = {"mrandreussi", "arleu juniior", "microsoft", "pdfcreator"}
        if lowered in blocked or "@" in cleaned or len(cleaned.split()) < 2:
            return False
        return len(parse_authors(cleaned)) >= 1

    def _scielo_title_from_layout(self, text: str) -> str | None:
        """Recover an Acta Scientiarum title between the issue header and author line."""
        lines = [self._clean(line) for line in text.splitlines() if self._clean(line)]
        header_index = next(
            (
                index
                for index, line in enumerate(lines)
                if re.search(
                    r"Maringá,?\s*v\.\s*\d+,\s*n\.\s*\d+,\s*p\.",
                    line,
                    re.IGNORECASE,
                )
            ),
            None,
        )
        if header_index is None:
            return None

        title_lines: list[str] = []
        for line in lines[header_index + 1 : header_index + 20]:
            if re.search(r"\d+\*?.*,.*\d+", line) and len(line) > 25:
                break
            if any(
                marker in line.casefold()
                for marker in (
                    "faculdade",
                    "departamento",
                    "autor para correspondência",
                    "resumo.",
                )
            ):
                break
            if len(line) >= 12:
                title_lines.append(line)

        unique: list[str] = []
        for line in title_lines:
            normalized = self._normalize(line)
            if not unique or normalized != self._normalize(unique[-1]):
                unique.append(line)

        # Multi-line titles may be repeated by the PDF producer. Keep one copy
        # of each normalized segment in first-seen order.
        deduplicated: list[str] = []
        seen: set[str] = set()
        for line in unique:
            normalized = self._normalize(line)
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduplicated.append(line)

        value = self._clean(" ".join(deduplicated))
        return value if self._title_candidate(value) else None

    def _scielo_title(self, text: str) -> str | None:
        """Backward-compatible alias for the generalized SciELO layout parser."""
        return self._scielo_title_from_layout(text)

    @staticmethod
    def _title_candidate(value: str) -> bool:
        lowered = value.casefold().strip()
        if not 25 <= len(value) <= 350:
            return False
        blocked = (
            "abstract",
            "resumo",
            "received",
            "available online",
            "doi:",
            "http://",
            "https://",
            "acta scientiarum",
            "universidade",
            "department",
            "faculdade",
            "review",
        )
        return not lowered.startswith(blocked) and "@" not in value

    @staticmethod
    def _author_candidate(value: str) -> bool:
        lowered = value.casefold()
        if len(value) > 450 or "@" in value:
            return False
        if any(
            token in lowered
            for token in (
                "universidade",
                "department",
                "faculdade",
                "abstract",
                "resumo",
            )
        ):
            return False
        return len(parse_authors(value)) >= 1

    @classmethod
    def _deduplicate_block(cls, value: str) -> str:
        lines = [cls._clean(line) for line in value.splitlines() if cls._clean(line)]
        unique: list[str] = []
        for line in lines:
            if not unique or cls._normalize(line) != cls._normalize(unique[-1]):
                unique.append(line)
        if not unique:
            return ""
        if len(set(cls._normalize(line) for line in unique)) == 1:
            return unique[0]
        joined = " ".join(unique)
        half = len(joined) // 2
        if half and cls._normalize(joined[:half]) == cls._normalize(joined[half:]):
            return joined[:half].strip()
        return joined

    @staticmethod
    def _evidence(
        value: object,
        confidence: float,
        method: str,
        page_number: int | None,
    ) -> Evidence:
        normalized = str(value).strip() if value not in {None, "", False} else None
        return Evidence(
            value=normalized,
            confidence=confidence if normalized else 0,
            page_number=page_number if normalized else None,
            excerpt=normalized,
            method=method,
        )

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            value.replace("\u00ad", "").replace("\u00a0", " ").replace("\u2011", "-"),
        ).strip()

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
        return re.sub(r"\W+", " ", ascii_text).casefold().strip()

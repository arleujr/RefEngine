from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import fitz

from refengine.domain.enums import ExtractionMethod
from refengine.domain.models import PageText
from refengine.domain.ports import OcrEngine
from refengine.infrastructure.pdf.tesseract_ocr import (
    OcrExecutableUnavailableError,
    OcrExecutionError,
    OcrLanguageUnavailableError,
    TesseractOcrEngine,
)

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Route each page to native extraction or local OCR.

    In metadata mode, native pages remain cheap to read, while image-only documents
    OCR only their first metadata pages. References depend on front matter,
    and this prevents a 400-page scanned manual from blocking the local folder workflow.
    """

    def __init__(
        self,
        minimum_native_characters: int = 80,
        ocr_engine: OcrEngine | None = None,
        metadata_ocr_page_limit: int | None = None,
        include_last_page_in_metadata_mode: bool = False,
    ) -> None:
        self._minimum_native_characters = minimum_native_characters
        self._ocr_engine = ocr_engine or TesseractOcrEngine()
        self._metadata_ocr_page_limit = metadata_ocr_page_limit
        self._include_last_page_in_metadata_mode = include_last_page_in_metadata_mode

    def cache_signature(self) -> str:
        """Return a deterministic fingerprint for extraction-affecting settings."""
        ocr_signature_method = getattr(self._ocr_engine, "cache_signature", None)
        ocr_signature: object
        if callable(ocr_signature_method):
            ocr_signature = ocr_signature_method()
        else:
            ocr_signature = {"engine": type(self._ocr_engine).__name__}
        payload = {
            "minimum_native_characters": self._minimum_native_characters,
            "metadata_ocr_page_limit": self._metadata_ocr_page_limit,
            "include_last_page_in_metadata_mode": (self._include_last_page_in_metadata_mode),
            "ocr": ocr_signature,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def process_pages(self, pdf_path: Path) -> list[PageText]:
        pages: list[PageText] = []
        with fitz.open(pdf_path) as document:
            page_count = document.page_count
            ocr_indexes = self._ocr_indexes(page_count)
            for index in range(page_count):
                page = document.load_page(index)
                text = page.get_text("text").strip()
                if len(text) >= self._minimum_native_characters:
                    pages.append(
                        PageText(
                            page_number=index + 1,
                            text=text,
                            method=ExtractionMethod.NATIVE,
                            character_count=len(text),
                        )
                    )
                    continue
                if self._metadata_ocr_page_limit is not None and index not in ocr_indexes:
                    pages.append(
                        PageText(
                            page_number=index + 1,
                            text="",
                            method=ExtractionMethod.SKIPPED,
                            character_count=0,
                            diagnostic_code="METADATA_MODE_SKIPPED",
                        )
                    )
                    continue
                pages.append(self._extract_with_ocr(pdf_path, index))
        logger.info("Processed %s pages from %s", len(pages), pdf_path.name)
        return pages

    def _ocr_indexes(self, page_count: int) -> set[int]:
        if self._metadata_ocr_page_limit is not None and self._metadata_ocr_page_limit <= 0:
            return set()
        if self._metadata_ocr_page_limit is None or page_count <= self._metadata_ocr_page_limit:
            return set(range(page_count))
        if not self._include_last_page_in_metadata_mode:
            return set(range(self._metadata_ocr_page_limit))
        front_count = max(1, self._metadata_ocr_page_limit - 1)
        return set(range(front_count)) | {page_count - 1}

    def _extract_with_ocr(self, pdf_path: Path, page_index: int) -> PageText:
        try:
            return self._ocr_engine.extract_page(pdf_path, page_index)
        except OcrExecutableUnavailableError:
            logger.warning("Tesseract is not available for page %s", page_index + 1)
            return PageText(
                page_number=page_index + 1,
                text="",
                method=ExtractionMethod.UNAVAILABLE,
                character_count=0,
                confidence=0,
                diagnostic_code="OCR_NOT_AVAILABLE",
            )
        except OcrLanguageUnavailableError as exc:
            logger.warning("OCR language data is unavailable for page %s: %s", page_index + 1, exc)
            return PageText(
                page_number=page_index + 1,
                text="",
                method=ExtractionMethod.UNAVAILABLE,
                character_count=0,
                confidence=0,
                diagnostic_code="OCR_LANGUAGE_MISSING",
            )
        except OcrExecutionError as exc:
            logger.warning("OCR failed for page %s: %s", page_index + 1, exc)
            return PageText(
                page_number=page_index + 1,
                text="",
                method=ExtractionMethod.UNAVAILABLE,
                character_count=0,
                confidence=0,
                diagnostic_code="OCR_FAILED",
            )

    @staticmethod
    def sha256(pdf_path: Path) -> str:
        digest = hashlib.sha256()
        with pdf_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

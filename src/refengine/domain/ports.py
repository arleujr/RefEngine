from __future__ import annotations

from pathlib import Path
from typing import Protocol

from refengine.domain.models import PageText, ProcessedDocument


class OcrEngine(Protocol):
    """Boundary for replaceable local OCR engines."""

    def extract_page(self, pdf_path: Path, page_index: int) -> PageText:
        """Return OCR text for one zero-based page index."""


class DocumentRepository(Protocol):
    """Persistence boundary for processed documents."""

    def save(self, document: ProcessedDocument) -> None:
        """Persist a processed document atomically."""

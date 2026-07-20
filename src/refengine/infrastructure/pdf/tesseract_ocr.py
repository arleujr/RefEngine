from __future__ import annotations

import csv
import logging
import subprocess
import tempfile
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageOps

from refengine.domain.enums import ExtractionMethod
from refengine.domain.models import PageText
from refengine.services.environment import (
    _decode_subprocess_output,
    find_tessdata_directory,
    find_tesseract_command,
    preferred_ocr_language_spec,
)

logger = logging.getLogger(__name__)


class OcrExecutableUnavailableError(RuntimeError):
    """Raised when the configured Tesseract executable does not exist."""


class OcrLanguageUnavailableError(RuntimeError):
    """Raised when Portuguese/English language data is unavailable."""


class OcrExecutionError(RuntimeError):
    """Raised when Tesseract returns a non-zero exit status."""

    def __init__(self, return_code: int, message: str) -> None:
        self.return_code = return_code
        self.message = message.strip() or "Tesseract failed without an error message."
        super().__init__(f"Tesseract exited with code {return_code}: {self.message}")


class TesseractOcrEngine:
    """Run Tesseract directly and parse its TSV output deterministically.

    This adapter intentionally does not use pytesseract. Pytesseract decodes
    Tesseract stderr as UTF-8 internally, which crashes on localized Windows
    installations that emit CP1252/CP850 messages.
    """

    def __init__(
        self,
        languages: str | None = None,
        dpi: int = 180,
        page_segmentation_mode: int = 3,
        timeout_seconds: int = 90,
        command: Path | None = None,
        tessdata_directory: Path | None = None,
    ) -> None:
        self._dpi = dpi
        self._page_segmentation_mode = page_segmentation_mode
        self._timeout_seconds = timeout_seconds
        self._command = command or find_tesseract_command()
        self._tessdata_directory = tessdata_directory or find_tessdata_directory(self._command)
        self._languages = languages or preferred_ocr_language_spec(
            self._command,
            self._tessdata_directory,
        )

    def smoke_test(self) -> None:
        """Execute the configured engine against a generated local image."""
        image = Image.new("L", (120, 60), color=255)
        self._extract_image_data(image)

    def cache_signature(self) -> dict[str, object]:
        """Return OCR settings that materially affect extracted page text."""
        traineddata: list[dict[str, object]] = []
        if self._tessdata_directory is not None and self._tessdata_directory.is_dir():
            for model in sorted(self._tessdata_directory.glob("*.traineddata")):
                try:
                    stat = model.stat()
                except OSError:
                    continue
                traineddata.append(
                    {
                        "name": model.name,
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    }
                )
        return {
            "engine": "tesseract_cli",
            "dpi": self._dpi,
            "page_segmentation_mode": self._page_segmentation_mode,
            "languages": self._languages,
            "traineddata": traineddata,
        }

    def extract_page(self, pdf_path: Path, page_index: int) -> PageText:
        image = self._render_page(pdf_path, page_index)
        data = self._extract_image_data(image)
        text = reconstruct_ocr_lines(data)
        confidence = mean_ocr_confidence(data)

        logger.info(
            "OCR completed for page %s with confidence %.2f using %s at %s DPI",
            page_index + 1,
            confidence,
            self._languages,
            self._dpi,
        )
        return PageText(
            page_number=page_index + 1,
            text=text,
            method=ExtractionMethod.OCR,
            character_count=len(text),
            confidence=confidence,
        )

    def _extract_image_data(
        self,
        image: Image.Image,
    ) -> dict[str, list[Any]]:
        command = self._validated_command()
        languages = self._validated_languages()

        with tempfile.TemporaryDirectory(prefix="refengine-ocr-") as temporary:
            temporary_directory = Path(temporary)
            input_path = temporary_directory / "page.png"
            output_base = temporary_directory / "result"
            output_tsv = output_base.with_suffix(".tsv")
            image.save(input_path, format="PNG")

            arguments = build_tesseract_arguments(
                command=command,
                input_path=input_path,
                output_base=output_base,
                languages=languages,
                page_segmentation_mode=self._page_segmentation_mode,
                tessdata_directory=self._tessdata_directory,
            )

            try:
                completed = subprocess.run(
                    arguments,
                    check=False,
                    capture_output=True,
                    text=False,
                    timeout=self._timeout_seconds,
                    creationflags=_windows_no_window_flag(),
                )
            except FileNotFoundError as exc:
                raise OcrExecutableUnavailableError(
                    f"Tesseract executable was not found: {command}"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise OcrExecutionError(
                    -1,
                    f"Tesseract timed out after {self._timeout_seconds} seconds.",
                ) from exc
            except OSError as exc:
                raise OcrExecutionError(-1, str(exc)) from exc

            if completed.returncode != 0:
                error_output = _decode_subprocess_output(
                    completed.stderr or completed.stdout or b""
                )
                raise OcrExecutionError(
                    completed.returncode,
                    error_output,
                )

            if not output_tsv.is_file():
                diagnostic = _decode_subprocess_output(completed.stderr or completed.stdout or b"")
                raise OcrExecutionError(
                    completed.returncode,
                    diagnostic or "Tesseract did not create TSV output.",
                )

            payload = output_tsv.read_bytes()
            return parse_tesseract_tsv(payload)

    def _validated_command(self) -> Path:
        if self._command is None or not self._command.is_file():
            raise OcrExecutableUnavailableError("Tesseract executable is unavailable.")
        return self._command

    def _validated_languages(self) -> str:
        if self._languages is None:
            raise OcrLanguageUnavailableError(
                "Tesseract exists, but por/eng traineddata is unavailable."
            )
        return self._languages

    def _render_page(self, pdf_path: Path, page_index: int) -> Image.Image:
        with fitz.open(pdf_path) as document:
            if page_index < 0 or page_index >= document.page_count:
                raise IndexError(
                    f"Page {page_index + 1} is outside a {document.page_count}-page PDF."
                )
            page = document.load_page(page_index)
            scale = self._dpi / 72
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                alpha=False,
            )

        image = Image.frombytes(
            "RGB",
            (pixmap.width, pixmap.height),
            pixmap.samples,
        )
        grayscale = ImageOps.grayscale(image)
        return ImageOps.autocontrast(grayscale)


def build_tesseract_arguments(
    *,
    command: Path,
    input_path: Path,
    output_base: Path,
    languages: str,
    page_segmentation_mode: int,
    tessdata_directory: Path | None,
) -> list[str]:
    """Build a TSV command without depending on tessdata/configs/tsv.

    The positional config name ``tsv`` is resolved relative to the selected
    tessdata directory. RefEngine deliberately stores only traineddata models,
    so TSV is enabled through the runtime parameter instead.
    """
    arguments = [
        str(command),
        str(input_path),
        str(output_base),
        "-l",
        languages,
        "--oem",
        "1",
        "--psm",
        str(page_segmentation_mode),
    ]
    if tessdata_directory is not None:
        arguments.extend(
            [
                "--tessdata-dir",
                str(tessdata_directory),
            ]
        )
    arguments.extend(
        [
            "-c",
            "tessedit_create_tsv=1",
        ]
    )
    return arguments


def parse_tesseract_tsv(payload: bytes) -> dict[str, list[Any]]:
    """Parse UTF-8 TSV emitted by Tesseract into a column-oriented mapping."""
    text = payload.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(StringIO(text), delimiter="\t")
    if reader.fieldnames is None:
        raise OcrExecutionError(0, "Tesseract TSV has no header.")

    data: dict[str, list[Any]] = {field: [] for field in reader.fieldnames}
    for row in reader:
        for field in reader.fieldnames:
            data[field].append(row.get(field, ""))
    return data


def reconstruct_ocr_lines(data: dict[str, list[Any]]) -> str:
    """Rebuild line breaks from one Tesseract TSV result."""
    lines: defaultdict[tuple[int, int, int, int], list[str]] = defaultdict(list)
    total = len(data.get("text", []))
    for index in range(total):
        word = str(data["text"][index]).strip()
        if not word:
            continue
        key = (
            _safe_int(_column_value(data, "page_num", index, 1), 1),
            _safe_int(_column_value(data, "block_num", index, 0), 0),
            _safe_int(_column_value(data, "par_num", index, 0), 0),
            _safe_int(_column_value(data, "line_num", index, 0), 0),
        )
        lines[key].append(word)
    return "\n".join(" ".join(words) for _, words in sorted(lines.items()) if words)


def mean_ocr_confidence(data: dict[str, list[Any]]) -> float:
    values: list[float] = []
    for raw in data.get("conf", []):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            values.append(value)
    if not values:
        return 0.0
    return max(0.0, min(sum(values) / len(values) / 100, 1.0))


def _column_value(
    data: dict[str, list[Any]],
    column: str,
    index: int,
    default: Any,
) -> Any:
    values = data.get(column, [])
    if index >= len(values):
        return default
    return values[index]


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _windows_no_window_flag() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

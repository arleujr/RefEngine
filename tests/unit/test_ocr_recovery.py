from pathlib import Path

from refengine.domain.enums import ExtractionMethod
from refengine.infrastructure.pdf.document_processor import DocumentProcessor
from refengine.infrastructure.pdf.tesseract_ocr import OcrLanguageUnavailableError


class MissingLanguageOcr:
    def extract_page(self, pdf_path: Path, page_index: int):
        raise OcrLanguageUnavailableError("missing por/eng")


def test_missing_ocr_languages_are_recoverable(tmp_path: Path) -> None:
    import fitz

    path = tmp_path / "image.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    pages = DocumentProcessor(ocr_engine=MissingLanguageOcr()).process_pages(path)

    assert pages[0].method is ExtractionMethod.UNAVAILABLE
    assert pages[0].diagnostic_code == "OCR_LANGUAGE_MISSING"

from pathlib import Path

from refengine.domain.enums import ExtractionMethod
from refengine.infrastructure.pdf.document_processor import DocumentProcessor
from refengine.infrastructure.pdf.tesseract_ocr import OcrExecutionError


class FailingOcr:
    def extract_page(self, pdf_path: Path, page_index: int):
        raise OcrExecutionError(1, "localized engine failure")


def test_ocr_engine_failure_is_reported_per_page(
    tmp_path: Path,
) -> None:
    import fitz

    pdf_path = tmp_path / "scan.pdf"
    document = fitz.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    processor = DocumentProcessor(
        ocr_engine=FailingOcr(),
        metadata_ocr_page_limit=1,
    )
    pages = processor.process_pages(pdf_path)

    assert pages[0].method is ExtractionMethod.UNAVAILABLE
    assert pages[0].diagnostic_code == "OCR_FAILED"

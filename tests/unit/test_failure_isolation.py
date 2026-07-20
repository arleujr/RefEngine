from pathlib import Path

from refengine.application.ingest_folder import IngestFolder
from refengine.domain.enums import ErrorCode, ProcessingStatus


def test_failed_pdf_uses_specific_processing_error(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not a pdf")

    document = IngestFolder._failed_document(source, ValueError("broken"))

    assert document.status is ProcessingStatus.FAILED
    assert document.errors == [ErrorCode.SOURCE_PROCESSING_FAILED]

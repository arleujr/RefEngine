from pathlib import Path

from refengine.infrastructure.pdf.tesseract_ocr import (
    build_tesseract_arguments,
)


def test_tsv_mode_does_not_require_tessdata_configs_directory(
    tmp_path: Path,
) -> None:
    command = tmp_path / "tesseract.exe"
    input_path = tmp_path / "page.png"
    output_base = tmp_path / "result"
    tessdata = tmp_path / "tessdata"

    arguments = build_tesseract_arguments(
        command=command,
        input_path=input_path,
        output_base=output_base,
        languages="por+eng",
        page_segmentation_mode=3,
        tessdata_directory=tessdata,
    )

    assert arguments[-2:] == ["-c", "tessedit_create_tsv=1"]
    assert "tsv" not in arguments
    assert arguments[arguments.index("--tessdata-dir") + 1] == str(tessdata)

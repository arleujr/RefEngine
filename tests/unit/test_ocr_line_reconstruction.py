from refengine.infrastructure.pdf.tesseract_ocr import (
    mean_ocr_confidence,
    reconstruct_ocr_lines,
)


def test_reconstructs_lines_from_single_tesseract_result() -> None:
    data = {
        "text": ["Title", "line", "", "Author", "Name"],
        "conf": ["95", "90", "-1", "80", "85"],
        "page_num": [1, 1, 1, 1, 1],
        "block_num": [1, 1, 1, 2, 2],
        "par_num": [1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 1, 1],
    }

    assert reconstruct_ocr_lines(data) == "Title line\nAuthor Name"
    assert mean_ocr_confidence(data) == 0.875

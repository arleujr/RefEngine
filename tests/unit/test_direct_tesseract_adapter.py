from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from refengine.infrastructure.pdf.tesseract_ocr import (
    OcrExecutionError,
    TesseractOcrEngine,
    parse_tesseract_tsv,
)


def test_parses_tesseract_tsv() -> None:
    payload = (
        b"level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        b"left\ttop\twidth\theight\tconf\ttext\n"
        b"5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t95\tTitle\n"
    )

    data = parse_tesseract_tsv(payload)

    assert data["text"] == ["Title"]
    assert data["conf"] == ["95"]


def test_non_utf8_stderr_is_decoded_without_pytesseract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    command = tmp_path / "tesseract.exe"
    command.write_bytes(b"fixture")
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "por.traineddata").write_bytes(b"fixture")
    (tessdata / "eng.traineddata").write_bytes(b"fixture")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=b"",
            stderr="Erro em Programação".encode("cp1252"),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    engine = TesseractOcrEngine(
        command=command,
        tessdata_directory=tessdata,
        languages="por+eng",
    )

    with pytest.raises(OcrExecutionError) as captured:
        engine._extract_image_data(Image.new("L", (10, 10), color=255))

    assert "Programação" in str(captured.value)

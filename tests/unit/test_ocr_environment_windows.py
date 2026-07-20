from pathlib import Path

from refengine.services.environment import (
    _decode_subprocess_output,
    available_tesseract_languages,
)


def test_decodes_cp1252_tesseract_output_without_unicode_error() -> None:
    payload = "versão em português".encode("cp1252")

    assert _decode_subprocess_output(payload) == "versão em português"


def test_configured_traineddata_files_are_language_source_of_truth(
    tmp_path: Path,
) -> None:
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "por.traineddata").write_bytes(b"por")
    (tessdata / "eng.traineddata").write_bytes(b"eng")
    (tessdata / "osd.traineddata").write_bytes(b"osd")

    assert available_tesseract_languages(
        command=None,
        tessdata_directory=tessdata,
    ) == ["eng", "osd", "por"]

import json
from pathlib import Path

from refengine.services.environment import (
    find_tessdata_directory,
    load_ocr_config,
)


def test_reads_project_local_ocr_configuration(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    tessdata = tmp_path / "tools" / "tesseract" / "tessdata"
    config_dir.mkdir()
    tessdata.mkdir(parents=True)
    (tessdata / "por.traineddata").write_bytes(b"fixture")
    (config_dir / "ocr.json").write_text(
        json.dumps({"tessdata_directory": str(tessdata)}),
        encoding="utf-8",
    )

    assert load_ocr_config(tmp_path)["tessdata_directory"] == str(tessdata)
    assert find_tessdata_directory(project_root=tmp_path) == tessdata.resolve()


def test_reads_powershell_utf8_bom_configuration(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    payload = json.dumps({"tesseract_command": r"C:\Program Files\Tesseract-OCR\tesseract.exe"})
    (config_dir / "ocr.json").write_bytes(b"\xef\xbb\xbf" + payload.encode("utf-8"))

    config = load_ocr_config(tmp_path)

    assert config["tesseract_command"].endswith("tesseract.exe")

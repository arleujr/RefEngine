from pathlib import Path

from refengine.services.input_inventory import build_input_inventory


def test_input_inventory_includes_ris_files(tmp_path: Path) -> None:
    (tmp_path / "article.ris").write_text(
        "TY  - JOUR\nTI  - Example\nER  -\n",
        encoding="utf-8",
    )

    inventory = build_input_inventory(tmp_path)

    assert [(item.relative_path, item.source_type) for item in inventory.files] == [
        ("article.ris", "ris")
    ]

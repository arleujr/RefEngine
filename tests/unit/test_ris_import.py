from pathlib import Path

from refengine.services.ris import metadata_from_ris, parse_ris_file

RIS = """TY  - JOUR
ID  - INGRAO2015
AU  - Ingrao, Carlo
AU  - Lo Giudice, Agata
TI  - Energy and environmental assessment of industrial hemp for building applications: A review
JF  - Renewable and Sustainable Energy Reviews
VL  - 51
SP  - 29
EP  - 42
PY  - 2015
DO  - 10.1016/j.rser.2015.06.002
UR  - https://www.sciencedirect.com/science/article/pii/S1364032115005729
N1  - First line
      continued note
ER  -
"""


def test_parses_ris_article_and_continuation_lines(tmp_path: Path) -> None:
    path = tmp_path / "article.ris"
    path.write_text(RIS, encoding="utf-8")

    entries = parse_ris_file(path)
    metadata = metadata_from_ris(entries[0])

    assert len(entries) == 1
    assert entries[0].fields["N1"] == ["First line continued note"]
    assert [author.family_name for author in metadata.authors] == [
        "Ingrao",
        "Lo Giudice",
    ]
    assert metadata.title.value.endswith(": A review")
    assert metadata.journal.value == "Renewable and Sustainable Energy Reviews"
    assert metadata.pages.value == "29-42"
    assert metadata.doi.value == "10.1016/j.rser.2015.06.002"


def test_parses_multiple_ris_records(tmp_path: Path) -> None:
    path = tmp_path / "records.ris"
    path.write_text(
        "TY  - BOOK\nID  - one\nTI  - First book\nER  -\n"
        "TY  - THES\nID  - two\nTI  - Second work\nER  -\n",
        encoding="utf-8",
    )

    entries = parse_ris_file(path)

    assert [entry.key for entry in entries] == ["one", "two"]
    assert [entry.entry_type for entry in entries] == ["BOOK", "THES"]


def test_parses_ris_tags_with_leading_whitespace(tmp_path: Path) -> None:
    path = tmp_path / "indented.ris"
    path.write_text(
        "  TY  - JOUR\n  TI  - Indented export\n  PY  - 2025\n  ER  -\n",
        encoding="utf-8",
    )

    entries = parse_ris_file(path)

    assert entries[0].title == "Indented export"

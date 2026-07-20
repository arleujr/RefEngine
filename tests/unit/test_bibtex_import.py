from pathlib import Path

from refengine.services.bibtex import (
    metadata_from_bibtex,
    normalize_doi,
    parse_bibtex_file,
)

BIBTEX = r"""
@article{INGRAO201529,
  title = {Energy and environmental assessment of industrial hemp for building applications: A review},
  journal = {Renewable and Sustainable Energy Reviews},
  volume = {51},
  pages = {29-42},
  year = {2015},
  doi = {https://doi.org/10.1016/j.rser.2015.06.002},
  url = {https://www.sciencedirect.com/science/article/pii/S1364032115005729},
  author = {Carlo Ingrao and Agata {Lo Giudice} and Jacopo Bacenetti}
}
"""


def test_parses_common_publisher_bibtex(tmp_path: Path) -> None:
    path = tmp_path / "article.bib"
    path.write_text(BIBTEX, encoding="utf-8")

    entries = parse_bibtex_file(path)
    metadata = metadata_from_bibtex(entries[0])

    assert len(entries) == 1
    assert metadata.title.value.endswith(": A review")
    assert metadata.journal.value == "Renewable and Sustainable Energy Reviews"
    assert metadata.doi.value == "10.1016/j.rser.2015.06.002"
    assert metadata.url.value.endswith("S1364032115005729")
    assert [author.family_name for author in metadata.authors] == [
        "Ingrao",
        "Lo Giudice",
        "Bacenetti",
    ]


def test_normalizes_doi_url() -> None:
    assert normalize_doi("https://doi.org/10.1000/example.") == "10.1000/example"


def test_discovers_bib_and_bibtex_extensions_case_insensitively(tmp_path: Path) -> None:
    from refengine.services.bibtex import discover_bibtex

    (tmp_path / "first.BIB").write_text(BIBTEX, encoding="utf-8")
    (tmp_path / "second.bibtex").write_text(BIBTEX, encoding="utf-8")

    discovered = discover_bibtex(tmp_path)

    assert [path.name for path in discovered] == ["first.BIB", "second.bibtex"]

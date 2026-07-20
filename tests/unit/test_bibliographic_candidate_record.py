from pathlib import Path

from refengine.domain.bibliography import SourceFormat
from refengine.rules.catalog import load_ufv_2025_catalog
from refengine.services.bibliographic_record import (
    merge_records,
    record_from_bibtex,
    record_from_ris,
)
from refengine.services.bibtex import parse_bibtex_file
from refengine.services.ris import parse_ris_file

BIBTEX = r"""@article{sample,
  author = {Carlo Ingrao and Agata {Lo Giudice}},
  title = {Energy and environmental assessment},
  journal = {Renewable and Sustainable Energy Reviews},
  year = {2015},
  doi = {10.1016/example},
  abstract = {This field is intentionally ignored.}
}
"""

RIS = """TY  - JOUR
ID  - sample-ris
AU  - Ingrao, Carlo
TI  - Energy and environmental assessment
JF  - Renewable and Sustainable Energy Reviews
PY  - 2015
DO  - 10.1016/example
KW  - hemp
ER  -
"""


def test_bibtex_record_preserves_candidates_and_raw_fields(tmp_path: Path) -> None:
    path = tmp_path / "sample.bib"
    path.write_text(BIBTEX, encoding="utf-8")
    record = record_from_bibtex(parse_bibtex_file(path)[0])

    assert {candidate.field_id for candidate in record.field_candidates} >= {
        "authors",
        "title",
        "periodical_title",
        "publication_year",
        "doi",
    }
    assert all(candidate.raw_field_name != "abstract" for candidate in record.field_candidates)
    assert any(candidate.schema_id == "ufv.22" for candidate in record.document_type_candidates)


def test_merges_bibtex_and_ris_without_losing_source_provenance(tmp_path: Path) -> None:
    bib_path = tmp_path / "sample.bib"
    ris_path = tmp_path / "sample.ris"
    bib_path.write_text(BIBTEX, encoding="utf-8")
    ris_path.write_text(RIS, encoding="utf-8")

    merged = merge_records(
        record_from_bibtex(parse_bibtex_file(bib_path)[0]),
        record_from_ris(parse_ris_file(ris_path)[0]),
    )

    assert merged is not None
    title_candidates = merged.candidates_for("title")
    assert {candidate.source_format for candidate in title_candidates} == {
        SourceFormat.BIBTEX,
        SourceFormat.RIS,
    }
    assert set(merged.source_files) == {"sample.bib", "sample.ris"}
    assert all(candidate.raw_field_name != "KW" for candidate in merged.field_candidates)


def test_every_candidate_field_is_registered_in_normative_catalog(tmp_path: Path) -> None:
    path = tmp_path / "sample.bib"
    path.write_text(BIBTEX, encoding="utf-8")
    record = record_from_bibtex(parse_bibtex_file(path)[0])
    known = {field.id for field in load_ufv_2025_catalog().fields}

    assert {candidate.field_id for candidate in record.field_candidates} <= known

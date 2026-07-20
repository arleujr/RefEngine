from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/refengine"


def test_no_citation_or_tcc_runtime_contract() -> None:
    models = (SOURCE / "domain/models.py").read_text(encoding="utf-8")
    formatter = (SOURCE / "services/reference_formatter.py").read_text(encoding="utf-8")
    assert "generated_citation" not in models
    assert "parenthetical_citation" not in formatter
    assert not (ROOT / "rules/ufv_2025/citations.yaml").exists()
    assert not (ROOT / "template").exists() or not any((ROOT / "template").iterdir())


def test_candidate_ledger_keeps_only_catalog_fields() -> None:
    bibliography = (SOURCE / "domain/bibliography.py").read_text(encoding="utf-8")
    record = (SOURCE / "services/bibliographic_record.py").read_text(encoding="utf-8")
    assert "RawSourceField" not in bibliography
    assert "raw_source_fields" not in record


def test_no_fixture_specific_bibliography_in_production_code() -> None:
    forbidden = (
        "10.1590/0103-9016-2015-0007",
        "10.1016/j.rser.2015.06.002",
        "Energy and environmental assessment of industrial hemp",
        "Seed vigor testing: an overview",
    )
    production = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE.rglob("*.py"))
    for value in forbidden:
        assert value not in production

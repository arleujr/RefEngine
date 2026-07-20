import json
from datetime import UTC, datetime
from pathlib import Path

from refengine.domain.enums import DocumentType, ProcessingStatus, VariantType
from refengine.domain.models import ArticleMetadata, Evidence, ProcessedDocument
from refengine.infrastructure.export.run_manifest_exporter import export_run_manifest
from refengine.services.input_inventory import build_input_inventory


def evidence(value: str | None) -> Evidence:
    return Evidence(value=value, confidence=1.0 if value else 0.0, method="test")


def test_manifest_hashes_inputs_and_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "source.bib").write_text("@article{x, title={T}}", encoding="utf-8")
    (output_dir / "references_ufv.txt").write_text("Reference\n", encoding="utf-8")
    metadata = ArticleMetadata(
        title=evidence("Title"),
        authors=[],
        authors_evidence=evidence(None),
        journal=evidence("Journal"),
        place=evidence(None),
        year=evidence("2024"),
        publication_month=evidence(None),
        volume=evidence("1"),
        issue=evidence(None),
        pages=evidence("1-2"),
        article_number=evidence(None),
        doi=evidence(None),
        url=evidence(None),
        extractor="test",
        document_type=DocumentType.JOURNAL_ARTICLE,
    )
    document = ProcessedDocument(
        source_path=input_dir / "source.bib",
        sha256="b" * 64,
        pages=[],
        metadata=metadata,
        status=ProcessingStatus.PROCESSED,
        generated_reference="Reference",
        variant_type=VariantType.BIBTEX,
    )
    now = datetime.now(UTC)

    manifest_path = export_run_manifest(
        [document],
        output_dir,
        run_id="run-test",
        command="ingest",
        started_at=now,
        finished_at=now,
        inventory=build_input_inventory(input_dir),
        settings={},
        cache_stats={"hits": 1, "misses": 0, "writes": 0},
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-test"
    assert payload["input"]["files"][0]["relative_path"] == "source.bib"
    assert payload["processing"]["cache"]["hits"] == 1
    assert payload["outputs"][0]["sha256"]

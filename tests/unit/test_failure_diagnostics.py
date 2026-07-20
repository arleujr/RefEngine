import json
from pathlib import Path

from refengine.application.ingest_folder import IngestFolder
from refengine.infrastructure.export.failure_exporter import export_failures


def test_failed_source_has_sanitized_incident_and_export(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"broken")
    document = IngestFolder._failed_document(
        source,
        ValueError(f"Could not open {tmp_path}/broken.pdf"),
    )

    assert document.incident is not None
    assert document.incident.phase == "pdf_processing"
    assert "<input>" in document.incident.message

    output = tmp_path / "failures.json"
    export_failures([document], output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["failed_sources"] == 1
    assert payload["failures"][0]["incident"]["incident_id"]

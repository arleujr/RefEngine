from __future__ import annotations

import json
from pathlib import Path

from refengine.domain.models import ProcessedDocument


def export_failures(documents: list[ProcessedDocument], output_path: Path) -> None:
    """Export sanitized per-source failures without exposing stack traces."""
    failures = []
    for document in documents:
        if document.incident is None and document.status.value != "failed":
            continue
        failures.append(
            {
                "source_file": document.source_path.name,
                "sha256": document.sha256,
                "status": document.status.value,
                "error_codes": [error.value for error in document.errors],
                "incident": (
                    document.incident.model_dump(mode="json")
                    if document.incident is not None
                    else None
                ),
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "failed_sources": len(failures),
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

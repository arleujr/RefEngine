from __future__ import annotations

import json
from pathlib import Path

from refengine.domain.models import ProcessedDocument


def export_resolved_bibliography(
    documents: list[ProcessedDocument],
    output_path: Path,
) -> None:
    """Export field-by-field selections, conflicts, and missing UFV fields."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "source_path": str(document.source_path),
            "sha256": document.sha256,
            "canonical_key": document.canonical_key,
            "include_in_output": document.include_in_output,
            "resolved": (
                document.resolved_bibliography.model_dump(mode="json")
                if document.resolved_bibliography is not None
                else None
            ),
        }
        for document in documents
    ]
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

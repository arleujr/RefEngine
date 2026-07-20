from __future__ import annotations

import json
from pathlib import Path

from refengine.domain.models import ProcessedDocument


def export_bibliographic_candidates(
    documents: list[ProcessedDocument],
    output_path: Path,
) -> None:
    """Export source-neutral candidate ledgers without choosing final values."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "source_path": str(document.source_path),
            "sha256": document.sha256,
            "canonical_key": document.canonical_key,
            "record": (
                document.bibliographic_record.model_dump(mode="json")
                if document.bibliographic_record is not None
                else None
            ),
        }
        for document in documents
    ]
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

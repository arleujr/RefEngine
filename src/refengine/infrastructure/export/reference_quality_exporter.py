from __future__ import annotations

import json
from pathlib import Path

from refengine.domain.models import ProcessedDocument
from refengine.services.reference_quality import build_reference_quality_report


def export_reference_quality(
    documents: list[ProcessedDocument],
    output_path: Path,
) -> None:
    """Write the final/draft/blocking decision for every physical document."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            build_reference_quality_report(documents),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

from __future__ import annotations

import json
from pathlib import Path

from refengine.domain.models import ProcessedDocument


def export_json(documents: list[ProcessedDocument], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [document.model_dump(mode="json") for document in documents]
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

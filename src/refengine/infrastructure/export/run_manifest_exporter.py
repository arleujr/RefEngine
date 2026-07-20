from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from refengine import __version__
from refengine.domain.models import ProcessedDocument
from refengine.services.input_inventory import InputInventory, sha256_file
from refengine.services.reference_quality import build_reference_quality_report


def export_run_manifest(
    documents: list[ProcessedDocument],
    output_directory: Path,
    *,
    run_id: str,
    command: str,
    started_at: datetime,
    finished_at: datetime,
    inventory: InputInventory | None,
    settings: dict[str, Any],
    cache_stats: dict[str, int] | None = None,
) -> Path:
    """Write a local reproducibility manifest for one completed run."""
    quality = build_reference_quality_report(documents)
    output_files = []
    for path in sorted(output_directory.rglob("*")):
        if not path.is_file() or path.name == "run_manifest.json":
            continue
        output_files.append(
            {
                "path": path.relative_to(output_directory).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    identified_works = {
        item.canonical_key or f"sha256:{item.sha256}"
        for item in documents
        if item.status.value != "failed"
    }
    final_references = sum(
        bool(item.generated_reference and item.include_in_output) for item in documents
    )
    payload = {
        "schema_version": 2,
        "run_id": run_id,
        "refengine_version": __version__,
        "command": command,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": max(0.0, (finished_at - started_at).total_seconds()),
        "settings": settings,
        "input": inventory.as_dict() if inventory is not None else None,
        "processing": {
            "physical_documents": len(documents),
            "failed_sources": sum(item.status.value == "failed" for item in documents),
            "identified_works": len(identified_works),
            "final_references": final_references,
            "ready_references": quality["ready_references"],
            "review_required_references": quality["review_required_references"],
            "blocked_references": quality["blocked_references"],
            "native_pages": sum(item.native_page_count for item in documents),
            "ocr_pages": sum(item.ocr_page_count for item in documents),
            "unavailable_pages": sum(item.unavailable_page_count for item in documents),
            "cache": cache_stats or {"hits": 0, "misses": 0, "writes": 0},
        },
        "outputs": output_files,
        "network_calls": 0,
    }
    output_path = output_directory / "run_manifest.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path

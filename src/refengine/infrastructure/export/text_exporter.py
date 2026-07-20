from __future__ import annotations

from pathlib import Path

from refengine.domain.models import ProcessedDocument


def export_references_text(
    documents: list[ProcessedDocument],
    output_path: Path,
    *,
    notice: str | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    references = [item.generated_reference for item in documents if item.generated_reference]
    sections: list[str] = []
    if notice:
        sections.append(notice.strip())
    sections.extend(reference for reference in references if reference)
    output_path.write_text(
        "\n\n".join(sections) + ("\n" if sections else ""),
        encoding="utf-8",
    )

from __future__ import annotations

from pathlib import Path

from refengine.domain.models import ProcessedDocument
from refengine.services.catalog_review import field_label, schema_for
from refengine.services.reference_quality import assess_reference, build_reference_quality_report


def export_reference_report(
    documents: list[ProcessedDocument],
    output_path: Path,
) -> None:
    """Write a compact local report focused on usable, reviewable, and blocked works."""
    summary = build_reference_quality_report(documents)
    lines = [
        "RefEngine — UFV reference report",
        "",
        f"Physical sources: {summary['physical_documents']}",
        f"Selected works: {summary['selected_works']}",
        f"Generated references: {summary['generated_references']}",
        f"Ready references: {summary['ready_references']}",
        f"Review required: {summary['review_required_references']}",
        f"Blocked references: {summary['blocked_references']}",
        "",
    ]

    for document in documents:
        if not document.include_in_output:
            continue
        quality = assess_reference(document)
        resolved = document.resolved_bibliography
        schema = schema_for(resolved.schema_id if resolved is not None else None)
        if quality.readiness.value == "ready":
            continue
        lines.append(f"[{quality.readiness.value.upper()}] {document.source_path.name}")
        if schema is not None:
            lines.append(
                f"  Schema: {schema.id} — {schema.label} ({schema.section}, p. {schema.printed_page})"
            )
        elif resolved is not None and resolved.schema_id:
            lines.append(f"  Schema: {resolved.schema_id}")
        else:
            lines.append("  Schema: not identified")
        if resolved is not None and resolved.missing_required_fields:
            missing = []
            for field_id in resolved.missing_required_fields:
                if field_id.startswith("any_of:"):
                    alternatives = field_id.removeprefix("any_of:").split("|")
                    missing.append(
                        "one of " + " / ".join(field_label(item) for item in alternatives)
                    )
                else:
                    missing.append(field_label(field_id))
            lines.append("  Missing: " + "; ".join(missing))
        if resolved is not None and resolved.conflicting_fields:
            lines.append(
                "  Conflicts: "
                + "; ".join(field_label(field_id) for field_id in resolved.conflicting_fields)
            )
        if quality.issues:
            lines.append("  Quality issues: " + ", ".join(issue.value for issue in quality.issues))
        lines.append(
            "  Review: use the local frontend/API to inspect evidence, edit fields, and approve."
        )
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

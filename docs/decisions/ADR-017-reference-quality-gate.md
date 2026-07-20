# ADR-017: Separate generated references from final-ready references

## Status

Accepted — 2026-07-13.

## Context

A formatter can produce syntactically valid ABNT text from metadata that still
requires verification. Labelling every formatted result as final creates a false
quality guarantee.

## Decision

RefEngine evaluates selected references with a deterministic quality gate. The
gate uses only observable runtime evidence: extraction status, document type,
field presence, confidence, extraction method, OCR provenance, and explicit
human approval. It does not consult benchmark answers or file hashes.

Final exports contain only `ready` references. Generated references that need
verification are exported separately and remain editable through the existing
review workbook.

## Consequences

- Automatic extraction remains useful without overstating certainty.
- Review work is focused on specific reason codes.
- Explicit approval can promote a correct reference without reprocessing PDFs.
- Some correct references may be conservatively held for review; this is an
  intentional precision-over-recall trade-off.

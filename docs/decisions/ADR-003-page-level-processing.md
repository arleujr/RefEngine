# ADR-003: Page-level document processing

## Status

Accepted.

## Decision

Detect native text and OCR requirements per page rather than per PDF.

## Rationale

A PDF may be hybrid: some pages contain searchable text while others are scanned images. File-level routing would either miss content or perform unnecessary OCR.

## Consequences

- processing records need page provenance;
- the pipeline becomes slightly more complex;
- OCR cost is reduced and extraction quality improves.

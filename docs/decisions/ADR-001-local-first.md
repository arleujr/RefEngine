# ADR-001: Local-first processing

## Status

Accepted.

## Decision

All document processing runs on the user's machine. The default product contains no remote OCR, metadata API, telemetry, or cloud model dependency.

## Rationale

Academic manuscripts may be unpublished or confidential. Local-first processing reduces disclosure risk and makes the privacy promise technically enforceable.

## Consequences

- installation is heavier;
- Tesseract must be available locally;
- metadata cannot rely on Crossref or publisher APIs;
- missing data must be reviewed by the user.

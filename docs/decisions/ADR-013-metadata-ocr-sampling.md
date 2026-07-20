# ADR-013: OCR only metadata-bearing pages by default

## Status

Accepted.

## Decision

For image-only PDFs OCR the first two pages at 180 DPI. Native text pages are still read normally. Remaining image pages are recorded as skipped.

## Rationale

Bibliographic fields normally appear in front matter. Testing the FIT 399 browser-print corpus showed that full-resolution OCR and final-page sampling increased processing time without improving reference metadata. Three front pages captured the title and author sections of the supplied SciELO print while keeping the local workflow responsive.

## Consequences

- the application is a reference extractor, not a full-document OCR archive;
- skipped pages remain visible in diagnostics;
- users can still inspect the complete PDF in the frontend;
- a future full-text feature must use a separate explicit job mode.

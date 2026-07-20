# ADR-008: Latest output and local run history

## Status

Accepted.

## Decision

The one-click workflow writes to `output/latest`. Before a new run, existing generated files are moved to a timestamped folder under `output/history`. A portable ZIP of the latest result is generated after processing.

## Rationale

Users need predictable locations without silently overwriting the previous review artifacts. Timestamped local history provides recovery without introducing a server or external storage.

## Consequences

- Repeated runs consume local disk space until the user removes old history folders.
- Scripts and documentation can rely on a stable latest-output path.
- Generated data remains outside version control.

# ADR-010: Processed-with-warnings status

## Status

Accepted.

## Decision

A document with valid required metadata but one or more non-blocking warnings receives `processed_with_warnings`, not `processed`.

## Rationale

A single success label hid meaningful conditions such as unavailable pages, inferred metadata, missing publication place, and explicit local API corrections.

## Consequences

- dashboards and reports distinguish clean and warning-bearing documents;
- warning-bearing references remain usable but visibly require attention;
- status and warning codes remain independently queryable.

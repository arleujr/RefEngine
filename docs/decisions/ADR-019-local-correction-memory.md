# ADR-019: Local correction memory

## Status

Accepted for v0.11.0.

## Context

Repeated OCR or source spelling issues can require the same human correction in different references. Applying those corrections silently would weaken provenance and could spread a wrong value across unrelated works.

## Decision

RefEngine stores reusable corrections only after two explicit actions: the user changes a field and then approves the reference. The memory is persisted locally in SQLite.

Suggestions require an exact normalized source match, the same bibliographic field, and the same document type. The interface displays the original value, proposed replacement, origin, and confirmation count. The user must press **Apply suggestion**.

Reusable fields are limited to textual bibliographic entities such as authors, titles, journals, institutions, departments, and publishers. Years, volumes, issues, pages, article numbers, total pages, DOI, and URL are excluded because their values are too generic or work-specific for safe reuse. Empty-value completions and case-only edits are also excluded.

Starting a new project removes project PDFs and reviews but preserves the correction memory. Users can inspect, delete, export, import, or clear the memory.

## Consequences

- Corrections remain auditable and reversible.
- The application becomes faster to review without introducing automatic hidden mutation.
- The mechanism is deterministic and offline.
- Some useful corrections will intentionally not be suggested when they do not meet the conservative reuse contract.

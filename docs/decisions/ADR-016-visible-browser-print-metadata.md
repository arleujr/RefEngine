# ADR-016: Visible-source-only browser-print metadata

- Status: Accepted
- Date: 2026-07-13

## Context

A browser-print PDF is not equivalent to the publisher PDF. It often contains
navigation labels, collapsed sections, metrics, icons, and line wrapping. OCR
can recover the visible text, but it cannot recover fields that were not
rendered on the page.

Earlier generic heuristics selected long abstract lines as titles and accepted
the local PDF creator as an author. That behavior made the output look more
complete than the evidence justified.

## Decision

RefEngine uses explicit source-template adapters for printed web pages. An
adapter may read only text visible in the PDF and may not consult:

- a file hash mapped to approved metadata;
- the benchmark oracle;
- a network service;
- metadata extracted from a different document.

The initial supported templates are:

- Springer Nature Link;
- ScienceDirect;
- LOCUS/DSpace item pages;
- SciELO article pages.

Each adapter extracts stable labels such as publication title, volume, issue,
page range, article number, author block, citation block, and URI. Extracted
fields retain `web_print_profile` provenance.

When a critical field is collapsed or absent, the adapter must leave it empty.
For example, a SciELO print with a collapsed `Autoria` or `Authorship` section
receives `AUTHORS_NOT_VISIBLE_IN_SOURCE`; it does not receive an author from the
PDF creator or a sibling original.

Visible spelling is also preserved. A source-specific correction may not be
hard-coded into an extractor. When a publisher PDF contains a misspelled name,
the automatic layer records the visible value and the reviewed value remains a
separate, explicitly attributed correction.

## Variant identity

Physical variants may be grouped when:

1. canonical keys or normalized DOIs match exactly; or
2. one side is a browser/scanned representation, the year and first-author
   family name match, and normalized title similarity is at least 0.96.

Fuzzy matching is not applied between two publisher originals. The selected
winner supplies the shared canonical identity, while all physical files remain
in the audit trail.

## Consequences

- Printed pages with visible bibliographic fields can generate references
  independently.
- Printed pages that hide a critical field remain review-required.
- Mixed original/print folders produce one final reference per resolved work.
- The system can state precisely whether a failure is OCR-related, layout-
  related, or caused by content that is not visible in the source.

# ADR-002: SQLite as the source of truth

## Status

Accepted.

## Decision

Use SQLite for the local catalog. JSON and Excel remain export and interchange formats.

## Rationale

SQLite provides transactions, indexing, deduplication, migrations, and relational queries without requiring a separate database server.

## Consequences

- schema migrations must be versioned;
- concurrent multi-user access is not a primary goal;
- the database file must be included in backup guidance.

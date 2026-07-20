# ADR-006: Conventional local workspace folders

## Status

Accepted.

## Decision

The repository includes `input`, `output`, `config`, and `data` workspace folders. The application reads supported sources from `input`, writes final artifacts to `output`, and stores run state and explicit review corrections locally.

## Rationale

Conventional folders keep the local workflow simple without introducing an upload endpoint. The official cross-platform entry point is the Python CLI: `refengine serve`.

## Consequences

- private source files must remain ignored by Git;
- generated output and local databases must remain ignored by Git;
- source paths are preserved relative to `input`;
- the CLI can fail early with a clear instruction when `input` is empty.

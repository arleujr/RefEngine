# Contributing

## Development setup

```bash
uv sync --frozen --extra dev
cd frontend
npm ci
cd ..
```

## Quality checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
cd frontend
npm test
npm run build
```

## Local application

```bash
uv run refengine serve --open-browser
```

Place public or synthetic test sources manually in `input/`. Do not commit private academic documents and do not add an upload endpoint.

## Engineering expectations

- Preserve the local-only and reference-generation-only scope.
- Keep UFV rules in the backend catalog and deterministic formatters.
- Do not duplicate normative rules in React.
- Reject fields that do not belong to the selected schema.
- Do not validate mandatory fields for excluded works.
- Keep source alternatives and provenance available.
- Do not introduce production conditions based on corpus titles, DOI values, hashes, or filenames.
- Add tests for every endpoint, bug fix, and normative rule.
- Use logging instead of debugging prints.

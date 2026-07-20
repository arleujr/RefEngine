#!/usr/bin/env bash
set -euo pipefail

uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest

(
  cd frontend
  npm test
  npm run build
)

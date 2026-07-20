# Data flow

1. The user manually places `.pdf`, `.bib`, and `.ris` files in `input/`.
2. `GET /api/v1/input` returns the local inventory.
3. `POST /api/v1/runs` creates a queued run and starts one local worker.
4. The worker extracts candidates, merges source variants, selects a UFV schema, resolves fields, and creates draft references.
5. The frontend polls `GET /api/v1/runs/{run_id}`.
6. The frontend reads works and evidence from the run endpoints.
7. `PATCH` stores explicit field/schema changes and recompiles the complete run.
8. `POST .../approve` confirms a review-required work after required-field validation.
9. `POST .../publish` rejects unresolved included works and writes final DOCX/TXT files.
10. Downloads are served from the run-specific local export folder.

No document bytes are transmitted over the API.

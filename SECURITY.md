# Security Policy

## Supported version

The latest released version is supported.

## Local privacy contract

RefEngine must not:

- upload PDFs, RIS, or BibTeX files;
- expose a file-upload endpoint;
- bind the official server to a public interface;
- call remote metadata APIs;
- send telemetry or OCR output;
- execute remote model inference.

The official CLI binds to `127.0.0.1`. CORS is limited to local React development origins. Source files are read from the project `input/` directory.

## Local file handling

- Source files are opened read-only.
- Each execution processes an immutable local snapshot.
- Draft data is stored under `data/runs/`.
- Final files are generated only after explicit publication.
- `output/latest` is replaced atomically and previous successful output is retained in history.
- File hashes support inventory, deduplication, cache, and audit records.

## Reporting a vulnerability

Use a private GitHub security advisory. Do not attach confidential academic documents to a public issue.

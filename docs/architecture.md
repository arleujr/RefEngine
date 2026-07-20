# Architecture

RefEngine 1.1 is a single-machine backend.

```text
React localhost client
        ↓ HTTP on 127.0.0.1
FastAPI transport
        ↓
run service + SQLite state
        ↓
PDF/OCR, BibTeX, RIS extraction
        ↓
UFV catalog resolver and formatter
        ↓
DOCX/TXT publication
```

## Boundaries

- The API has no upload endpoint.
- Source files are discovered only in the project `input/` directory.
- React contains no UFV formatting rule.
- SQLite stores run and review state.
- The existing extraction and normative core remains independent from FastAPI.
- Final files are generated only by the publish operation.

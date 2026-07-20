# Privacy threat model

## Protected data

Academic source PDFs, structured bibliographic files, extracted text, candidate metadata, corrections, and final references.

## Controls

- The official CLI binds Uvicorn to `127.0.0.1` only.
- No upload endpoint exists.
- The backend reads only the fixed local `input/` directory.
- CORS allows only React development origins on localhost port 5173.
- Processing performs no internet request.
- Interactive API documentation that depends on external assets is disabled; the OpenAPI JSON is local.
- Run databases, logs, drafts, and exports stay in project folders.

The backend is not designed for remote or multi-user deployment.

PLACE SOURCE FILES HERE MANUALLY

Accepted extensions:
- .pdf
- .bib
- .bibtex
- .ris

The React interface and API do not upload documents.
After placing the files here, build the frontend and run:

uv run refengine serve --open-browser

Each run processes an immutable snapshot. Later changes do not contaminate that run;
input-status remains available only as a technical diagnostic endpoint.

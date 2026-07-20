# Testing strategy

Automated tests cover:

- the 43 UFV schemas and deterministic formatting;
- PDF/OCR, BibTeX, and RIS extraction behavior;
- candidate selection, conflicts, and required fields;
- API input inventory with no upload path;
- asynchronous folder processing;
- draft detail and schema-aware editing;
- rejection of fields outside the selected schema;
- exclusion without mandatory-field validation;
- publish blocking and explicit approval;
- DOCX/TXT generation and download;
- SQLite recovery after interrupted runs;
- loopback-only server configuration;
- absence of corpus-specific production conditions.

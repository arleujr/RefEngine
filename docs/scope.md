# Frozen scope

RefEngine:

- reads PDF, BibTeX, and RIS files placed manually in `input/`;
- performs native extraction and local OCR;
- applies the UFV 2025 reference catalog;
- exposes drafts, evidence, conflicts, and missing fields through a local API;
- accepts local review corrections;
- generates alphabetically ordered DOCX and TXT reference lists.

Out of scope:

- file upload through frontend or API;
- reading or editing the TCC;
- citation detection or audit;
- internet lookup;
- cloud storage;
- AI or machine learning;
- multiple universities or citation styles;
- authentication for remote access;
- public network binding.

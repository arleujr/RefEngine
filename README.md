

<div align="center">
  <video src="https://github.com/user-attachments/assets/c51d9923-573c-4856-be14-110f19a515c5" controls="controls" width="100%" muted="muted">
    Seu navegador não suporta a tag de vídeo.
  </video>
</div>

# RefEngine

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

> **Documentação em português:** [README.pt-BR.md](README.pt-BR.md)

**RefEngine** is an independently developed local web application for extracting, reviewing, and generating academic references from PDF, BibTeX, and RIS files according to the Universidade Federal de Viçosa 2025 reference catalog.

While writing my Agronomy undergraduate thesis at the Universidade Federal de Viçosa, I identified that organizing references from different source formats required repetitive checking and manual data entry. I created RefEngine with two main goals:

* **Reduce manual work** during the initial identification, review, and organization of academic references.
* **Build practical software engineering experience** by applying Python, APIs, document processing, deterministic rules, local persistence, and a React frontend to a real academic problem.

Users place source files in the local `input` folder, review the extracted fields in the browser, and publish an alphabetically ordered `.docx` and `.txt` reference list.

> **Note:** RefEngine is an independent support tool and portfolio project. It does not replace human review, the institutional manual, or the author's responsibility for the references used in academic work.

---

## Technologies

* **Frontend:** React, TypeScript, and Vite
* **Backend:** Python, FastAPI, and Pydantic
* **Local persistence:** SQLite
* **PDF extraction:** PyMuPDF
* **Optional OCR:** Tesseract
* **Document generation:** python-docx
* **Testing:** pytest, Vitest, and React Testing Library
* **API contract:** OpenAPI

---

## Main Features

* Local processing of PDF, BibTeX (`.bib` and `.bibtex`), and RIS files.
* Native text extraction and local OCR for scanned PDFs.
* Consolidation of PDF, BibTeX, and RIS sources describing the same work.
* Document-type identification and UFV schema selection.
* Browser-based field review and correction.
* Field-specific missing-data and conflict messages.
* Exclusion without mandatory-field validation.
* Alphabetical ordering of final references.
* DOCX and TXT publication.
* No file upload, cloud storage, telemetry, or remote metadata lookup.

---

## Project Structure

```text
.
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── package-lock.json
├── src/refengine/
├── tests/
├── docs/
├── scripts/
├── openapi/
├── input/
├── output/
├── data/
├── pyproject.toml
├── uv.lock
├── requirements.lock
├── requirements-dev.lock
├── README.md
├── README.pt-BR.md
└── LICENSE
```

The versioned UFV catalog is located at:

```text
src/refengine/rules/data/ufv_2025_reference_catalog.yaml
```

The YAML catalog defines schemas, registered fields, requirements, conditions, labels, and field order. Deterministic and tested Python formatters implement punctuation and textual assembly. The React frontend does not duplicate normative rules.

---

## Local Setup

### Requirements

* Python 3.12 or newer
* [uv](https://docs.astral.sh/uv/)
* Node.js 20.19 or newer
* npm
* Git
* Tesseract only for OCR of scanned PDFs

Clone the repository:

```bash
git clone https://github.com/arleujr/RefEngine.git
cd RefEngine
```

Install the locked Python environment:

```bash
uv sync --frozen
```

Install and build the frontend:

```bash
cd frontend
npm ci
npm run build
cd ..
```

Place supported files in `input/`, then start the application:

```bash
uv run refengine serve --open-browser
```

The local interface is available at:

```text
http://127.0.0.1:8000
```

For frontend development, run the backend with `uv run refengine serve` and start Vite in another terminal with `cd frontend && npm run dev`.

---

## Processing Flow

```text
input files
    ↓
immutable run snapshot
    ↓
PDF, BibTeX, and RIS extraction
    ↓
source consolidation
    ↓
document-type identification
    ↓
UFV 2025 catalog rules
    ↓
human review
    ↓
DOCX and TXT publication
```

Matching PDF, BibTeX, and RIS sources become a single work instead of duplicate references. Provenance and source-backed alternatives remain available during review.

The form keeps edits locally and sends a `PATCH` only after **Save changes** is clicked. Excluded works do not require a schema or mandatory fields and do not block publication.

---

## DOI and URL Policy

* A DOI URL that duplicates the DOI is not printed twice.
* A work with a DOI and no distinct URL prints only the DOI.
* A work without a DOI uses `Available at` and an access date.
* A work with a DOI and a genuinely different repository URL may keep both.

Final references are published as one alphabetically ordered list.

---

## PDF Extraction

BibTeX and RIS usually provide structured metadata and tend to require less review.

PDF extraction combines embedded text, document metadata, regular expressions, structural signals, and optional local OCR. It is heuristic: scanned files, two-column layouts, unusual typography, and poorly structured documents may require manual correction.

Production code does not contain rules conditioned on a test document's filename, title, DOI, or hash.

---

## Tests

Install development dependencies:

```bash
uv sync --frozen --extra dev
```

Run backend quality checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

Run frontend tests and build:

```bash
cd frontend
npm ci
npm test
npm run build
```

GitHub Actions runs both backend and frontend checks.

---

## Privacy

RefEngine runs locally and binds only to `127.0.0.1`. It has no upload endpoint and performs no cloud storage, telemetry, remote bibliographic lookup, or AI inference. Input documents, run snapshots, databases, and generated outputs are ignored by Git.

---

## Limitations

* The current scope targets the UFV 2025 catalog.
* RefEngine does not read or edit the thesis manuscript.
* It does not audit in-text citations.
* PDF extraction may require manual review.
* OCR depends on a local Tesseract installation and source quality.
* The final file must be reviewed before academic use.

---

## Roadmap

* Expand generic extractors for books, chapters, conference papers, and academic works.
* Improve support for complex and multi-column PDF layouts.
* Add review filters for unidentified publication places such as `[S. l.]`.
* Increase test coverage with public documents from different publishers.
* Create a distributable Windows installer.
* Evolve integration with [tccBuilder](https://github.com/arleujr/tccBuilder).

---

## Author

Developed by **Arleu Júnior**

[![GitHub](https://img.shields.io/badge/GitHub-arleujr-181717?logo=github)](https://github.com/arleujr)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Arleu%20Júnior-0A66C2?logo=linkedin)](https://www.linkedin.com/in/arleujunior/)

---

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE) for details.

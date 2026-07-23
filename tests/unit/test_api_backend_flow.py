from __future__ import annotations

import time
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from refengine.api.app import create_app
from refengine.api.service import RefEngineApiService
from refengine.domain.bibliography import ResolutionAlternative, ResolutionStatus
from refengine.domain.models import CorrectionSuggestion

_COMPLETE_BIBTEX = """@article{demo,
  author = {Silva, Ana and Souza, Bruno},
  title = {Teste local de referências},
  journal = {Revista Exemplo},
  year = {2024},
  volume = {10},
  number = {2},
  pages = {1--10},
  doi = {10.1234/demo.2024},
  url = {https://doi.org/10.1234/demo.2024}
}
"""


def _client(tmp_path: Path) -> tuple[TestClient, RefEngineApiService]:
    (tmp_path / "input").mkdir(parents=True, exist_ok=True)
    service = RefEngineApiService(tmp_path)
    return TestClient(create_app(service=service)), service


def _wait_for_review(client: TestClient, run_id: str) -> dict[str, object]:
    for _ in range(200):
        response = client.get(f"/api/v1/runs/{run_id}")
        payload = response.json()
        if payload["status"] not in {"queued", "processing"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("The local run did not finish in time")


def test_api_reads_only_the_input_folder_and_exposes_no_upload_endpoint(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    (tmp_path / "input" / "source.bib").write_text(_COMPLETE_BIBTEX, encoding="utf-8")

    with client:
        health = client.get("/api/v1/health")
        inventory = client.get("/api/v1/input")
        openapi = client.get("/api/v1/openapi.json").json()

    assert health.status_code == 200
    assert health.json()["input_mode"] == "folder"
    assert inventory.json()["counts"] == {"pdf": 0, "bibtex": 1, "ris": 0}
    assert not any("upload" in path.casefold() for path in openapi["paths"])
    assert "multipart/form-data" not in str(openapi)


def test_api_processes_folder_edits_draft_and_publishes_final_files(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    (tmp_path / "input" / "source.bib").write_text(_COMPLETE_BIBTEX, encoding="utf-8")

    with client:
        created = client.post("/api/v1/runs", json={})
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        run = _wait_for_review(client, run_id)
        assert run["status"] == "review"
        assert run["selected_works"] == 1

        works = client.get(f"/api/v1/runs/{run_id}/works").json()
        assert len(works) == 1
        work_id = works[0]["work_id"]
        detail = client.get(f"/api/v1/runs/{run_id}/works/{work_id}")
        assert detail.status_code == 200
        assert detail.json()["schema"]["id"] == "ufv.22"

        edited = client.patch(
            f"/api/v1/runs/{run_id}/works/{work_id}",
            json={"fields": {"title": "Teste local de referências corrigido"}},
        )
        assert edited.status_code == 200
        assert "corrigido" in edited.json()["work"]["reference"]

        published = client.post(f"/api/v1/runs/{run_id}/publish")
        assert published.status_code == 200
        assert published.json()["references"] == 1
        text = client.get(f"/api/v1/runs/{run_id}/exports/txt")
        document = client.get(f"/api/v1/runs/{run_id}/exports/docx")

    assert text.status_code == 200
    assert "1-10" in text.text
    assert "1--10" not in text.text
    assert "corrigido" in text.text
    assert document.status_code == 200
    assert document.content.startswith(b"PK")
    assert (tmp_path / "output" / "latest" / "references_ufv.docx").is_file()
    assert not list(tmp_path.rglob("*.xlsx"))


def test_publish_is_blocked_until_a_review_required_work_is_approved(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    (tmp_path / "input" / "source.bib").write_text(_COMPLETE_BIBTEX, encoding="utf-8")

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        _wait_for_review(client, run_id)
        document = service.repository.load_documents(run_id)[0]
        document.correction_suggestions = [
            CorrectionSuggestion(
                field_name="title",
                field_label="Título",
                source_value="Teste local de referências",
                replacement_value="Teste local de referências",
            )
        ]
        service.repository.save_documents(run_id, [document], preserve_original=True)
        work_id = document.sha256

        blocked = client.post(f"/api/v1/runs/{run_id}/publish")
        assert blocked.status_code == 409
        assert blocked.json()["error"] == "publication_blocked"

        approved = client.post(f"/api/v1/runs/{run_id}/works/{work_id}/approve")
        assert approved.status_code == 200
        assert approved.json()["work"]["readiness"] == "ready"

        published = client.post(f"/api/v1/runs/{run_id}/publish")
        assert published.status_code == 200


def test_review_rejects_fields_that_do_not_belong_to_selected_schema(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    (tmp_path / "input" / "source.bib").write_text(_COMPLETE_BIBTEX, encoding="utf-8")

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        _wait_for_review(client, run_id)
        work_id = client.get(f"/api/v1/runs/{run_id}/works").json()[0]["work_id"]
        response = client.patch(
            f"/api/v1/runs/{run_id}/works/{work_id}",
            json={"fields": {"academic_place": "Viçosa, MG"}},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_review"


def test_catalog_fields_endpoint_exposes_frontend_metadata(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        response = client.get("/api/v1/catalog/fields")

    assert response.status_code == 200
    fields = response.json()
    assert len(fields) == 114
    title = next(item for item in fields if item["id"] == "title")
    assert title == {
        "id": "title",
        "label": "Título principal",
        "repeatable": False,
        "value_type": "text",
    }


def test_run_exposes_relative_paths_for_duplicate_filenames(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    first = tmp_path / "input" / "group-a"
    second = tmp_path / "input" / "group-b"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "source.bib").write_text(
        _COMPLETE_BIBTEX.replace("demo,", "first,").replace(
            "Teste local de referências", "Primeira referência"
        ),
        encoding="utf-8",
    )
    (second / "source.bib").write_text(
        _COMPLETE_BIBTEX.replace("demo,", "second,")
        .replace("Silva, Ana and Souza, Bruno", "Oliveira, Carla")
        .replace("Teste local de referências", "Segunda referência")
        .replace("Revista Exemplo", "Periódico Distinto")
        .replace("2024", "2023")
        .replace("10.1234/demo.2024", "10.9876/second.2023"),
        encoding="utf-8",
    )

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        _wait_for_review(client, run_id)
        works = client.get(f"/api/v1/runs/{run_id}/works").json()

    relative_paths = {item["source_relative_path"].split("#", 1)[0] for item in works}
    assert relative_paths == {"group-a/source.bib", "group-b/source.bib"}
    assert all(item["source_relative_paths"] for item in works)


def test_input_status_reports_changes_without_invalidating_processed_snapshot(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path)
    source = tmp_path / "input" / "source.bib"
    source.write_text(_COMPLETE_BIBTEX, encoding="utf-8")

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        completed = _wait_for_review(client, run_id)
        assert completed["status"] == "review"
        source.write_text(
            _COMPLETE_BIBTEX.replace("Teste local de referências", "Conteúdo posterior"),
            encoding="utf-8",
        )
        status = client.get(f"/api/v1/runs/{run_id}/input-status")
        works = client.get(f"/api/v1/runs/{run_id}/works").json()

    assert status.status_code == 200
    assert status.json()["changed"] is True
    assert status.json()["changes"] == [{"relative_path": "source.bib", "change": "modified"}]
    assert works[0]["title"] == "Teste local de referências"
    assert (tmp_path / "data" / "runs" / run_id / "input_snapshot" / "source.bib").is_file()


def test_static_frontend_build_is_served_by_fastapi(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<h1>RefEngine UI</h1>", encoding="utf-8")
    service = RefEngineApiService(tmp_path)

    with TestClient(create_app(service=service)) as client:
        root = client.get("/")
        health = client.get("/api/v1/health")

    assert root.status_code == 200
    assert "RefEngine UI" in root.text
    assert health.json()["frontend_available"] is True


def test_bibtex_extension_is_inventoried_and_exposed_as_a_used_source(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    (tmp_path / "input" / "source.BIBTEX").write_text(_COMPLETE_BIBTEX, encoding="utf-8")

    with client:
        inventory = client.get("/api/v1/input").json()
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        _wait_for_review(client, run_id)
        work = client.get(f"/api/v1/runs/{run_id}/works").json()[0]

    assert inventory["counts"]["bibtex"] == 1
    assert work["source_types"] == ["bibtex"]
    assert work["source_relative_path"].startswith("source.BIBTEX#")


def test_work_detail_exposes_field_specific_conflict_messages(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    (tmp_path / "input" / "source.bib").write_text(_COMPLETE_BIBTEX, encoding="utf-8")

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        _wait_for_review(client, run_id)
        document = service.repository.load_documents(run_id)[0]
        resolved = document.resolved_bibliography
        assert resolved is not None
        title = resolved.fields["title"]
        title.status = ResolutionStatus.CONFLICT
        title.alternatives = [
            ResolutionAlternative(
                values=["Teste local de referências"],
                normalized_values=["teste local de referencias"],
                score=0.98,
                sources=["source.bib"],
                methods=["bibtex_raw_field"],
            ),
            ResolutionAlternative(
                values=["Título divergente"],
                normalized_values=["titulo divergente"],
                score=0.95,
                sources=["source.ris"],
                methods=["ris_raw_field"],
            ),
        ]
        resolved.conflicting_fields = ["title"]
        service.repository.save_documents(run_id, [document], preserve_original=True)

        detail = client.get(f"/api/v1/runs/{run_id}/works/{document.sha256}").json()

    conflict = next(item for item in detail["attention_items"] if item["code"] == "FIELD_CONFLICT")
    assert conflict["field_id"] == "title"
    assert conflict["field_label"] == "Título principal"
    assert "source.bib" in conflict["message"]
    assert "source.ris" in conflict["message"]
    assert "REFERENCE_FIELD_CONFLICT" not in conflict["message"]


def test_malformed_ris_exposes_the_actual_read_error(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    (tmp_path / "input" / "broken.ris").write_text(
        "TY  - JOUR\nTI  - Registro sem terminador\n",
        encoding="utf-8",
    )

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        _wait_for_review(client, run_id)
        work = client.get(f"/api/v1/runs/{run_id}/works").json()[0]
        detail = client.get(f"/api/v1/runs/{run_id}/works/{work['work_id']}").json()

    assert detail["processing_error"]
    assert "terminating 'ER -'" in detail["processing_error"]
    assert any(item["code"] == "SOURCE_READ_FAILED" for item in detail["attention_items"])


def test_source_file_endpoint_opens_the_immutable_run_snapshot(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    source = tmp_path / "input" / "source.bib"
    source.write_text(_COMPLETE_BIBTEX, encoding="utf-8")

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        _wait_for_review(client, run_id)
        response = client.get(
            f"/api/v1/runs/{run_id}/source",
            params={"path": "source.bib"},
        )
        invalid = client.get(
            f"/api/v1/runs/{run_id}/source",
            params={"path": "../outside.txt"},
        )

    assert response.status_code == 200
    assert response.content == _COMPLETE_BIBTEX.encode("utf-8")
    assert response.headers["content-disposition"].startswith("inline")
    assert invalid.status_code == 404
    assert invalid.json()["error"] == "source_not_found"


def test_published_text_is_alphabetical_even_when_repository_loads_by_filename(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path)
    input_dir = tmp_path / "input"
    (input_dir / "01-zulu.bib").write_text(
        _COMPLETE_BIBTEX.replace("Silva, Ana and Souza, Bruno", "Zulu, Zoe")
        .replace("Teste local de referências", "Referência Z")
        .replace("10.1234/demo.2024", "10.1234/zulu.2024"),
        encoding="utf-8",
    )
    (input_dir / "99-avila.bib").write_text(
        _COMPLETE_BIBTEX.replace("Silva, Ana and Souza, Bruno", "Ávila, Ana")
        .replace("Teste local de referências", "Referência A")
        .replace("10.1234/demo.2024", "10.1234/avila.2024"),
        encoding="utf-8",
    )

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        _wait_for_review(client, run_id)
        works = client.get(f"/api/v1/runs/{run_id}/works").json()
        assert [item["title"] for item in works] == ["Referência A", "Referência Z"]
        published = client.post(f"/api/v1/runs/{run_id}/publish")
        assert published.status_code == 200
        text = client.get(f"/api/v1/runs/{run_id}/exports/txt").text

    assert text.index("ÁVILA") < text.index("ZULU")


def test_excluding_work_does_not_require_schema_or_mandatory_fields(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    (tmp_path / "input" / "source.bib").write_text(_COMPLETE_BIBTEX, encoding="utf-8")

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        _wait_for_review(client, run_id)
        document = service.repository.load_documents(run_id)[0]
        record = document.bibliographic_record
        assert record is not None
        record.schema_override = None
        record.document_type_candidates = []
        document.bibliographic_record = record
        document.resolved_bibliography = None
        document.generated_reference = None
        service.repository.save_documents(run_id, [document], preserve_original=True)

        response = client.patch(
            f"/api/v1/runs/{run_id}/works/{document.sha256}",
            json={"included": False, "fields": {"title": None}},
        )

    assert response.status_code == 200
    work = response.json()["work"]
    assert work["included"] is False
    assert work["attention_items"] == []
    assert work["missing_required_fields"] == []
    assert response.json()["run"]["excluded_works"] == 1


def test_generic_native_text_pdf_reaches_review_with_extracted_article_fields(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path)
    pdf_path = tmp_path / "input" / "generic-article.pdf"
    document = fitz.open()
    first_page = document.new_page()
    first_page.insert_text(
        (72, 72),
        "A generic article title\n"
        "Ana Silva; Bruno Souza\n"
        "Journal of Applied Examples 12 (2024) 101-112\n"
        "DOI: 10.1234/example.2024.15\n\n"
        "Abstract\n"
        "This study validates generic PDF metadata extraction.\n"
        "Keywords: metadata; extraction; references\n"
        "Received 2 January 2024; Accepted 10 March 2024",
        fontsize=10,
    )
    second_page = document.new_page()
    second_page.insert_text(
        (72, 72),
        "References\n"
        "SILVA, A. Previous work. Journal of Previous Examples, 2020. "
        "This additional text keeps the page in native-text mode during the test.",
        fontsize=10,
    )
    document.save(pdf_path)
    document.close()

    with client:
        run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
        run = _wait_for_review(client, run_id)
        works = client.get(f"/api/v1/runs/{run_id}/works").json()
        detail = client.get(f"/api/v1/runs/{run_id}/works/{works[0]['work_id']}").json()

    assert run["status"] == "review"
    assert len(works) == 1
    assert detail["schema"]["id"] == "ufv.22"
    fields = {field["field_id"]: field["selected_values"] for field in detail["fields"]}
    assert fields["title"] == ["A generic article title"]
    assert fields["authors"] == ["Ana Silva", "Bruno Souza"]
    assert fields["periodical_title"] == ["Journal of Applied Examples"]
    assert detail["readiness"] == "review_required"
    assert not any(item["code"] == "SCHEMA_NOT_IDENTIFIED" for item in detail["attention_items"])

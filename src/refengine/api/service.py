from __future__ import annotations

import hashlib
import json
import shutil
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from refengine import __version__
from refengine.api.review_service import ApiReviewError, ApiReviewService
from refengine.api.schemas import (
    AttentionItemResponse,
    CandidateResponse,
    CatalogFieldResponse,
    FieldDetailResponse,
    InputFileChangeResponse,
    InputFileResponse,
    InputInventoryResponse,
    PublishResponse,
    RunCreateRequest,
    RunInputStatusResponse,
    RunResponse,
    SchemaResponse,
    WorkActionResponse,
    WorkDetailResponse,
    WorkSummaryResponse,
)
from refengine.application.ingest_folder import IngestFolder
from refengine.domain.enums import ApiRunStatus, QualityIssueCode, ReferenceReadiness
from refengine.domain.models import ProcessedDocument
from refengine.infrastructure.export.bibliographic_candidates_exporter import (
    export_bibliographic_candidates,
)
from refengine.infrastructure.export.docx_exporter import export_references_docx
from refengine.infrastructure.export.failure_exporter import export_failures
from refengine.infrastructure.export.json_exporter import export_json
from refengine.infrastructure.export.reference_quality_exporter import export_reference_quality
from refengine.infrastructure.export.reference_report_exporter import export_reference_report
from refengine.infrastructure.export.resolved_bibliography_exporter import (
    export_resolved_bibliography,
)
from refengine.infrastructure.export.text_exporter import export_references_text
from refengine.infrastructure.pdf.document_processor import DocumentProcessor
from refengine.infrastructure.persistence.api_repository import ApiRepository, ApiRunRecord
from refengine.infrastructure.persistence.extraction_cache import ExtractionCache
from refengine.infrastructure.persistence.review_memory import ReviewMemoryStore
from refengine.infrastructure.persistence.sqlite_repository import SqliteDocumentRepository
from refengine.infrastructure.runtime.run_guard import OutputTransaction, RunLock, new_run_id
from refengine.logging_config import configure_logging, shutdown_logging
from refengine.rules.catalog import NormativeCatalog, ReferenceSchema, load_ufv_2025_catalog
from refengine.services.catalog_review import (
    field_label,
    requirement_for,
    rule_details,
    rule_summary,
)
from refengine.services.input_inventory import build_input_inventory
from refengine.services.metadata_extractor import MetadataExtractor
from refengine.services.reference_formatter import ReferenceFormatter
from refengine.services.reference_quality import assess_reference


class ApiServiceError(RuntimeError):
    def __init__(
        self, error: str, message: str, *, details: dict[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.details = details or {}


class RefEngineApiService:
    """Local application service used by the FastAPI transport layer."""

    def __init__(
        self,
        project_root: Path,
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.input_directory = self.project_root / "input"
        self.output_directory = self.project_root / "output" / "latest"
        self.frontend_directory = self.project_root / "frontend" / "dist"
        self.data_directory = self.project_root / "data"
        self.runs_directory = self.data_directory / "runs"
        self.config_directory = self.project_root / "config"
        self.api_database = self.data_directory / "refengine_api.sqlite3"
        self.repository = ApiRepository(self.api_database)
        self.catalog: NormativeCatalog = load_ufv_2025_catalog()
        self._schemas = {schema.id: schema for schema in self.catalog.schemas}
        self._fields = {field.id: field for field in self.catalog.fields}
        catalog_schema_ids = frozenset(self._schemas)
        formatter_schema_ids = ReferenceFormatter.supported_schema_ids()
        if formatter_schema_ids != catalog_schema_ids:
            missing = sorted(catalog_schema_ids - formatter_schema_ids)
            extra = sorted(formatter_schema_ids - catalog_schema_ids)
            raise RuntimeError(
                "UFV catalog and formatter contract diverged; "
                f"missing_formatters={missing}, unknown_formatters={extra}"
            )
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="refengine-run",
        )
        self._owns_executor = executor is None
        self._futures: dict[str, Future[None]] = {}
        self._lock = threading.RLock()

    def startup(self) -> None:
        self.input_directory.mkdir(parents=True, exist_ok=True)
        self.output_directory.parent.mkdir(parents=True, exist_ok=True)
        self.runs_directory.mkdir(parents=True, exist_ok=True)
        self.config_directory.mkdir(parents=True, exist_ok=True)
        self.repository.recover_interrupted_runs()

    def shutdown(self) -> None:
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=False)

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "version": __version__,
            "local_only": True,
            "input_mode": "folder",
            "input_directory": str(self.input_directory),
            "api_database": str(self.api_database),
            "frontend_available": (self.frontend_directory / "index.html").is_file(),
        }

    def inventory(self, *, recursive: bool = True) -> InputInventoryResponse:
        self.input_directory.mkdir(parents=True, exist_ok=True)
        inventory = build_input_inventory(self.input_directory, recursive=recursive)
        counts = {"pdf": 0, "bibtex": 0, "ris": 0}
        files: list[InputFileResponse] = []
        for item in inventory.files:
            counts[item.source_type] = counts.get(item.source_type, 0) + 1
            files.append(
                InputFileResponse(
                    relative_path=item.relative_path,
                    source_type=item.source_type,
                    size_bytes=item.size_bytes,
                    sha256=item.sha256,
                )
            )
        return InputInventoryResponse(
            input_directory=str(self.input_directory),
            files=files,
            fingerprint=inventory.fingerprint,
            total_bytes=inventory.total_bytes,
            counts=counts,
        )

    def create_run(self, request: RunCreateRequest) -> RunResponse:
        with self._lock:
            active = self.repository.active_run()
            if active is not None:
                raise ApiServiceError(
                    "run_already_active",
                    "Another local processing run is already queued or running.",
                    details={"run_id": active.run_id, "status": active.status.value},
                )
            inventory = self.inventory(recursive=request.recursive)
            if not inventory.files:
                raise ApiServiceError(
                    "input_empty",
                    "No PDF, BibTeX, or RIS files were found in the input folder.",
                    details={"input_directory": inventory.input_directory},
                )
            run_id = new_run_id()
            access_date = request.access_date or date.today()
            settings: dict[str, object] = {
                "recursive": request.recursive,
                "ocr_page_limit": request.ocr_page_limit,
                "first_author_et_al": request.first_author_et_al,
                "cache": request.cache,
            }
            record = self.repository.create_run(
                run_id=run_id,
                access_date=access_date.isoformat(),
                settings=settings,
                input_inventory=inventory.model_dump(
                    mode="json", exclude={"input_directory", "counts"}
                ),
            )
            self._futures[run_id] = self._executor.submit(self._process_run, run_id)
            return self._run_response(record)

    def list_runs(self, limit: int = 20) -> list[RunResponse]:
        return [self._run_response(item) for item in self.repository.list_runs(limit)]

    def get_run(self, run_id: str) -> RunResponse:
        return self._run_response(self._require_run(run_id))

    def input_status(self, run_id: str) -> RunInputStatusResponse:
        run = self._require_run(run_id)
        recursive = bool(run.settings.get("recursive", True))
        current = build_input_inventory(self.input_directory, recursive=recursive)
        expected_fingerprint = str(run.input_inventory.get("fingerprint", ""))
        current_files = {item.relative_path: item for item in current.files}
        expected_files = {
            str(item.get("relative_path", "")): item
            for item in _inventory_file_records(run.input_inventory)
            if item.get("relative_path")
        }
        changes: list[InputFileChangeResponse] = []
        for path in sorted(current_files.keys() - expected_files.keys(), key=str.casefold):
            changes.append(InputFileChangeResponse(relative_path=path, change="added"))
        for path in sorted(expected_files.keys() - current_files.keys(), key=str.casefold):
            changes.append(InputFileChangeResponse(relative_path=path, change="removed"))
        for path in sorted(current_files.keys() & expected_files.keys(), key=str.casefold):
            expected = expected_files[path]
            current_item = current_files[path]
            if (
                str(expected.get("sha256", "")) != current_item.sha256
                or expected.get("size_bytes") != current_item.size_bytes
                or str(expected.get("source_type", "")) != current_item.source_type
            ):
                changes.append(InputFileChangeResponse(relative_path=path, change="modified"))
        return RunInputStatusResponse(
            run_id=run_id,
            changed=current.fingerprint != expected_fingerprint,
            expected_fingerprint=expected_fingerprint,
            current_fingerprint=current.fingerprint,
            checked_at=datetime.now(UTC).isoformat(),
            changes=changes,
        )

    def list_works(
        self,
        run_id: str,
        *,
        status: str | None = None,
    ) -> list[WorkSummaryResponse]:
        self._require_reviewable_run(run_id)
        documents = self._ordered_documents(run_id, self.repository.load_documents(run_id))
        summaries = [self._work_summary(item) for item in documents]
        if status is None:
            return summaries
        token = status.casefold()
        valid = {"ready", "review_required", "blocked", "excluded"}
        if token not in valid:
            raise ApiServiceError(
                "invalid_status_filter",
                f"Status must be one of: {', '.join(sorted(valid))}.",
            )
        return [
            item
            for item in summaries
            if ("excluded" if not item.included else item.readiness.value) == token
        ]

    def get_work(self, run_id: str, work_id: str) -> WorkDetailResponse:
        self._require_reviewable_run(run_id)
        document = self.repository.load_document(run_id, work_id)
        if document is None:
            raise ApiServiceError("work_not_found", "The requested work does not exist.")
        return self._work_detail(document)

    def patch_work(
        self,
        run_id: str,
        work_id: str,
        *,
        request: Any,
    ) -> WorkActionResponse:
        with self._lock:
            run = self._require_editable_run(run_id)
            documents = self.repository.load_documents(run_id)
            review = ApiReviewService(
                include_all_authors=not bool(run.settings.get("first_author_et_al", False)),
                catalog=self.catalog,
            )
            try:
                updated, changes = review.patch(
                    documents,
                    work_id=work_id,
                    access_date=date.fromisoformat(run.access_date),
                    schema_id_provided="schema_id" in request.model_fields_set,
                    schema_id=request.schema_id,
                    field_changes=request.fields,
                    included=request.included,
                )
            except KeyError as exc:
                raise ApiServiceError(
                    "work_not_found", "The requested work does not exist."
                ) from exc
            except ApiReviewError as exc:
                raise ApiServiceError("invalid_review", str(exc)) from exc
            self.repository.save_documents(run_id, updated, preserve_original=True)
            self.repository.append_review_event(
                run_id=run_id,
                work_id=work_id,
                action="patch",
                payload={"changes": changes},
            )
            self.repository.set_status(run_id, ApiRunStatus.REVIEW)
            document = self.repository.load_document(run_id, work_id)
            if document is None:
                raise ApiServiceError("work_not_found", "The requested work does not exist.")
            return WorkActionResponse(
                run=self.get_run(run_id),
                work=self._work_detail(document),
            )

    def approve_work(self, run_id: str, work_id: str) -> WorkActionResponse:
        with self._lock:
            run = self._require_editable_run(run_id)
            documents = self.repository.load_documents(run_id)
            review = ApiReviewService(
                include_all_authors=not bool(run.settings.get("first_author_et_al", False)),
                catalog=self.catalog,
            )
            try:
                updated = review.approve(
                    documents,
                    work_id=work_id,
                    access_date=date.fromisoformat(run.access_date),
                )
            except KeyError as exc:
                raise ApiServiceError(
                    "work_not_found", "The requested work does not exist."
                ) from exc
            except ApiReviewError as exc:
                current = self.repository.load_document(run_id, work_id)
                missing = (
                    current.resolved_bibliography.missing_required_fields
                    if current and current.resolved_bibliography
                    else []
                )
                raise ApiServiceError(
                    "reference_not_approvable",
                    str(exc),
                    details={"missing_fields": missing},
                ) from exc
            self.repository.save_documents(run_id, updated, preserve_original=True)
            approved = self.repository.load_document(run_id, work_id)
            original = self.repository.load_original_document(run_id, work_id)
            if approved is None or original is None:
                raise ApiServiceError("work_not_found", "The requested work does not exist.")
            remembered = ReviewMemoryStore(
                self.config_directory / "review_memory.sqlite3"
            ).remember_review(
                original,
                approved,
                ApiReviewService.reviewed_changes(approved),
            )
            self.repository.append_review_event(
                run_id=run_id,
                work_id=work_id,
                action="approve",
                payload={"corrections_remembered": remembered},
            )
            self.repository.set_status(run_id, ApiRunStatus.REVIEW)
            return WorkActionResponse(
                run=self.get_run(run_id),
                work=self._work_detail(approved),
            )

    def publish(self, run_id: str) -> PublishResponse:
        with self._lock:
            run = self._require_editable_run(run_id)
            documents = self._ordered_documents(run_id, self.repository.load_documents(run_id))
            included = [item for item in documents if item.include_in_output]
            not_ready = [
                item
                for item in included
                if assess_reference(item).readiness is not ReferenceReadiness.READY
            ]
            if not_ready:
                raise ApiServiceError(
                    "publication_blocked",
                    "Every included work must be ready or explicitly approved before publication.",
                    details={
                        "works": [
                            {
                                "work_id": item.sha256,
                                "source_file": item.source_path.name,
                                "readiness": assess_reference(item).readiness.value,
                                "issues": [issue.value for issue in assess_reference(item).issues],
                            }
                            for item in not_ready
                        ]
                    },
                )
            run_exports = self.runs_directory / run_id / "exports"
            try:
                transaction = OutputTransaction(run_exports, run_id=f"publish-{new_run_id()}")
                with (
                    RunLock(self.config_directory / "refengine.lock", operation="api-publish"),
                    transaction,
                ):
                    staging = transaction.staging
                    export_references_text(included, staging / "references_ufv.txt")
                    export_references_docx(included, staging / "references_ufv.docx")
                    (staging / "publication.json").write_text(
                        json.dumps(
                            {
                                "run_id": run_id,
                                "refengine_version": __version__,
                                "references": len(included),
                                "access_date": run.access_date,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    transaction.publish()

                mirror = OutputTransaction(self.output_directory, run_id=f"api-{run_id}")
                with mirror:
                    for source in run_exports.iterdir():
                        if source.is_file():
                            shutil.copy2(source, mirror.staging / source.name)
                    mirror.publish()
            except OSError as exc:
                raise ApiServiceError(
                    "publication_failed",
                    "The final DOCX/TXT files could not be written locally.",
                    details={"exception": type(exc).__name__},
                ) from exc

            export_urls: dict[str, str] = {}
            for extension in ("docx", "txt"):
                path = run_exports / f"references_ufv.{extension}"
                self.repository.save_export(
                    run_id=run_id,
                    format=extension,
                    path=path,
                    sha256=_sha256(path),
                    size_bytes=path.stat().st_size,
                )
                export_urls[extension] = f"/api/v1/runs/{run_id}/exports/{extension}"
            self.repository.set_status(run_id, ApiRunStatus.PUBLISHED)
            return PublishResponse(
                run=self.get_run(run_id),
                references=len(included),
                exports=export_urls,
            )

    def export_path(self, run_id: str, format: str) -> Path:
        if format not in {"docx", "txt"}:
            raise ApiServiceError("export_not_found", "Only DOCX and TXT exports are available.")
        run = self._require_run(run_id)
        if run.status is not ApiRunStatus.PUBLISHED:
            raise ApiServiceError(
                "run_not_published", "Publish the run before downloading final files."
            )
        record = self.repository.get_export(run_id, format)
        if record is None:
            raise ApiServiceError("export_not_found", "The requested export does not exist.")
        path = Path(record.path)
        if not path.is_file():
            raise ApiServiceError("export_not_found", "The export file is no longer available.")
        return path

    def list_catalog_fields(self) -> list[CatalogFieldResponse]:
        return [
            CatalogFieldResponse(
                id=field.id,
                label=field.label,
                repeatable=field.repeatable,
                value_type=field.value_type,
            )
            for field in self.catalog.fields
        ]

    def list_schemas(self) -> list[SchemaResponse]:
        return [self._schema_response(schema) for schema in self.catalog.schemas]

    def get_schema(self, schema_id: str) -> SchemaResponse:
        schema = self._schemas.get(schema_id)
        if schema is None:
            raise ApiServiceError("schema_not_found", "The requested UFV schema does not exist.")
        return self._schema_response(schema)

    def _process_run(self, run_id: str) -> None:
        run = self.repository.get_run(run_id)
        if run is None:
            return
        run_directory = self.runs_directory / run_id
        draft_directory = run_directory / "draft"
        try:
            self.repository.set_status(run_id, ApiRunStatus.PROCESSING)
            run_directory.mkdir(parents=True, exist_ok=True)
            configure_logging(run_directory / "refengine.log")
            with RunLock(self.config_directory / "refengine.lock", operation="api-ingest"):
                snapshot_directory = self._prepare_input_snapshot(run, run_directory)
                processor = DocumentProcessor(
                    metadata_ocr_page_limit=_int_setting(run.settings, "ocr_page_limit", 2)
                )
                use_case = IngestFolder(
                    processor=processor,
                    extractor=MetadataExtractor(),
                    formatter=ReferenceFormatter(
                        include_all_authors=not bool(run.settings.get("first_author_et_al", False)),
                        output_policy=self.catalog.output_policy,
                    ),
                    repository=SqliteDocumentRepository(run_directory / "catalog.sqlite3"),
                    review_memory=ReviewMemoryStore(
                        self.config_directory / "review_memory.sqlite3"
                    ),
                    extraction_cache=(
                        ExtractionCache(self.config_directory / "extraction_cache.sqlite3")
                        if bool(run.settings.get("cache", True))
                        else None
                    ),
                )
                documents = use_case.execute(
                    snapshot_directory,
                    access_date=date.fromisoformat(run.access_date),
                    recursive=bool(run.settings.get("recursive", True)),
                )
                self._restore_input_paths(documents, run, snapshot_directory)
                selected = [
                    item
                    for item in documents
                    if QualityIssueCode.SECONDARY_VARIANT not in assess_reference(item).issues
                ]
                self.repository.save_documents(run_id, selected, preserve_original=False)
                draft_directory.mkdir(parents=True, exist_ok=True)
                export_json(selected, draft_directory / "metadata.json")
                export_bibliographic_candidates(
                    selected,
                    draft_directory / "bibliographic_candidates.json",
                )
                export_resolved_bibliography(
                    selected,
                    draft_directory / "resolved_bibliography.json",
                )
                export_reference_quality(selected, draft_directory / "reference_quality.json")
                export_reference_report(selected, draft_directory / "reference_report.txt")
                export_failures(documents, draft_directory / "failures.json")
            self.repository.set_status(run_id, ApiRunStatus.REVIEW)
        except Exception as exc:
            self.repository.set_status(
                run_id,
                ApiRunStatus.FAILED,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        finally:
            shutdown_logging()

    def _prepare_input_snapshot(self, run: ApiRunRecord, run_directory: Path) -> Path:
        recursive = bool(run.settings.get("recursive", True))
        expected_fingerprint = str(run.input_inventory.get("fingerprint", ""))
        current = build_input_inventory(self.input_directory, recursive=recursive)
        if current.fingerprint != expected_fingerprint:
            raise RuntimeError(
                "The input folder changed after the run was created. "
                "Review the files and start a new run."
            )

        snapshot_directory = run_directory / "input_snapshot"
        staging = run_directory / ".input_snapshot.tmp"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            for item in current.files:
                source = self.input_directory / item.relative_path
                destination = staging / item.relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            copied = build_input_inventory(staging, recursive=recursive)
            if copied.fingerprint != expected_fingerprint:
                raise RuntimeError(
                    "The input folder changed while RefEngine was creating the run snapshot. "
                    "Start a new run after the folder is stable."
                )
            shutil.rmtree(snapshot_directory, ignore_errors=True)
            staging.replace(snapshot_directory)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return snapshot_directory

    def _restore_input_paths(
        self,
        documents: list[ProcessedDocument],
        run: ApiRunRecord,
        snapshot_directory: Path,
    ) -> None:
        inventory_paths = [
            str(item.get("relative_path", ""))
            for item in _inventory_file_records(run.input_inventory)
            if item.get("relative_path")
        ]
        by_name: dict[str, list[str]] = {}
        for relative_path in inventory_paths:
            by_name.setdefault(Path(relative_path).name.casefold(), []).append(relative_path)

        for document in documents:
            source_text = str(document.source_path)
            base_text, separator, fragment = source_text.partition("#")
            base_path = Path(base_text)
            try:
                primary = base_path.relative_to(snapshot_directory).as_posix()
            except ValueError:
                primary = base_path.name
            display_primary = f"{primary}#{fragment}" if separator else primary
            relative_paths = [display_primary]
            if document.bibliographic_record is not None:
                for source_file in document.bibliographic_record.source_files:
                    source_name = Path(source_file.partition("#")[0]).name.casefold()
                    for candidate in by_name.get(source_name, []):
                        if candidate not in relative_paths:
                            relative_paths.append(candidate)
            document.source_path = Path(display_primary)
            document.source_relative_paths = relative_paths

    def source_file_path(self, run_id: str, relative_path: str) -> Path:
        """Return a validated source file from the immutable run snapshot."""
        self._require_reviewable_run(run_id)
        normalized = relative_path.partition("#")[0].replace("\\", "/").strip("/")
        documents = self.repository.load_documents(run_id)
        allowed = {
            source.partition("#")[0].replace("\\", "/").strip("/")
            for document in documents
            for source in (document.source_relative_paths or [document.source_path.as_posix()])
        }
        if not normalized or normalized not in allowed:
            raise ApiServiceError(
                "source_not_found",
                "The requested source file is not part of this run.",
            )

        snapshot_root = (self.runs_directory / run_id / "input_snapshot").resolve()
        candidate = (snapshot_root / Path(normalized)).resolve()
        try:
            candidate.relative_to(snapshot_root)
        except ValueError as exc:
            raise ApiServiceError(
                "source_not_found",
                "The requested source path is invalid.",
            ) from exc
        if not candidate.is_file():
            raise ApiServiceError("source_not_found", "The requested source file no longer exists.")
        return candidate

    def _ordered_documents(
        self,
        run_id: str,
        documents: list[ProcessedDocument],
    ) -> list[ProcessedDocument]:
        """Order works alphabetically using the same formatter profile as the run."""
        run = self.repository.get_run(run_id)
        if run is None:
            raise ApiServiceError("run_not_found", "The requested run does not exist.")
        formatter = ReferenceFormatter(
            include_all_authors=not bool(run.settings.get("first_author_et_al", False)),
            output_policy=self.catalog.output_policy,
        )

        def key(document: ProcessedDocument) -> tuple[str, str, str]:
            resolved = document.resolved_bibliography
            if resolved is not None:
                return formatter.resolved_sort_key(resolved)
            return (document.source_path.name.casefold(), "", "")

        return sorted(documents, key=key)

    def _work_summary(self, document: ProcessedDocument) -> WorkSummaryResponse:
        assessment = assess_reference(document)
        resolved = document.resolved_bibliography
        schema = self._schemas.get((resolved.schema_id or "") if resolved else "")
        return WorkSummaryResponse(
            work_id=document.sha256,
            source_file=document.source_path.name,
            source_files=(
                list(document.bibliographic_record.source_files)
                if document.bibliographic_record is not None
                else [document.source_path.name]
            ),
            source_relative_path=(
                document.source_relative_paths[0]
                if document.source_relative_paths
                else document.source_path.as_posix()
            ),
            source_relative_paths=(
                list(document.source_relative_paths)
                if document.source_relative_paths
                else [document.source_path.as_posix()]
            ),
            schema_id=resolved.schema_id if resolved else None,
            schema_label=schema.label if schema else None,
            schema_family=schema.family if schema else None,
            manual_section=schema.section if schema else None,
            title=resolved.value_for("title") if resolved else document.metadata.title.value,
            readiness=assessment.readiness,
            review_state=document.review_state,
            included=document.include_in_output,
            reference=document.generated_reference,
            issues=[issue.value for issue in assessment.issues],
            source_types=self._source_types(document),
        )

    def _work_detail(self, document: ProcessedDocument) -> WorkDetailResponse:
        summary = self._work_summary(document)
        resolved = document.resolved_bibliography
        schema = self._schemas.get((resolved.schema_id or "") if resolved else "")
        fields: list[FieldDetailResponse] = []
        if schema is not None and resolved is not None:
            for field_id in schema.ordered_fields:
                current = resolved.fields.get(field_id)
                fields.append(
                    FieldDetailResponse(
                        field_id=field_id,
                        label=field_label(field_id),
                        repeatable=self._fields[field_id].repeatable,
                        value_type=self._fields[field_id].value_type,
                        requirement=requirement_for(schema, field_id),
                        selected_values=list(current.values) if current else [],
                        resolution_status=current.status.value if current else "missing",
                        confidence=current.confidence if current else 0.0,
                        reason=current.reason if current else "No candidate value was found.",
                        selected_sources=list(current.selected_sources) if current else [],
                        alternatives=[
                            CandidateResponse(
                                values=list(item.values),
                                score=item.score,
                                sources=list(item.sources),
                                methods=list(item.methods),
                            )
                            for item in (current.alternatives if current else [])
                        ],
                        rule_summary=rule_summary(schema, field_id),
                        rule_details=rule_details(field_id),
                    )
                )
        can_approve = bool(
            document.include_in_output
            and resolved is not None
            and resolved.schema_id is not None
            and not resolved.missing_required_fields
            and document.generated_reference
        )
        included = document.include_in_output
        return WorkDetailResponse(
            **summary.model_dump(),
            schema=self._schema_response(schema) if schema else None,
            fields=fields,
            missing_required_fields=(
                list(resolved.missing_required_fields) if included and resolved else []
            ),
            conflicting_fields=(
                list(resolved.conflicting_fields) if included and resolved else []
            ),
            can_approve=can_approve,
            correction_suggestions=(
                [item.model_dump(mode="json") for item in document.correction_suggestions]
                if included
                else []
            ),
            attention_items=self._attention_items(document),
            processing_error=(document.incident.message if document.incident else None),
        )

    def _source_types(self, document: ProcessedDocument) -> list[str]:
        record = document.bibliographic_record
        values: set[str] = set()
        if record is not None:
            values.update(candidate.source_format.value for candidate in record.field_candidates)
            values.update(
                candidate.source_format.value for candidate in record.document_type_candidates
            )
        for source_path in document.source_relative_paths or [document.source_path.as_posix()]:
            suffix = Path(source_path.partition("#")[0]).suffix.casefold()
            if suffix == ".pdf":
                values.add("pdf")
            elif suffix in {".bib", ".bibtex"}:
                values.add("bibtex")
            elif suffix == ".ris":
                values.add("ris")
        order = {"pdf": 0, "bibtex": 1, "ris": 2}
        return sorted((item for item in values if item in order), key=order.__getitem__)

    def _attention_items(self, document: ProcessedDocument) -> list[AttentionItemResponse]:
        if not document.include_in_output:
            return []
        assessment = assess_reference(document)
        resolved = document.resolved_bibliography
        items: list[AttentionItemResponse] = []

        if document.incident is not None:
            items.append(
                AttentionItemResponse(
                    code="SOURCE_READ_FAILED",
                    severity="error",
                    message=(
                        f'Não foi possível ler "{document.source_path.name}": '
                        f"{document.incident.message}"
                    ),
                )
            )

        if resolved is not None:
            for field_id in resolved.missing_required_fields:
                label = field_label(field_id)
                items.append(
                    AttentionItemResponse(
                        code="REQUIRED_FIELD_MISSING",
                        severity="error",
                        field_id=field_id,
                        field_label=label,
                        message=f'Preencha o campo obrigatório "{label}".',
                    )
                )
            for field_id in resolved.conflicting_fields:
                label = field_label(field_id)
                field = resolved.fields.get(field_id)
                source_names: list[str] = []
                if field is not None:
                    source_names = list(
                        dict.fromkeys(
                            Path(source.partition("#")[0]).name
                            for alternative in field.alternatives
                            for source in alternative.sources
                        )
                    )
                origin = f" em {', '.join(source_names)}" if source_names else " entre as fontes"
                items.append(
                    AttentionItemResponse(
                        code="FIELD_CONFLICT",
                        severity="warning",
                        field_id=field_id,
                        field_label=label,
                        message=(
                            f'Confira o campo "{label}": foram encontrados valores diferentes'
                            f"{origin}. Escolha ou digite o valor correto."
                        ),
                    )
                )

        represented = {item.code for item in items}
        issue_messages: dict[QualityIssueCode, tuple[str, str | None]] = {
            QualityIssueCode.REFERENCE_SCHEMA_NOT_IDENTIFIED: (
                "O arquivo foi lido, mas não houve sinais suficientes para identificar automaticamente se é artigo, livro, trabalho acadêmico ou outro tipo. Selecione o modelo UFV correto.",
                None,
            ),
            QualityIssueCode.REFERENCE_SCHEMA_NOT_IMPLEMENTED: (
                "O modelo UFV selecionado ainda não possui formatador disponível.",
                None,
            ),
            QualityIssueCode.REFERENCE_NOT_GENERATED: (
                "A referência ainda não pôde ser gerada. Corrija os campos obrigatórios indicados.",
                None,
            ),
            QualityIssueCode.EXTRACTION_BLOCKED: (
                "A fonte não pôde ser processada. Confira o erro de leitura exibido acima.",
                None,
            ),
            QualityIssueCode.OCR_ONLY_SOURCE: (
                "O documento foi lido somente por OCR. Confira principalmente título, autores e ano.",
                None,
            ),
            QualityIssueCode.HEURISTIC_AUTHOR_EXTRACTION: (
                "Confira os autores: os nomes foram inferidos a partir do texto do documento.",
                "authors",
            ),
            QualityIssueCode.LOW_TITLE_CONFIDENCE: (
                "Confira o título: a extração automática não foi suficientemente segura.",
                "title",
            ),
            QualityIssueCode.LOW_AUTHOR_CONFIDENCE: (
                "Confira os autores: a extração automática não foi suficientemente segura.",
                "authors",
            ),
            QualityIssueCode.LOW_CONFIDENCE_OCR_EVIDENCE: (
                "Há campos essenciais obtidos de OCR com baixa legibilidade. Confira os dados destacados.",
                None,
            ),
            QualityIssueCode.STRUCTURED_METADATA_CONFLICT: (
                "Os dados do PDF e dos arquivos BibTeX/RIS não coincidem. Confira os campos destacados.",
                None,
            ),
            QualityIssueCode.CORRECTION_SUGGESTION_AVAILABLE: (
                "Há uma correção previamente confirmada disponível para esta referência.",
                None,
            ),
            QualityIssueCode.UNSUPPORTED_DOCUMENT_TYPE: (
                "O tipo do documento não foi reconhecido. Selecione manualmente o modelo UFV.",
                None,
            ),
        }
        skipped = {
            QualityIssueCode.REFERENCE_FIELD_CONFLICT,
            QualityIssueCode.REQUIRED_REFERENCE_FIELD_MISSING,
            QualityIssueCode.SECONDARY_VARIANT,
        }
        for issue in assessment.issues:
            if issue in skipped:
                continue
            if issue is QualityIssueCode.EXTRACTION_BLOCKED and "SOURCE_READ_FAILED" in represented:
                continue
            if (
                issue is QualityIssueCode.STRUCTURED_METADATA_CONFLICT
                and "FIELD_CONFLICT" in represented
            ):
                continue
            message_and_field = issue_messages.get(issue)
            if message_and_field is None:
                continue
            issue_message, issue_field_id = message_and_field
            issue_label = field_label(issue_field_id) if issue_field_id else None
            items.append(
                AttentionItemResponse(
                    code=issue.value,
                    severity=(
                        "error" if assessment.readiness is ReferenceReadiness.BLOCKED else "warning"
                    ),
                    message=issue_message,
                    field_id=issue_field_id,
                    field_label=issue_label,
                )
            )
        return items

    @staticmethod
    def _schema_response(schema: ReferenceSchema) -> SchemaResponse:
        return SchemaResponse(
            id=schema.id,
            section=schema.section,
            printed_page=schema.printed_page,
            label=schema.label,
            family=schema.family,
            medium=schema.medium,
            required_fields=list(schema.required_fields),
            conditional_fields=list(schema.conditional_fields),
            ordered_fields=list(schema.ordered_fields),
            pattern=schema.pattern,
            notes=list(schema.notes),
        )

    @staticmethod
    def _run_response(record: ApiRunRecord) -> RunResponse:
        return RunResponse(
            run_id=record.run_id,
            status=record.status,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            published_at=record.published_at,
            access_date=record.access_date,
            physical_sources=record.physical_sources,
            selected_works=record.selected_works,
            ready_references=record.ready_references,
            review_required_references=record.review_required_references,
            blocked_references=record.blocked_references,
            excluded_works=record.excluded_works,
            revision=record.revision,
            error_message=record.error_message,
        )

    def _require_run(self, run_id: str) -> ApiRunRecord:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ApiServiceError("run_not_found", "The requested run does not exist.")
        return run

    def _require_reviewable_run(self, run_id: str) -> ApiRunRecord:
        run = self._require_run(run_id)
        if run.status in {ApiRunStatus.QUEUED, ApiRunStatus.PROCESSING}:
            raise ApiServiceError("run_not_ready", "The input folder is still being processed.")
        if run.status is ApiRunStatus.FAILED:
            raise ApiServiceError(
                "run_failed",
                run.error_message or "The processing run failed.",
            )
        return run

    def _require_editable_run(self, run_id: str) -> ApiRunRecord:
        return self._require_reviewable_run(run_id)


def _inventory_file_records(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        return []
    return [cast(dict[str, object], item) for item in raw_files if isinstance(item, dict)]


def _int_setting(settings: dict[str, object], key: str, default: int) -> int:
    value = settings.get(key, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from refengine.api.schemas import (
    CatalogFieldResponse,
    ErrorResponse,
    HealthResponse,
    InputInventoryResponse,
    PublishResponse,
    RunCreateRequest,
    RunInputStatusResponse,
    RunResponse,
    SchemaResponse,
    WorkActionResponse,
    WorkDetailResponse,
    WorkPatchRequest,
    WorkSummaryResponse,
)
from refengine.api.service import ApiServiceError, RefEngineApiService


def create_app(
    *,
    project_root: Path | None = None,
    service: RefEngineApiService | None = None,
) -> FastAPI:
    root = (project_root or (service.project_root if service else Path.cwd())).resolve()
    api_service = service or RefEngineApiService(root)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        api_service.startup()
        try:
            yield
        finally:
            api_service.shutdown()

    app = FastAPI(
        title="RefEngine API",
        version="1.0.0",
        description=(
            "Local-only reference engine. Source files are read exclusively from the input "
            "folder; the API intentionally has no upload endpoint."
        ),
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.refengine_service = api_service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(ApiServiceError)
    async def api_error_handler(_: Request, exc: ApiServiceError) -> JSONResponse:
        status = _status_for(exc.error)
        return JSONResponse(
            status_code=status,
            content=ErrorResponse(
                error=exc.error,
                message=exc.message,
                details=exc.details,
            ).model_dump(mode="json"),
        )

    router = APIRouter(prefix="/api/v1")

    @router.get("", response_model=HealthResponse)
    @router.get("/health", response_model=HealthResponse)
    def health() -> dict[str, object]:
        return api_service.health()

    @router.get("/input", response_model=InputInventoryResponse)
    def input_inventory(
        recursive: Annotated[bool, Query()] = True,
    ) -> InputInventoryResponse:
        return api_service.inventory(recursive=recursive)

    @router.post("/runs", response_model=RunResponse, status_code=202)
    def create_run(payload: RunCreateRequest) -> RunResponse:
        return api_service.create_run(payload)

    @router.get("/runs", response_model=list[RunResponse])
    def list_runs(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> list[RunResponse]:
        return api_service.list_runs(limit)

    @router.get("/runs/{run_id}", response_model=RunResponse)
    def get_run(run_id: str) -> RunResponse:
        return api_service.get_run(run_id)

    @router.get("/runs/{run_id}/input-status", response_model=RunInputStatusResponse)
    def get_run_input_status(run_id: str) -> RunInputStatusResponse:
        return api_service.input_status(run_id)

    @router.get(
        "/runs/{run_id}/works",
        response_model=list[WorkSummaryResponse],
    )
    def list_works(
        run_id: str,
        status: Annotated[str | None, Query()] = None,
    ) -> list[WorkSummaryResponse]:
        return api_service.list_works(run_id, status=status)

    @router.get(
        "/runs/{run_id}/works/{work_id}",
        response_model=WorkDetailResponse,
    )
    def get_work(run_id: str, work_id: str) -> WorkDetailResponse:
        return api_service.get_work(run_id, work_id)

    @router.patch(
        "/runs/{run_id}/works/{work_id}",
        response_model=WorkActionResponse,
    )
    def patch_work(
        run_id: str,
        work_id: str,
        payload: WorkPatchRequest,
    ) -> WorkActionResponse:
        return api_service.patch_work(run_id, work_id, request=payload)

    @router.post(
        "/runs/{run_id}/works/{work_id}/approve",
        response_model=WorkActionResponse,
    )
    def approve_work(run_id: str, work_id: str) -> WorkActionResponse:
        return api_service.approve_work(run_id, work_id)

    @router.post(
        "/runs/{run_id}/publish",
        response_model=PublishResponse,
    )
    def publish(run_id: str) -> PublishResponse:
        return api_service.publish(run_id)

    @router.get("/runs/{run_id}/source")
    def open_source_file(
        run_id: str,
        path: Annotated[str, Query(min_length=1)],
    ) -> FileResponse:
        source = api_service.source_file_path(run_id, path)
        media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        return FileResponse(
            source,
            media_type=media_type,
            filename=source.name,
            content_disposition_type="inline",
        )

    @router.get("/runs/{run_id}/exports/{format}")
    def download_export(run_id: str, format: str) -> FileResponse:
        path = api_service.export_path(run_id, format)
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if format == "docx"
            else "text/plain; charset=utf-8"
        )
        return FileResponse(path, media_type=media_type, filename=path.name)

    @router.get("/catalog/fields", response_model=list[CatalogFieldResponse])
    def list_catalog_fields() -> list[CatalogFieldResponse]:
        return api_service.list_catalog_fields()

    @router.get("/catalog/schemas", response_model=list[SchemaResponse])
    def list_schemas() -> list[SchemaResponse]:
        return api_service.list_schemas()

    @router.get("/catalog/schemas/{schema_id}", response_model=SchemaResponse)
    def get_schema(schema_id: str) -> SchemaResponse:
        return api_service.get_schema(schema_id)

    app.include_router(router)

    frontend_directory = root / "frontend" / "dist"
    if (frontend_directory / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")
    else:

        @app.get("/", include_in_schema=False)
        def frontend_not_built() -> JSONResponse:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "frontend_not_built",
                    "message": (
                        "Frontend build not found. Run `cd frontend`, `npm ci`, "
                        "and `npm run build`, then start RefEngine again."
                    ),
                },
            )

    return app


def _status_for(error: str) -> int:
    if error in {
        "run_not_found",
        "work_not_found",
        "schema_not_found",
        "export_not_found",
        "source_not_found",
    }:
        return 404
    if error in {"run_not_ready", "run_not_published"}:
        return 409
    if error in {
        "run_already_active",
        "reference_not_approvable",
        "publication_blocked",
        "run_failed",
    }:
        return 409
    if error in {"input_empty", "invalid_review", "invalid_status_filter"}:
        return 422
    if error == "publication_failed":
        return 500
    return 400


app = create_app()

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from refengine.api.server import run_server
from refengine.infrastructure.pdf.tesseract_ocr import (
    OcrExecutableUnavailableError,
    OcrExecutionError,
    OcrLanguageUnavailableError,
    TesseractOcrEngine,
)
from refengine.infrastructure.persistence.api_repository import ApiRepository
from refengine.infrastructure.persistence.extraction_cache import ExtractionCache
from refengine.infrastructure.persistence.review_memory import ReviewMemoryStore
from refengine.rules.catalog import validate_catalog
from refengine.services.environment import environment_report
from refengine.services.input_inventory import build_input_inventory

app = typer.Typer(no_args_is_help=True, help="RefEngine backend utilities")


@app.command("init-workspace")
def init_workspace(
    project_directory: Annotated[
        Path,
        typer.Argument(file_okay=False, help="Directory where the local workspace is created."),
    ] = Path("."),
) -> None:
    """Create the local folders used by the API and the extraction engine."""
    directories = [
        project_directory / "input",
        project_directory / "output" / "latest",
        project_directory / "output" / "history",
        project_directory / "output" / "failed",
        project_directory / "config",
        project_directory / "data" / "runs",
        project_directory / "tools" / "tesseract",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


@app.command()
def doctor(
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check the local runtime without opening or transmitting documents."""
    report = environment_report()
    if as_json:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return
    typer.echo("RefEngine diagnostics")
    typer.echo(f"  Version: {report['refengine_version']}")
    typer.echo(f"  Python: {report['python_version']}")
    typer.echo(f"  Platform: {report['platform']}")
    typer.echo(f"  Tesseract: {'available' if report['tesseract_available'] else 'not found'}")
    typer.echo(f"  OCR ready: {report['ocr_ready']}")
    typer.echo("  Privacy mode: local_only")


@app.command("rules-check")
def rules_check(
    catalog: Annotated[Path | None, typer.Option()] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate the UFV 2025 reference-rule catalog."""
    report = validate_catalog(catalog)
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo("RefEngine normative rules check")
        typer.echo(f"  Catalog: {report.catalog_id} ({report.catalog_version})")
        typer.echo(f"  Fields: {report.fields}")
        typer.echo(f"  General rules: {report.general_rules}")
        typer.echo(f"  Renderable schemas: {report.renderable_schemas}")
        typer.echo(f"  Main sections: {report.main_sections}/34")
        typer.echo(f"  Electronic schemas: {report.electronic_schemas}")
        typer.echo(f"  Local only: {report.local_only}")
        typer.echo(f"  Valid: {report.valid}")
        for error in report.errors:
            typer.echo(f"  Error: {error}")
    if not report.valid:
        raise typer.Exit(code=1)


@app.command("backend-check")
def backend_check(
    project_directory: Annotated[
        Path,
        typer.Option(file_okay=False, help="RefEngine project root."),
    ] = Path("."),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate input, local databases, output access, and OCR readiness."""
    root = project_directory.resolve()
    input_directory = root / "input"
    output_directory = root / "output"
    input_directory.mkdir(parents=True, exist_ok=True)
    output_directory.mkdir(parents=True, exist_ok=True)
    inventory = build_input_inventory(input_directory)
    environment = environment_report()
    cache_integrity = ExtractionCache(root / "config/extraction_cache.sqlite3").integrity_check()
    review_integrity = ReviewMemoryStore(root / "config/review_memory.sqlite3").integrity_check()
    api_integrity = ApiRepository(root / "data/refengine_api.sqlite3").integrity_check()
    probe = output_directory / ".refengine-write-check.tmp"
    output_writable = False
    try:
        probe.write_text("ok", encoding="utf-8")
        output_writable = probe.read_text(encoding="utf-8") == "ok"
    except OSError:
        output_writable = False
    finally:
        probe.unlink(missing_ok=True)
    source_counts = {
        "pdf": sum(item.source_type == "pdf" for item in inventory.files),
        "bibtex": sum(item.source_type == "bibtex" for item in inventory.files),
        "ris": sum(item.source_type == "ris" for item in inventory.files),
    }
    pdf_count = source_counts["pdf"]
    frontend_ready = (root / "frontend" / "dist" / "index.html").is_file()
    payload = {
        "backend_ready": (
            output_writable
            and cache_integrity.casefold() == "ok"
            and review_integrity.casefold() == "ok"
            and api_integrity.casefold() == "ok"
            and frontend_ready
            and (pdf_count == 0 or bool(environment["ocr_ready"]))
        ),
        "input_directory": str(input_directory),
        "sources": source_counts,
        "output_writable": output_writable,
        "cache_integrity": cache_integrity,
        "review_memory_integrity": review_integrity,
        "api_database_integrity": api_integrity,
        "frontend_ready": frontend_ready,
        "ocr_ready": bool(environment["ocr_ready"]),
    }
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo("RefEngine backend check")
        typer.echo(f"  Input folder: {input_directory}")
        typer.echo(
            "  Sources: "
            f"PDFs={source_counts['pdf']} | "
            f"BibTeX={source_counts['bibtex']} | RIS={source_counts['ris']}"
        )
        typer.echo(f"  Output write: {'ok' if output_writable else 'failed'}")
        typer.echo(f"  Cache database: {cache_integrity}")
        typer.echo(f"  Review memory: {review_integrity}")
        typer.echo(f"  API database: {api_integrity}")
        typer.echo(f"  Frontend build: {'ready' if frontend_ready else 'missing'}")
        typer.echo(f"  OCR: {'ready' if environment['ocr_ready'] else 'not ready'}")
        typer.echo(f"  Backend ready: {payload['backend_ready']}")
    if not payload["backend_ready"]:
        raise typer.Exit(code=1)


@app.command("cache-status")
def cache_status(
    database: Annotated[Path, typer.Option()] = Path("config/extraction_cache.sqlite3"),
) -> None:
    """Show the local extraction cache state."""
    cache = ExtractionCache(database)
    summary = cache.summary()
    typer.echo(f"Cache file: {database.resolve()}")
    typer.echo(f"Entries: {summary.entries}")
    typer.echo(f"Payload: {summary.payload_bytes} bytes")
    typer.echo(f"Integrity: {cache.integrity_check()}")


@app.command("cache-clear")
def cache_clear(
    database: Annotated[Path, typer.Option()] = Path("config/extraction_cache.sqlite3"),
) -> None:
    """Clear extraction cache without removing reviewed corrections."""
    removed = ExtractionCache(database).clear()
    typer.echo(f"Cache entries removed: {removed}")
    typer.echo("Review memory was not changed.")


@app.command("ocr-check")
def ocr_check(
    pdf: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    page: Annotated[int, typer.Option(min=1)] = 1,
    output: Annotated[Path, typer.Option()] = Path("output/ocr-smoke.txt"),
) -> None:
    """Verify OCR readiness and optionally read one PDF page."""
    report = environment_report()
    if not report["ocr_ready"]:
        typer.echo("OCR is not ready. Install Tesseract and run `refengine ocr-check`.", err=True)
        raise typer.Exit(code=2)
    engine = TesseractOcrEngine()
    try:
        engine.smoke_test()
        if pdf is None:
            typer.echo("OCR runtime smoke test: passed")
            return
        result = engine.extract_page(pdf, page - 1)
    except (
        OcrExecutableUnavailableError,
        OcrLanguageUnavailableError,
        OcrExecutionError,
    ) as exc:
        typer.echo(f"OCR runtime smoke test failed: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.text, encoding="utf-8")
    typer.echo(f"OCR runtime smoke test: passed ({result.character_count} characters)")
    typer.echo(f"Text: {output.resolve()}")


@app.command("serve")
def serve(
    port: Annotated[
        int,
        typer.Option(
            "--port",
            min=1,
            max=65535,
            help="Port used by the local application.",
        ),
    ] = 8000,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open-browser",
            help="Open the local interface after startup.",
        ),
    ] = False,
) -> None:
    """Start the local application on the loopback interface."""
    run_server(port=port, open_browser=open_browser)

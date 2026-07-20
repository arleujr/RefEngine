from __future__ import annotations

from pathlib import Path


def discover_pdfs(directory: Path, recursive: bool = True) -> list[Path]:
    """Return PDF files deterministically, including uppercase extensions."""
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.casefold() == ".pdf"),
        key=lambda path: str(path.relative_to(directory)).casefold(),
    )

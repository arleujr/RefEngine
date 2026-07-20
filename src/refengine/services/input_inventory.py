from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from refengine.services.bibtex import discover_bibtex
from refengine.services.file_discovery import discover_pdfs
from refengine.services.ris import discover_ris


@dataclass(frozen=True)
class InputFileRecord:
    relative_path: str
    source_type: str
    size_bytes: int
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class InputInventory:
    files: tuple[InputFileRecord, ...]
    fingerprint: str
    total_bytes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "files": [record.as_dict() for record in self.files],
            "fingerprint": self.fingerprint,
            "total_bytes": self.total_bytes,
        }


def build_input_inventory(directory: Path, recursive: bool = True) -> InputInventory:
    paths = [
        *((path, "pdf") for path in discover_pdfs(directory, recursive=recursive)),
        *((path, "bibtex") for path in discover_bibtex(directory, recursive=recursive)),
        *((path, "ris") for path in discover_ris(directory, recursive=recursive)),
    ]
    records: list[InputFileRecord] = []
    for path, source_type in sorted(paths, key=lambda item: str(item[0]).casefold()):
        stat = path.stat()
        records.append(
            InputFileRecord(
                relative_path=path.relative_to(directory).as_posix(),
                source_type=source_type,
                size_bytes=stat.st_size,
                sha256=sha256_file(path),
            )
        )

    digest = hashlib.sha256()
    for record in records:
        digest.update(record.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(record.source_type.encode("ascii"))
        digest.update(b"\0")
        digest.update(record.sha256.encode("ascii"))
        digest.update(b"\0")
    return InputInventory(
        files=tuple(records),
        fingerprint=digest.hexdigest(),
        total_bytes=sum(record.size_bytes for record in records),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

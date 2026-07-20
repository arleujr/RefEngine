from __future__ import annotations

import json
import locale
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

from refengine import __version__

_REQUIRED_OCR_LANGUAGES = ("por", "eng")
_OCR_CONFIG_PATH = Path("config") / "ocr.json"


class EnvironmentReport(TypedDict):
    refengine_version: str
    python_version: str
    python_executable: str
    platform: str
    tesseract_available: bool
    tesseract_command: str | None
    tesseract_version: str | None
    tessdata_directory: str | None
    tesseract_languages: list[str]
    required_ocr_languages: list[str]
    missing_ocr_languages: list[str]
    preferred_ocr_language_spec: str | None
    ocr_ready: bool
    privacy_mode: str


def load_ocr_config(project_root: Path | None = None) -> dict[str, str]:
    """Load an explicit local OCR configuration without scanning documents."""
    root = project_root or Path.cwd()
    path = root / _OCR_CONFIG_PATH
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if value is not None}


def find_tesseract_command(project_root: Path | None = None) -> Path | None:
    """Resolve configured, PATH, portable, or common Windows Tesseract installs."""
    root = project_root or Path.cwd()
    config = load_ocr_config(root)
    candidates: list[Path] = []

    configured = os.environ.get("TESSERACT_CMD") or config.get("tesseract_command")
    if configured:
        candidates.append(Path(configured))

    resolved = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if resolved:
        candidates.append(Path(resolved))

    candidates.extend(
        [
            root / "tools" / "tesseract" / "tesseract.exe",
            root / "vendor" / "tesseract" / "tesseract.exe",
        ]
    )

    if os.name == "nt":
        program_files = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        relative_paths = [
            Path("Tesseract-OCR") / "tesseract.exe",
            Path("Programs") / "Tesseract-OCR" / "tesseract.exe",
            Path("Microsoft") / "WinGet" / "Packages",
        ]
        for base in program_files:
            if not base:
                continue
            for relative in relative_paths:
                candidate = Path(base) / relative
                if candidate.is_dir() and relative.name == "Packages":
                    candidates.extend(candidate.glob("**/tesseract.exe"))
                else:
                    candidates.append(candidate)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_tessdata_directory(
    command: Path | None = None,
    project_root: Path | None = None,
) -> Path | None:
    """Resolve a language-data folder that directly contains traineddata files."""
    root = project_root or Path.cwd()
    config = load_ocr_config(root)
    candidates: list[Path] = []

    configured = os.environ.get("REFENGINE_TESSDATA_DIR") or config.get("tessdata_directory")
    if configured:
        candidates.append(Path(configured))

    tessdata_prefix = os.environ.get("TESSDATA_PREFIX")
    if tessdata_prefix:
        prefix = Path(tessdata_prefix)
        candidates.extend([prefix, prefix / "tessdata"])

    candidates.extend(
        [
            root / "tools" / "tesseract" / "tessdata",
            root / "vendor" / "tesseract" / "tessdata",
        ]
    )

    resolved_command = command or find_tesseract_command(root)
    if resolved_command is not None:
        candidates.extend(
            [
                resolved_command.parent / "tessdata",
                resolved_command.parent.parent / "share" / "tessdata",
            ]
        )

    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.traineddata")):
            return candidate.resolve()
    return None


def available_tesseract_languages(
    command: Path | None = None,
    tessdata_directory: Path | None = None,
) -> list[str]:
    """Return OCR languages without trusting localized console encoding.

    When an explicit tessdata folder is configured, the traineddata filenames
    are the source of truth. This avoids decoding localized Windows output from
    Tesseract and exactly matches the files used by the OCR engine.
    """
    if tessdata_directory is not None and tessdata_directory.is_dir():
        direct_languages = sorted(
            path.stem for path in tessdata_directory.glob("*.traineddata") if path.is_file()
        )
        if direct_languages:
            return direct_languages

    resolved = command or find_tesseract_command()
    if resolved is None:
        return []

    arguments = [str(resolved)]
    if tessdata_directory is not None:
        arguments.extend(["--tessdata-dir", str(tessdata_directory)])
    arguments.append("--list-langs")

    try:
        result = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    output = _decode_subprocess_output(result.stdout or result.stderr or b"")
    return sorted(
        line.strip()
        for line in output.splitlines()
        if line.strip() and not line.lower().startswith("list of available languages")
    )


def preferred_ocr_language_spec(
    command: Path | None = None,
    tessdata_directory: Path | None = None,
) -> str | None:
    """Prefer Portuguese plus English, while accepting either language alone."""
    available = set(available_tesseract_languages(command, tessdata_directory))
    selected = [language for language in _REQUIRED_OCR_LANGUAGES if language in available]
    return "+".join(selected) if selected else None


def environment_report(project_root: Path | None = None) -> EnvironmentReport:
    """Return local OCR diagnostics without collecting document content."""
    root = project_root or Path.cwd()
    tesseract = find_tesseract_command(root)
    tessdata = find_tessdata_directory(tesseract, root)
    languages = available_tesseract_languages(tesseract, tessdata)
    missing = [language for language in _REQUIRED_OCR_LANGUAGES if language not in languages]
    preferred = preferred_ocr_language_spec(tesseract, tessdata)
    return {
        "refengine_version": __version__,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "tesseract_available": tesseract is not None,
        "tesseract_command": str(tesseract) if tesseract else None,
        "tesseract_version": _tesseract_version(tesseract),
        "tessdata_directory": str(tessdata) if tessdata else None,
        "tesseract_languages": languages,
        "required_ocr_languages": list(_REQUIRED_OCR_LANGUAGES),
        "missing_ocr_languages": missing,
        "preferred_ocr_language_spec": preferred,
        "ocr_ready": tesseract is not None and preferred is not None,
        "privacy_mode": "local_only",
    }


def _decode_subprocess_output(payload: bytes) -> str:
    """Decode native Windows tool output without crashing reader threads."""
    if not payload:
        return ""

    encodings = [
        "utf-8",
        locale.getpreferredencoding(False),
    ]
    if os.name == "nt":
        encodings.extend(["cp1252", "cp850"])
    encodings.append("latin-1")

    seen: set[str] = set()
    for encoding in encodings:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def _tesseract_version(command: Path | None) -> str | None:
    if command is None:
        return None
    try:
        result = subprocess.run(
            [str(command), "--version"],
            check=False,
            capture_output=True,
            text=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = _decode_subprocess_output(result.stdout or result.stderr or b"")
    first_line = output.splitlines()
    return first_line[0].strip() if first_line else None

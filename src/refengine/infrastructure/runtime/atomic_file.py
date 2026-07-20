from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path


def publish_file_with_backup(
    temporary_path: Path,
    target_path: Path,
    *,
    history_directory: Path | None = None,
    history_limit: int = 10,
) -> Path:
    """Atomically publish one file and retain bounded previous versions."""
    if not temporary_path.is_file():
        raise FileNotFoundError(temporary_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if target_path.exists():
        history = history_directory or target_path.parent / "history" / "tcc"
        history.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        backup = history / f"{target_path.stem}-{timestamp}{target_path.suffix}"
        counter = 2
        while backup.exists():
            backup = history / (f"{target_path.stem}-{timestamp}-{counter}{target_path.suffix}")
            counter += 1
        shutil.copy2(target_path, backup)

    try:
        os.replace(temporary_path, target_path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise

    if backup is not None:
        history = backup.parent
        files = sorted(
            (path for path in history.iterdir() if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for obsolete in files[history_limit:]:
            obsolete.unlink(missing_ok=True)
    return target_path

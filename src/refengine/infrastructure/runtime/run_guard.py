from __future__ import annotations

import json
import os
import shutil
import socket
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import uuid4


class ConcurrentRunError(RuntimeError):
    """Raised when another RefEngine operation owns the local run lock."""


class OutputPublishError(RuntimeError):
    """Raised when a completed staging directory cannot be published safely."""


@dataclass(frozen=True)
class LockOwner:
    operation: str
    pid: int
    host: str
    started_at: str
    token: str


class RunLock:
    """Cross-platform lock file that prevents overlapping local operations.

    The lock deliberately avoids platform-specific packages. A lock older than
    ``stale_after`` is treated as abandoned and replaced. The token prevents one
    process from deleting a lock that was recreated by another process.
    """

    def __init__(
        self,
        path: Path,
        *,
        operation: str,
        stale_after: timedelta = timedelta(hours=12),
    ) -> None:
        self.path = path
        self.operation = operation
        self.stale_after = stale_after
        self._owner: LockOwner | None = None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self) -> LockOwner:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        owner = LockOwner(
            operation=self.operation,
            pid=os.getpid(),
            host=socket.gethostname(),
            started_at=datetime.now(UTC).isoformat(),
            token=uuid4().hex,
        )
        payload = json.dumps(owner.__dict__, ensure_ascii=False, indent=2)

        for attempt in range(2):
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError as exc:
                if attempt == 0 and self._remove_stale_lock():
                    continue
                existing = self._read_owner()
                detail = (
                    f" operation={existing.operation}, pid={existing.pid}, "
                    f"host={existing.host}, started_at={existing.started_at}"
                    if existing is not None
                    else ""
                )
                raise ConcurrentRunError(
                    "Another RefEngine operation is already running."
                    f"{detail}. Close it before starting a new run."
                ) from exc
            else:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                self._owner = owner
                return owner

        raise ConcurrentRunError("Could not acquire the RefEngine run lock.")

    def release(self) -> None:
        if self._owner is None:
            return
        existing = self._read_owner()
        if existing is not None and existing.token != self._owner.token:
            self._owner = None
            return
        try:
            self.path.unlink(missing_ok=True)
        finally:
            self._owner = None

    def _remove_stale_lock(self) -> bool:
        existing = self._read_owner()
        if (
            existing is not None
            and existing.host == socket.gethostname()
            and not _pid_exists(existing.pid)
        ):
            try:
                self.path.unlink()
            except OSError:
                return False
            return True
        try:
            modified_at = datetime.fromtimestamp(
                self.path.stat().st_mtime,
                tz=UTC,
            )
        except OSError:
            return False
        if datetime.now(UTC) - modified_at <= self.stale_after:
            return False
        try:
            self.path.unlink()
        except OSError:
            return False
        return True

    def _read_owner(self) -> LockOwner | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return LockOwner(
                operation=str(payload["operation"]),
                pid=int(payload["pid"]),
                host=str(payload["host"]),
                started_at=str(payload["started_at"]),
                token=str(payload["token"]),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None


class OutputTransaction:
    """Write a complete run in staging and publish it without partial output.

    A previous target is moved to ``history`` only after every exporter and
    database check succeeds. If publication fails, the previous target is
    restored. Fatal runs are retained under ``failed`` for diagnosis while the
    last successful output remains untouched.
    """

    def __init__(
        self,
        target: Path,
        *,
        run_id: str | None = None,
        history_limit: int = 10,
    ) -> None:
        if history_limit < 0:
            raise ValueError("history_limit must be non-negative")
        self.target = target
        self.run_id = run_id or new_run_id()
        self.history_limit = history_limit
        self.root = target.parent
        self.staging = self.root / ".staging" / f"{target.name}-{self.run_id}"
        self.history_root = self.root / "history"
        self.failed_root = self.root / "failed"
        self._published = False
        self._entered = False
        self._previous: Path | None = None
        self.failed_output: Path | None = None

    def __enter__(self) -> Self:
        self.root.mkdir(parents=True, exist_ok=True)
        self._cleanup_abandoned_staging()
        if self.staging.exists():
            shutil.rmtree(self.staging)
        self.staging.mkdir(parents=True, exist_ok=False)
        (self.staging / ".run.json").write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "started_at": datetime.now(UTC).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._published and self.staging.exists():
            self.failed_output = self._retain_failed_staging()

    @property
    def published(self) -> bool:
        return self._published

    def publish(self) -> Path:
        if not self._entered or not self.staging.is_dir():
            raise OutputPublishError("Output transaction has no staging directory.")
        if self._published:
            return self.target

        previous: Path | None = None
        try:
            (self.staging / ".run.json").unlink(missing_ok=True)
            if self.target.exists():
                self.history_root.mkdir(parents=True, exist_ok=True)
                previous = self._unique_history_path()
                self.target.rename(previous)
                self._previous = previous
            self.staging.rename(self.target)
            self._published = True
            self._cleanup_history()
            self._cleanup_empty_staging_root()
            return self.target
        except OSError as exc:
            if previous is not None and previous.exists() and not self.target.exists():
                with suppress(OSError):
                    previous.rename(self.target)
            raise OutputPublishError(
                f"Could not publish completed output to {self.target}. "
                "The previous successful output was preserved when possible."
            ) from exc

    def _cleanup_abandoned_staging(self) -> None:
        staging_root = self.root / ".staging"
        if not staging_root.is_dir():
            return
        now = datetime.now(UTC)
        for candidate in staging_root.iterdir():
            if not candidate.is_dir():
                continue
            marker = candidate / ".run.json"
            abandoned = False
            try:
                payload = json.loads(marker.read_text(encoding="utf-8"))
                pid = int(payload.get("pid", 0))
                host = str(payload.get("host", ""))
                if host == socket.gethostname() and not _pid_exists(pid):
                    abandoned = True
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                try:
                    modified = datetime.fromtimestamp(
                        candidate.stat().st_mtime,
                        tz=UTC,
                    )
                    abandoned = now - modified > timedelta(hours=12)
                except OSError:
                    continue
            if abandoned:
                shutil.rmtree(candidate, ignore_errors=True)

    def _retain_failed_staging(self) -> Path | None:
        if not self.staging.exists():
            return None
        self.failed_root.mkdir(parents=True, exist_ok=True)
        destination = self.failed_root / self.run_id
        counter = 2
        while destination.exists():
            destination = self.failed_root / f"{self.run_id}-{counter}"
            counter += 1
        try:
            self.staging.rename(destination)
        except OSError:
            shutil.rmtree(self.staging, ignore_errors=True)
            return None
        self._cleanup_empty_staging_root()
        return destination

    def _unique_history_path(self) -> Path:
        previous_run_id = "previous-run"
        timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        manifest = self.target / "run_manifest.json"
        if manifest.is_file():
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                previous_run_id = str(payload.get("run_id") or previous_run_id)
                finished_at = payload.get("finished_at")
                if isinstance(finished_at, str):
                    timestamp = (
                        datetime.fromisoformat(finished_at).astimezone().strftime("%Y%m%d-%H%M%S")
                    )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        candidate = self.history_root / f"{timestamp}-{previous_run_id}"
        counter = 2
        while candidate.exists():
            candidate = self.history_root / f"{timestamp}-{previous_run_id}-{counter}"
            counter += 1
        return candidate

    def _cleanup_history(self) -> None:
        if not self.history_root.exists():
            return
        directories = sorted(
            (path for path in self.history_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for obsolete in directories[self.history_limit :]:
            shutil.rmtree(obsolete, ignore_errors=True)

    def _cleanup_empty_staging_root(self) -> None:
        staging_root = self.root / ".staging"
        with suppress(OSError):
            staging_root.rmdir()


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            from ctypes import WinDLL

            kernel32 = WinDLL("kernel32", use_last_error=True)
            process_query_limited_information = 0x1000
            handle = kernel32.OpenProcess(
                process_query_limited_information,
                False,
                pid,
            )
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        except (AttributeError, OSError):
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


def new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:8]}"

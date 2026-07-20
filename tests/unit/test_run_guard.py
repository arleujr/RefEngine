import json
import os
import socket
from datetime import timedelta
from pathlib import Path

import pytest

from refengine.infrastructure.runtime.run_guard import (
    ConcurrentRunError,
    OutputTransaction,
    RunLock,
)


def test_run_lock_rejects_overlapping_operations(tmp_path: Path) -> None:
    lock_path = tmp_path / "refengine.lock"

    with (
        RunLock(lock_path, operation="ingest"),
        pytest.raises(ConcurrentRunError),
        RunLock(lock_path, operation="api-review"),
    ):
        pass

    with RunLock(lock_path, operation="api-review"):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_stale_lock_is_recovered(tmp_path: Path) -> None:
    lock_path = tmp_path / "refengine.lock"
    lock_path.write_text("not-json", encoding="utf-8")
    os.utime(lock_path, (1, 1))

    with RunLock(
        lock_path,
        operation="ingest",
        stale_after=timedelta(seconds=1),
    ):
        assert lock_path.exists()


def test_output_is_published_only_after_completion(tmp_path: Path) -> None:
    target = tmp_path / "output" / "latest"
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old", encoding="utf-8")

    with OutputTransaction(target, run_id="run-1", history_limit=2) as transaction:
        (transaction.staging / "new.txt").write_text("new", encoding="utf-8")
        transaction.publish()

    assert not (target / "old.txt").exists()
    assert (target / "new.txt").read_text(encoding="utf-8") == "new"
    history = list((target.parent / "history").iterdir())
    assert len(history) == 1
    assert (history[0] / "old.txt").read_text(encoding="utf-8") == "old"


def test_failed_run_keeps_previous_output_and_diagnostics(tmp_path: Path) -> None:
    target = tmp_path / "output" / "latest"
    target.mkdir(parents=True)
    (target / "stable.txt").write_text("stable", encoding="utf-8")
    transaction = OutputTransaction(target, run_id="failed-run")

    with pytest.raises(RuntimeError), transaction:
        (transaction.staging / "refengine.log").write_text(
            "failure",
            encoding="utf-8",
        )
        raise RuntimeError("boom")

    assert (target / "stable.txt").read_text(encoding="utf-8") == "stable"
    assert transaction.failed_output is not None
    assert (transaction.failed_output / "refengine.log").exists()


def test_dead_process_lock_is_recovered_immediately(tmp_path: Path) -> None:
    lock_path = tmp_path / "refengine.lock"
    lock_path.write_text(
        json.dumps(
            {
                "operation": "ingest",
                "pid": 99999999,
                "host": socket.gethostname(),
                "started_at": "2026-07-14T00:00:00+00:00",
                "token": "dead",
            }
        ),
        encoding="utf-8",
    )

    with RunLock(lock_path, operation="ingest"):
        assert lock_path.exists()


def test_abandoned_staging_from_dead_process_is_cleaned(tmp_path: Path) -> None:
    target = tmp_path / "output" / "latest"
    abandoned = target.parent / ".staging" / "latest-old-run"
    abandoned.mkdir(parents=True)
    (abandoned / ".run.json").write_text(
        json.dumps(
            {
                "run_id": "old-run",
                "pid": 99999999,
                "host": socket.gethostname(),
                "started_at": "2026-07-14T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (abandoned / "partial.txt").write_text("partial", encoding="utf-8")

    with OutputTransaction(target, run_id="new-run") as transaction:
        assert not abandoned.exists()
        (transaction.staging / "complete.txt").write_text("ok", encoding="utf-8")
        transaction.publish()

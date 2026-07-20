from pathlib import Path

from refengine.domain.enums import ApiRunStatus
from refengine.infrastructure.persistence.api_repository import ApiRepository


def test_api_repository_recovers_interrupted_local_runs(tmp_path: Path) -> None:
    repository = ApiRepository(tmp_path / "api.sqlite3")
    repository.create_run(
        run_id="run-1",
        access_date="2026-07-14",
        settings={},
        input_inventory={"files": []},
    )
    repository.set_status("run-1", ApiRunStatus.PROCESSING)

    assert repository.recover_interrupted_runs() == 1
    run = repository.get_run("run-1")

    assert run is not None
    assert run.status is ApiRunStatus.FAILED
    assert "stopped" in (run.error_message or "")
    assert repository.integrity_check().casefold() == "ok"

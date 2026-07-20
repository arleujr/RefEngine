from pathlib import Path

import pytest

from refengine.api.schemas import RunCreateRequest
from refengine.api.service import RefEngineApiService

_BIBTEX = """@article{demo,
  author = {Silva, Ana},
  title = {Snapshot original},
  journal = {Revista Exemplo},
  year = {2025}
}
"""


def test_snapshot_rejects_a_file_changed_between_fingerprint_and_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_directory = tmp_path / "input"
    input_directory.mkdir()
    source = input_directory / "source.bib"
    source.write_text(_BIBTEX, encoding="utf-8")
    service = RefEngineApiService(tmp_path)
    inventory = service.inventory()
    record = service.repository.create_run(
        run_id="snapshot-test",
        access_date="2026-07-14",
        settings=RunCreateRequest().model_dump(mode="json"),
        input_inventory=inventory.model_dump(mode="json", exclude={"input_directory", "counts"}),
    )

    from refengine.api import service as service_module

    original_copy = service_module.shutil.copy2

    def mutate_then_copy(source_path: Path, destination: Path) -> None:
        Path(source_path).write_text(
            _BIBTEX.replace("Snapshot original", "Snapshot alterado"),
            encoding="utf-8",
        )
        original_copy(source_path, destination)

    monkeypatch.setattr(service_module.shutil, "copy2", mutate_then_copy)

    with pytest.raises(RuntimeError, match="changed while RefEngine was creating"):
        service._prepare_input_snapshot(record, tmp_path / "data" / "runs" / record.run_id)

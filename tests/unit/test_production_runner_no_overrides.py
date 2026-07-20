from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_has_no_override_module_or_cli_option() -> None:
    assert not (ROOT / "src/refengine/services/overrides.py").exists()
    cli = (ROOT / "src/refengine/cli.py").read_text(encoding="utf-8")
    assert "--overrides" not in cli
    assert "metadata_overrides" not in cli


def test_source_repository_has_no_batch_launchers() -> None:
    assert not list(ROOT.rglob("*.bat"))


def test_server_is_loopback_only() -> None:
    server = (ROOT / "src/refengine/api/server.py").read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in server
    assert 'host="0.0.0.0"' not in server

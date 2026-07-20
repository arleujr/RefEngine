from pathlib import Path

from typer.testing import CliRunner

from refengine.cli import app

runner = CliRunner()


def test_init_workspace_creates_expected_directories(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init-workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / "input").is_dir()
    assert (tmp_path / "output" / "latest").is_dir()
    assert (tmp_path / "output" / "history").is_dir()
    assert (tmp_path / "data" / "runs").is_dir()
    assert not (tmp_path / "config" / "metadata_overrides.yaml").exists()


def test_cli_exposes_backend_server_not_spreadsheet_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "serve" in result.output
    assert "apply-review" not in result.output
    assert "ingest" not in result.output


def test_serve_command_exposes_cross_platform_options() -> None:
    result = runner.invoke(app, ["serve", "--help"])

    assert result.exit_code == 0
    assert "--port" in result.output
    assert "--open-browser" in result.output

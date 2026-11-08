"""Updater orchestration without changing the login service, dependencies, or database."""

import subprocess

import pytest
from test_service import script


def test_update_runs_in_workspace_in_order_and_syncs_only_after_stopping(
    monkeypatch, tmp_path
):
    updater = script("update")
    root = tmp_path / "Budget & plans"
    monkeypatch.setattr(updater, "ROOT", root)
    monkeypatch.setattr(updater, "preflight", lambda: None)
    calls = []
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )
    assert updater.main([]) == 0
    assert calls == [
        (command, {"cwd": root, "check": True}) for _, command in updater.STEPS
    ]
    assert updater.STEPS[0][1][2] == "--no-sync"
    assert updater.STEPS[1][1] == ("uv", "sync", "--locked")


@pytest.mark.parametrize("failed_step", range(6))
def test_update_stops_at_failure_without_running_later_steps(
    monkeypatch, capsys, failed_step
):
    updater = script("update")
    monkeypatch.setattr(updater, "preflight", lambda: None)
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        if len(calls) == failed_step + 1:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(updater.subprocess, "run", run)
    assert updater.main([]) == 1
    assert calls == [command for _, command in updater.STEPS[: failed_step + 1]]
    error = capsys.readouterr().err
    assert updater.STEPS[failed_step][0] in error
    if 0 < failed_step < 5:
        assert "remains stopped" in error


def test_update_dry_run_never_checks_or_changes_system(monkeypatch, capsys):
    updater = script("update")
    monkeypatch.setattr(
        updater, "preflight", lambda: pytest.fail("Dry-run checked system")
    )
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *_a, **_k: pytest.fail("Dry-run executed command"),
    )
    assert updater.main(["--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "uv sync --locked" in output and "alembic upgrade head" in output
    assert "npm run build --prefix frontend" in output


def test_preflight_failure_leaves_running_service_alone(monkeypatch, capsys):
    updater = script("update")

    def fail():
        raise RuntimeError("Install npm first")

    monkeypatch.setattr(updater, "preflight", fail)
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *_a, **_k: pytest.fail("Stopped before preflight passed"),
    )
    assert updater.main([]) == 1
    assert "Install npm first" in capsys.readouterr().err

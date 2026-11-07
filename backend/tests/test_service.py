"""Startup checks and credential-free LaunchAgent generation, without system mutations."""

import importlib.util
import plistlib
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launch_agent_uses_single_venv_process_absolute_paths_and_no_credentials(
    tmp_path,
):
    service = script("macos_service")
    root = tmp_path / "Budget & plans"
    home = tmp_path / "Home"
    agent = plistlib.loads(plistlib.dumps(service.launch_agent(root, home, 8020)))
    assert agent["ProgramArguments"] == [
        str(root / ".venv/bin/python"),
        str(root / "scripts/run_service.py"),
        "--port",
        "8020",
    ]
    assert agent["WorkingDirectory"] == str(root)
    assert agent["RunAtLoad"] and agent["KeepAlive"]
    assert agent["ThrottleInterval"] == 30 and agent["ExitTimeOut"] == 60
    assert agent["EnvironmentVariables"] == {"PYTHONUNBUFFERED": "1"}
    assert "DATABASE_URL" not in str(agent) and "PASS" not in str(agent)


def test_dry_run_does_not_create_home_files(tmp_path, monkeypatch, capsys):
    service = script("macos_service")
    home = tmp_path / "nonexistent"
    monkeypatch.setattr(service.Path, "home", lambda: home)
    assert service.main(["install", "--dry-run"]) == 0
    assert plistlib.loads(capsys.readouterr().out.encode())["Label"] == "local.abacus"
    assert not home.exists()


def test_waits_for_readiness_without_log_flooding(monkeypatch):
    runner = script("run_service")
    reasons = iter(["database", "database", "port", None])
    delays = []
    messages = []
    monkeypatch.setattr(runner.time, "sleep", delays.append)
    monkeypatch.setattr(runner.logging, "warning", messages.append)
    runner.wait_until_ready(lambda: next(reasons))
    assert delays == [5, 5, 5] and messages == ["database", "port"]


def test_busy_port_never_starts_another_database_app_worker(tmp_path, monkeypatch):
    runner = script("run_service")
    index = tmp_path / "frontend/dist/index.html"
    index.parent.mkdir(parents=True)
    index.write_text("test")
    monkeypatch.setattr(runner, "port_available", lambda port: False)
    monkeypatch.setattr(
        runner,
        "database_problem",
        lambda root: (_ for _ in ()).throw(
            AssertionError("Should wait for existing server")
        ),
    )
    assert "already in use" in runner.readiness_problem(tmp_path, 8017)
    index.unlink()
    assert "Frontend build missing" in runner.readiness_problem(tmp_path, 8017)


def test_schema_mismatch_waits_for_explicit_upgrade(monkeypatch, tmp_path):
    runner = script("run_service")
    engine = MagicMock()
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *a, **k: engine)
    context = MagicMock()
    context.get_current_heads.return_value = ["0010"]
    monkeypatch.setattr(
        "alembic.migration.MigrationContext.configure", lambda *a: context
    )
    scripts = MagicMock()
    scripts.get_heads.return_value = ["0011"]
    monkeypatch.setattr("alembic.script.ScriptDirectory", lambda *a: scripts)
    assert "migrations are pending" in runner.database_problem(tmp_path)
    context.get_current_heads.return_value = ["0011"]
    assert runner.database_problem(tmp_path) is None
    assert engine.dispose.call_count == 2


def test_database_errors_do_not_expose_credentials(monkeypatch, tmp_path):
    from sqlalchemy.exc import OperationalError

    runner = script("run_service")
    engine = MagicMock()
    engine.connect.side_effect = OperationalError(
        "password=private-secret", {}, Exception("private-secret")
    )
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *a, **k: engine)
    message = runner.database_problem(tmp_path)
    assert "Waiting for PostgreSQL" in message and "private-secret" not in message
    engine.dispose.assert_called_once()


def test_start_enables_before_bootstrap_and_existing_job_is_not_duplicated(
    monkeypatch, tmp_path
):
    service = script("macos_service")
    calls = []
    monkeypatch.setattr(service, "control", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(service, "registered", lambda target: False)
    path = tmp_path / "agent.plist"
    service.start(path, "gui/501/local.abacus", "gui/501")
    assert calls == [
        ("enable", "gui/501/local.abacus"),
        ("bootstrap", "gui/501", str(path)),
    ]
    calls.clear()
    monkeypatch.setattr(service, "registered", lambda target: True)
    service.start(path, "gui/501/local.abacus", "gui/501")
    assert calls == [
        ("enable", "gui/501/local.abacus"),
        ("kickstart", "gui/501/local.abacus"),
    ]


def test_port_check_blocks_active_listener_but_allows_recently_closed_connections():
    import socket

    runner = script("run_service")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert not runner.port_available(port)
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            peer, _ = server.accept()
            with peer:
                peer.shutdown(socket.SHUT_WR)
                assert client.recv(1) == b""
    assert runner.port_available(port)


def test_restart_waits_for_old_job_removal_before_loading_new_job(monkeypatch):
    service = script("macos_service")
    states = iter([True, True, True, False])
    calls = []
    monkeypatch.setattr(service, "registered", lambda target: next(states))
    monkeypatch.setattr(service, "control", lambda *args: calls.append(args))
    monkeypatch.setattr(
        service.time, "sleep", lambda delay: calls.append(("wait", delay))
    )
    service.unload("gui/501/local.abacus")
    assert calls == [("bootout", "gui/501/local.abacus"), ("wait", 0.2), ("wait", 0.2)]

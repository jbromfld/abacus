"""Provisioning helper redacts admin data and never enables the optional feature."""

from types import SimpleNamespace

from script_helpers import script
from sqlalchemy.engine import URL


def setup(monkeypatch, tmp_path):
    helper = script("setup_memory")
    babar = tmp_path / "Babar workspace"
    python = babar / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    env = tmp_path / ".env"
    env.write_text("# retain me\nUSER=main\nADVISOR_PASS=synthetic-reader-secret\n")
    monkeypatch.setattr(helper, "ENV_FILE", env)
    monkeypatch.setattr(
        helper,
        "database_url",
        lambda: URL.create(
            "postgresql+psycopg",
            username="admin",
            password="synthetic-admin-secret",
            host="127.0.0.1",
            database="budget",
        ),
    )
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "synthetic-search-secret")
    monkeypatch.setenv("ADVISOR_PASS", "synthetic-reader-secret")
    return helper, babar, env


def test_provisioning_passes_only_admin_env_and_saves_local_paths(
    monkeypatch, tmp_path, capsys
):
    helper, babar, env = setup(monkeypatch, tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(helper.subprocess, "run", run)
    assert helper.main(["--babar", str(babar)]) == 0
    command, kwargs = calls[0]
    assert "synthetic-admin-secret" not in str(command)
    assert kwargs["env"]["PGPASSWORD"] == "synthetic-admin-secret"
    assert not {"BRAVE_SEARCH_API_KEY", "ADVISOR_PASS", "PASS"} & kwargs["env"].keys()
    assert "abacus-advisor" in command and "--rotate-password" not in command
    assert "MEMORA_PYTHON=" in env.read_text() and "# retain me" in env.read_text()
    assert "advisor_memory_enabled" not in env.read_text()
    assert env.stat().st_mode & 0o777 == 0o600
    assert "secret" not in capsys.readouterr().out


def test_provisioning_failure_preserves_config_and_redacts_child_output(
    monkeypatch, tmp_path, capsys
):
    helper, babar, env = setup(monkeypatch, tmp_path)
    original = env.read_text()
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stderr=b"synthetic-admin-secret postgres://private"
        ),
    )
    assert helper.main(["--babar", str(babar)]) == 1
    assert env.read_text() == original
    output = capsys.readouterr().err
    assert "synthetic-admin-secret" not in output and "postgres://" not in output

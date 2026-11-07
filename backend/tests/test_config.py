from abacus import config


def test_discrete_credentials_are_loaded_without_url_interpolation(
    monkeypatch, tmp_path
):
    env = tmp_path / ".env"
    env.write_text(
        "HOST=127.0.0.1\nPORT=5433\nUSER=budget_user\nPASS='p@ss:/# ${HOME} with spaces'\nDATABASE=budget_local\n"
    )
    monkeypatch.setattr(config, "ENV_FILE", env)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("USER", "login_shell_user")
    url = config.database_url()
    assert url.username == "budget_user"
    assert url.password == "p@ss:/# ${HOME} with spaces"
    assert url.host == "127.0.0.1" and url.port == 5433
    assert url.database == "budget_local"
    assert "p@ss" not in str(url)


def test_explicit_database_url_takes_precedence(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("USER=file_user\nDATABASE=file_database\n")
    monkeypatch.setattr(config, "ENV_FILE", env)
    override = "postgresql+psycopg://test_user:test_pass@localhost/abacus_test"
    monkeypatch.setenv("DATABASE_URL", override)
    assert config.database_url() == override


def test_process_attributes_without_env_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for name, value in {
        "HOST": "localhost",
        "PORT": "5434",
        "USER": "configured_user",
        "PASS": "secret",
        "DATABASE": "configured_db",
    }.items():
        monkeypatch.setenv(name, value)
    url = config.database_url()
    assert (url.host, url.port, url.username, url.password, url.database) == (
        "localhost",
        5434,
        "configured_user",
        "secret",
        "configured_db",
    )

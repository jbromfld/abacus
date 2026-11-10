"""Test privileges independently of PostgreSQL's read-only transaction setting."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from abacus import config
from abacus.advisor_access import (
    ADVISOR_TABLES,
    verify_advisor_access,
)
from abacus.advisor_setup import (
    AdvisorSetupError,
    check_connection,
    persist_credentials,
    provision_advisor,
)
from abacus.db import engine, read_only_session
from abacus.models import Settings
from fastapi import HTTPException
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError


@pytest.fixture
def reader_engine(advisor_credentials):
    reader = create_engine(
        engine.url.set(
            username=advisor_credentials[0], password=advisor_credentials[1]
        ),
        hide_parameters=True,
    )
    yield reader
    reader.dispose()


def test_role_can_read_only_the_explicit_allowlist(reader_engine):
    with reader_engine.connect() as connection:
        assert connection.scalar(text("SELECT current_user")) != engine.url.username
        verify_advisor_access(
            connection, connection.scalar(text("SELECT current_user"))
        )
        connection.execute(text("SELECT id, name FROM accounts LIMIT 0"))
        for name in ADVISOR_TABLES:
            connection.execute(text(f'SELECT 1 FROM public."{name}" LIMIT 0'))


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO month_status(month,complete) VALUES ('1999-01',true)",
        "UPDATE settings SET currency=currency",
        "DELETE FROM month_status WHERE month='1999-01'",
        "TRUNCATE month_status",
        "ALTER TABLE settings ADD COLUMN advisor_bad int",
        "DROP TABLE month_status",
        "CREATE TABLE public.advisor_bad(id int)",
        "SELECT csv_mapping FROM accounts LIMIT 0",
        "SELECT stale_alert_enabled FROM accounts LIMIT 0",
        "UPDATE accounts SET name=name",
        "SELECT 1 FROM imports LIMIT 0",
        "SELECT 1 FROM import_pages LIMIT 0",
    ],
)
def test_read_write_transaction_still_cannot_write_or_read_unapproved_tables(
    reader_engine, statement
):
    with reader_engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ WRITE"))
        assert connection.scalar(text("SHOW transaction_read_only")) == "off"
        with pytest.raises(DBAPIError) as error:
            connection.execute(text(statement))
        assert error.value.orig.sqlstate == "42501"
        connection.rollback()


def test_cannot_switch_to_the_application_role(reader_engine):
    with engine.connect() as admin:
        app_role = admin.scalar(text("SELECT current_user"))
    with reader_engine.connect() as connection:
        with pytest.raises(DBAPIError) as error:
            connection.exec_driver_sql(
                "SET ROLE " + engine.dialect.identifier_preparer.quote(app_role)
            )
        assert error.value.orig.sqlstate == "42501"


def test_missing_credentials_fail_only_advisor_without_writable_fallback(
    client, db, monkeypatch
):
    db.get(Settings, 1).advisor_enabled = True
    db.commit()
    monkeypatch.delenv("ADVISOR_PASS")
    with monkeypatch.context() as patch:
        patch.setattr(
            "abacus.db.Session",
            lambda: pytest.fail("Advisor used the writable factory"),
        )
        response = client.post(
            "/api/advisor/chat", json={"month": "2026-11", "message": "Savings?"}
        )
    assert (
        response.status_code == 503 and "setup_advisor.py" in response.json()["detail"]
    )
    assert client.get("/api/settings").status_code == 200


def test_authentication_failure_is_redacted_and_never_falls_back(client, monkeypatch):
    secret = "PASSWORD_CANARY_DO_NOT_PRINT"

    def fail():
        raise OperationalError("private URL " + secret, {}, Exception(secret))

    monkeypatch.setattr("abacus.db.advisor_session_factory", fail)
    response = client.post(
        "/api/advisor/chat", json={"month": "2026-11", "message": "Savings?"}
    )
    assert response.status_code == 503 and secret not in response.text


def test_insufficient_grants_fail_closed_and_idempotent_setup_repairs(
    reader_engine, advisor_credentials, client
):
    role, password = advisor_credentials
    with engine.begin() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("REVOKE SELECT ON settings FROM {}").format(
                    sql.Identifier(role)
                )
            )
    try:
        response = client.post(
            "/api/advisor/chat", json={"month": "2026-11", "message": "Savings?"}
        )
        assert response.status_code == 503
    finally:
        assert provision_advisor(engine.url, role, password) == password
    with reader_engine.connect() as connection:
        verify_advisor_access(connection, role)


def test_unexpected_direct_grants_are_reconciled_and_future_tables_not_auto_granted(
    advisor_credentials,
):
    role, password = advisor_credentials
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE public.advisor_future_test(id int)"))
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("GRANT UPDATE ON settings TO {}").format(sql.Identifier(role))
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON accounts TO {}").format(sql.Identifier(role))
            )
            cursor.execute(
                sql.SQL("GRANT SELECT (id) ON imports TO {}").format(
                    sql.Identifier(role)
                )
            )
    try:
        with pytest.raises(HTTPException) as error:
            with contextmanager(read_only_session)():
                pass
        assert error.value.status_code == 503
        assert provision_advisor(engine.url, role, password) == password
        with contextmanager(read_only_session)() as reader:
            assert (
                reader.scalar(
                    text(
                        "SELECT has_table_privilege(current_user,'advisor_future_test','SELECT')"
                    )
                )
                is False
            )
    finally:
        provision_advisor(engine.url, role, password)
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE advisor_future_test"))


def test_unmanaged_role_is_never_adopted_or_modified():
    role = "abacus_test_unmanaged_" + uuid4().hex[:10]
    with engine.begin() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role))
            )
    try:
        with pytest.raises(AdvisorSetupError, match="unrelated"):
            provision_advisor(engine.url, role)
        with engine.connect() as connection:
            assert not connection.scalar(
                text("SELECT rolcanlogin FROM pg_roles WHERE rolname=:role"),
                {"role": role},
            )
    finally:
        with engine.begin() as connection:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_password_rotation_is_explicit_and_managed_role_can_be_recovered():
    role = "abacus_test_recovery_" + uuid4().hex[:10]
    try:
        first = provision_advisor(engine.url, role)
        assert provision_advisor(engine.url, role, first) == first
        with pytest.raises(AdvisorSetupError, match="rotate-password"):
            provision_advisor(engine.url, role)
        second = provision_advisor(engine.url, role, rotate=True)
        assert second != first
        check_connection(engine.url.set(username=role, password=second))
    finally:
        with engine.begin() as connection:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_atomic_dotenv_persistence_preserves_settings_and_private_permissions(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# local\nPASS='writer secret'\nDATABASE=abacus_test\nADVISOR_USER=old\n"
    )
    persist_credentials(path, "abacus_advisor", "reader '$ with spaces")
    from dotenv import dotenv_values

    values = dotenv_values(path, interpolate=False)
    assert values["PASS"] == "writer secret" and values["DATABASE"] == "abacus_test"
    assert values["ADVISOR_PASS"] == "reader '$ with spaces"
    assert path.read_text().startswith("# local\n")
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".env.advisor-*"))


def test_advisor_url_inherits_resolved_transport_but_never_writer_credentials(
    monkeypatch, tmp_path
):
    path = tmp_path / ".env"
    path.write_text("ADVISOR_USER=reader\nADVISOR_PASS='r@/# : secret'\n")
    monkeypatch.setattr(config, "ENV_FILE", path)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://writer:private@127.0.0.1:5433/abacus_test?sslmode=require&application_name=budget",
    )
    url = config.advisor_database_url()
    assert (url.username, url.password) == ("reader", "r@/# : secret")
    assert (url.host, url.port, url.database) == ("127.0.0.1", 5433, "abacus_test")
    assert dict(url.query) == {"sslmode": "require", "application_name": "budget"}
    assert "secret" not in str(url)


def test_memberships_are_rejected_without_silently_revoking_them(
    advisor_credentials, client
):
    role, password = advisor_credentials
    parent = "abacus_test_parent_" + uuid4().hex[:10]
    with engine.begin() as connection:
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(parent))
            )
            cursor.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(parent), sql.Identifier(role)
                )
            )
    try:
        assert (
            client.post(
                "/api/advisor/chat", json={"month": "2026-11", "message": "Savings?"}
            ).status_code
            == 503
        )
        with pytest.raises(AdvisorSetupError, match="memberships"):
            provision_advisor(engine.url, role, password)
    finally:
        with engine.begin() as connection:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("REVOKE {} FROM {}").format(
                        sql.Identifier(parent), sql.Identifier(role)
                    )
                )
                cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(parent)))


def test_public_write_privileges_are_rejected_and_never_changed_by_setup(
    advisor_credentials,
):
    role, password = advisor_credentials
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE public.advisor_public_test(id int)"))
        connection.execute(text("GRANT UPDATE ON advisor_public_test TO PUBLIC"))
    try:
        with pytest.raises(AdvisorSetupError, match="verification failed"):
            provision_advisor(engine.url, role, password)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT has_table_privilege(:role,'advisor_public_test','UPDATE')"
                    ),
                    {"role": role},
                )
                is True
            )
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE advisor_public_test"))
    assert provision_advisor(engine.url, role, password) == password


def test_same_user_credentials_are_not_accepted(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    path.write_text("ADVISOR_USER=writer\nADVISOR_PASS=reader-secret\n")
    monkeypatch.setattr(config, "ENV_FILE", path)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://writer:writer-secret@localhost/abacus_test",
    )
    with pytest.raises(ValueError, match="Dedicated"):
        config.advisor_database_url()


def test_setup_error_does_not_echo_password_or_connection_url(monkeypatch, capsys):
    from test_service import script

    setup = script("setup_advisor")

    def fail():
        raise ValueError("postgresql://writer:PRIVATE_PASSWORD@host/private")

    monkeypatch.setattr(setup, "advisor_database_url", fail)
    assert setup.main(["--check"]) == 1
    output = capsys.readouterr()
    assert "PRIVATE_PASSWORD" not in output.err + output.out
    assert "postgresql://" not in output.err + output.out


def test_unexpected_function_ownership_blocks_requests_and_provisioning(
    advisor_credentials, client
):
    role, password = advisor_credentials
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION public.advisor_owner_probe() RETURNS int LANGUAGE sql AS $$ SELECT 1 $$"
            )
        )
        with connection.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "ALTER FUNCTION public.advisor_owner_probe() OWNER TO {}"
                ).format(sql.Identifier(role))
            )
    try:
        assert (
            client.post(
                "/api/advisor/chat", json={"month": "2026-11", "message": "Savings?"}
            ).status_code
            == 503
        )
        with pytest.raises(AdvisorSetupError, match="ownership"):
            provision_advisor(engine.url, role, password)
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP FUNCTION public.advisor_owner_probe()"))

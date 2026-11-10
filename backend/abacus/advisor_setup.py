"""Explicit, idempotent provisioning for the managed local advisor login."""

import os
import re
import secrets
import tempfile
from pathlib import Path

import psycopg
from dotenv import set_key
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .advisor_access import (
    ADVISOR_COLUMNS,
    ADVISOR_TABLES,
    AdvisorAccessError,
    verify_advisor_access,
)


class AdvisorSetupError(RuntimeError):
    pass


def check_connection(url):
    engine = create_engine(
        url, hide_parameters=True, connect_args={"connect_timeout": 5}
    )
    try:
        with engine.connect() as connection:
            connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            verify_advisor_access(connection, url.username)
            for table in ADVISOR_TABLES:
                connection.execute(text(f'SELECT 1 FROM public."{table}" LIMIT 0'))
    except (SQLAlchemyError, AdvisorAccessError):
        raise AdvisorSetupError(
            "Advisor verification failed. Check its credentials and grants; use --rotate-password to recover a managed login. Shared PUBLIC privileges are never changed."
        ) from None
    finally:
        engine.dispose()


def provision_advisor(admin_url, role, password=None, *, rotate=False):
    """Returns the secret to persist; callers must never log it or rendered DDL."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise AdvisorSetupError(
            "ADVISOR_USER must be a lowercase PostgreSQL identifier, at most 63 characters."
        )
    engine = create_engine(
        admin_url, hide_parameters=True, connect_args={"connect_timeout": 5}
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "abacus-advisor:" + role},
            )
            current = connection.scalar(text("SELECT current_user"))
            if current == role:
                raise AdvisorSetupError(
                    "Advisor and application logins must be different."
                )
            database, oid = connection.execute(
                text(
                    "SELECT datname,oid FROM pg_database WHERE datname=current_database()"
                )
            ).one()
            marker = f"abacus-advisor-v1:database={oid}"
            existing = (
                connection.execute(
                    text(
                        "SELECT oid, shobj_description(oid,'pg_authid') AS marker FROM pg_roles WHERE rolname=:role"
                    ),
                    {"role": role},
                )
                .mappings()
                .one_or_none()
            )
            if existing and existing["marker"] != marker:
                raise AdvisorSetupError(
                    "An unrelated role already uses ADVISOR_USER. Choose another name; no permissions were changed."
                )
            if existing:
                unsafe = connection.scalar(
                    text("""SELECT EXISTS (SELECT 1 FROM pg_auth_members WHERE member=:oid)
                    OR EXISTS (SELECT 1 FROM pg_database WHERE datdba=:oid)
                    OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner=:oid)
                    OR EXISTS (SELECT 1 FROM pg_class WHERE relowner=:oid)
                    OR EXISTS (SELECT 1 FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=:oid AND deptype='o')"""),
                    {"oid": existing["oid"]},
                )
                if unsafe:
                    raise AdvisorSetupError(
                        "Managed advisor has unexpected memberships or ownership. Resolve these explicitly; nothing was changed."
                    )
                if not password and not rotate:
                    raise AdvisorSetupError(
                        "ADVISOR_PASS is missing for the managed role. Run setup with --rotate-password."
                    )
            if not existing or rotate:
                password = secrets.token_urlsafe(32)
            raw = connection.connection.driver_connection
            with raw.cursor() as cursor:
                identifier = sql.Identifier(role)
                if not existing:
                    cursor.execute(
                        sql.SQL(
                            "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"
                        ).format(identifier)
                    )
                    cursor.execute(
                        sql.SQL("COMMENT ON ROLE {} IS {}").format(
                            identifier, sql.Literal(marker)
                        )
                    )
                else:
                    cursor.execute(
                        sql.SQL(
                            "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"
                        ).format(identifier)
                    )
                if not existing or rotate:
                    # Send a SCRAM verifier, never a plaintext password in SQL.
                    verifier = raw.pgconn.encrypt_password(
                        password.encode(), role.encode(), algorithm=b"scram-sha-256"
                    ).decode()
                    cursor.execute(
                        sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                            identifier, sql.Literal(verifier)
                        )
                    )
                cursor.execute(
                    sql.SQL(
                        "ALTER ROLE {} SET default_transaction_read_only = on"
                    ).format(identifier)
                )
                cursor.execute(
                    sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(
                        sql.Identifier(database), identifier
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(database), identifier
                    )
                )
                schemas = (
                    connection.execute(
                        text(
                            "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'"
                        )
                    )
                    .scalars()
                    .all()
                )
                for schema in schemas:
                    cursor.execute(
                        sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}").format(
                            sql.Identifier(schema), identifier
                        )
                    )
                    cursor.execute(
                        sql.SQL(
                            "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {} FROM {}"
                        ).format(sql.Identifier(schema), identifier)
                    )
                    cursor.execute(
                        sql.SQL(
                            "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {} FROM {}"
                        ).format(sql.Identifier(schema), identifier)
                    )
                    # Table-level REVOKE does not revoke independent column grants.
                    columns = connection.execute(
                        text("""SELECT c.relname,a.attname FROM pg_attribute a
                        JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                        WHERE n.nspname=:schema AND a.attnum>0 AND NOT a.attisdropped
                          AND EXISTS (SELECT 1 FROM aclexplode(a.attacl) x WHERE x.grantee=(SELECT oid FROM pg_roles WHERE rolname=:role))"""),
                        {"schema": schema, "role": role},
                    ).all()
                    for table, column in columns:
                        cursor.execute(
                            sql.SQL(
                                "REVOKE SELECT ({}), INSERT ({}), UPDATE ({}), REFERENCES ({}) ON TABLE {}.{} FROM {}"
                            ).format(
                                *([sql.Identifier(column)] * 4),
                                sql.Identifier(schema),
                                sql.Identifier(table),
                                identifier,
                            )
                        )
                cursor.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(identifier)
                )
                for table, columns in ADVISOR_COLUMNS.items():
                    cursor.execute(
                        sql.SQL("GRANT SELECT ({}) ON TABLE public.{} TO {}").format(
                            sql.SQL(", ").join(map(sql.Identifier, columns)),
                            sql.Identifier(table),
                            identifier,
                        )
                    )
                for table in ADVISOR_TABLES:
                    cursor.execute(
                        sql.SQL("GRANT SELECT ON TABLE public.{} TO {}").format(
                            sql.Identifier(table), identifier
                        )
                    )
        url = admin_url.set(username=role, password=password).difference_update_query(
            ["user", "password"]
        )
        check_connection(url)
        return password
    except (SQLAlchemyError, psycopg.Error):
        raise AdvisorSetupError(
            "Advisor provisioning failed. The application login needs role-management and table-grant permissions. No credentials or SQL are logged. Fix the database configuration and retry."
        ) from None
    finally:
        engine.dispose()


def persist_credentials(path, role, password):
    persist_local_values(path, {"ADVISOR_USER": role, "ADVISOR_PASS": password})


def persist_local_values(path, values):
    """Atomic owner-only dotenv replacement, preserving unrelated lines/comments."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise AdvisorSetupError(
            "Use an existing, regular .env file before provisioning."
        )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".env.advisor-",
            dir=path.parent,
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(path.read_text())
        for key, value in values.items():
            set_key(temporary, key, value, quote_mode="always")
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

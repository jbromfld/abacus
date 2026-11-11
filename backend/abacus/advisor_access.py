"""Explicit advisor permissions, independent of transaction read-only settings."""

import json

from sqlalchemy import text

ADVISOR_TABLES = (
    "settings",
    "categories",
    "recurring",
    "amount_changes",
    "bill_payments",
    "annual_income",
    "plans",
    "plan_categories",
    "payee_groups",
    "payee_rules",
    "purchases",
    "transactions",
    "month_status",
    "bill_estimates",
)
ADVISOR_COLUMNS = {"accounts": ("id", "name")}
ROLE_ATTRIBUTES = (
    "rolsuper",
    "rolcreatedb",
    "rolcreaterole",
    "rolreplication",
    "rolbypassrls",
    "rolinherit",
)
ADVISOR_UNAVAILABLE = "Advisor database access is unavailable. Run uv run --no-sync python scripts/setup_advisor.py, then restart Abacus. No writable connection was used for this request."


class AdvisorAccessError(RuntimeError):
    pass


def verify_advisor_access(connection, expected_role):
    """Check effective permissions before reading any financial tables."""
    role = (
        connection.execute(
            text("""
        SELECT r.*, current_user = session_user AS unchanged,
          EXISTS (SELECT 1 FROM pg_auth_members WHERE member = r.oid) AS memberships,
          EXISTS (SELECT 1 FROM pg_database WHERE datdba = r.oid) AS owns_database,
          EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner = r.oid) AS owns_schema,
          EXISTS (SELECT 1 FROM pg_class WHERE relowner = r.oid) AS owns_relation,
          EXISTS (SELECT 1 FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=r.oid AND deptype='o') AS owns_object
        FROM pg_roles r WHERE rolname = current_user
    """)
        )
        .mappings()
        .one()
    )
    if (
        role["rolname"] != expected_role
        or not role["unchanged"]
        or not role["rolcanlogin"]
        or any(role[key] for key in ROLE_ATTRIBUTES)
        or any(
            role[key]
            for key in (
                "memberships",
                "owns_database",
                "owns_schema",
                "owns_relation",
                "owns_object",
            )
        )
    ):
        raise AdvisorAccessError("The advisor role has unsafe attributes or ownership.")
    if connection.scalar(
        text(
            "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
        )
    ):
        raise AdvisorAccessError("The advisor can create schemas in the database.")
    schemas = (
        connection.execute(
            text("""
        SELECT nspname, has_schema_privilege(current_user, oid, 'CREATE') AS can_create
        FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'
    """)
        )
        .mappings()
        .all()
    )
    if any(row["can_create"] for row in schemas):
        raise AdvisorAccessError("The advisor can create objects in a user schema.")
    if not connection.scalar(
        text(
            "SELECT has_database_privilege(current_user, current_database(), 'CONNECT') AND has_schema_privilege(current_user, 'public', 'USAGE')"
        )
    ):
        raise AdvisorAccessError("The advisor lacks database/schema access.")
    relations = (
        connection.execute(
            text("""
        SELECT n.nspname, c.relname, c.relkind,
          EXISTS (SELECT 1 FROM aclexplode(COALESCE(c.relacl, acldefault(
            CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relowner))) a
            WHERE a.grantee IN (0, :role_oid) AND a.privilege_type = 'SELECT') AS can_read,
          EXISTS (SELECT 1 FROM aclexplode(COALESCE(c.relacl, acldefault(
            CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relowner))) a
            WHERE a.grantee IN (0, :role_oid) AND (a.privilege_type <> 'SELECT' OR a.is_grantable)) AS unsafe
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
          AND c.relkind IN ('r','p','v','m','f','S')
    """),
            {"role_oid": role["oid"]},
        )
        .mappings()
        .all()
    )
    allowed = {("public", name) for name in ADVISOR_TABLES}
    readable = {
        (row["nspname"], row["relname"]) for row in relations if row["can_read"]
    }
    if readable != allowed or any(row["unsafe"] for row in relations):
        raise AdvisorAccessError(
            "The advisor effective table privileges do not match its allowlist."
        )
    # Table ACLs do not include column grants or SECURITY DEFINER functions.
    if connection.scalar(
        text("""
        SELECT EXISTS (SELECT 1 FROM pg_attribute a
          JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
          CROSS JOIN LATERAL aclexplode(a.attacl) x
          WHERE x.grantee IN (0,:role_oid) AND n.nspname NOT LIKE 'pg_%'
            AND n.nspname <> 'information_schema'
            AND (x.privilege_type <> 'SELECT' OR x.is_grantable OR n.nspname <> 'public'
                 OR NOT (c.relname = ANY(:tables) OR
                   COALESCE((CAST(:columns AS jsonb)->c.relname) ? a.attname, false))))
    """),
        {
            "role_oid": role["oid"],
            "tables": list(ADVISOR_TABLES),
            "columns": json.dumps(ADVISOR_COLUMNS),
        },
    ):
        raise AdvisorAccessError("Unexpected column privileges for the advisor.")
    for table, columns in ADVISOR_COLUMNS.items():
        for column in columns:
            if not connection.scalar(
                text(
                    "SELECT has_column_privilege(current_user, :table, :column, 'SELECT')"
                ),
                {"table": "public." + table, "column": column},
            ):
                raise AdvisorAccessError(
                    "The advisor lacks required account-label access."
                )
    if connection.scalar(
        text("""
        SELECT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
          WHERE p.prosecdef AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
            AND has_function_privilege(current_user,p.oid,'EXECUTE'))
    """)
    ):
        raise AdvisorAccessError(
            "An executable SECURITY DEFINER function bypasses advisor permissions."
        )

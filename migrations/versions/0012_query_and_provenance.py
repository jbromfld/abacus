"""Compact shared PDF provenance, index transaction lookups, and version import jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "imports", sa.Column("processing_token", sa.String(36), nullable=True)
    )
    op.create_index("ix_transactions_import_id", "transactions", ["import_id"])
    op.create_index(
        "ix_transactions_account_date", "transactions", ["account_id", "date"]
    )
    pages = op.create_table(
        "import_pages",
        sa.Column(
            "import_id",
            sa.String(36),
            sa.ForeignKey("imports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint("number > 0"),
    )
    connection = op.get_bind()
    cache = {}

    def compact(source, import_id):
        if not isinstance(source, dict):
            return source
        number, text = source.get("page"), source.get("original")
        if type(number) is not int or number <= 0 or not isinstance(text, str):
            return source
        key = (import_id, number)
        if key in cache and cache[key] != text:
            return source  # Preserve exceptional conflicting source snapshots.
        if key not in cache:
            cache[key] = text
            connection.execute(
                pages.insert().values(import_id=import_id, number=number, text=text)
            )
        return {key: value for key, value in source.items() if key != "original"}

    imports = sa.table(
        "imports",
        sa.column("id"),
        sa.column("source", sa.JSON),
        sa.column("rows", sa.JSON),
    )
    for row in connection.execute(
        sa.select(imports.c.id, imports.c.rows).where(
            imports.c.source["type"].as_string() == "pdf"
        )
    ):
        rows = [
            {**item, "source": compact(item.get("source", {}), row.id)}
            for item in row.rows
        ]
        connection.execute(
            imports.update().where(imports.c.id == row.id).values(rows=rows)
        )
    transactions = sa.table(
        "transactions",
        sa.column("id"),
        sa.column("import_id"),
        sa.column("provenance", sa.JSON),
    )
    for row in connection.execute(
        sa.select(transactions).where(transactions.c.import_id.is_not(None))
    ):
        value = dict(row.provenance)
        source = value.get("source", {})
        review = dict(value.get("original_review", {}))
        if review.get("source") == source:
            review.pop("source", None)
        elif "source" in review:
            review["source"] = compact(review["source"], row.import_id)
        value.update(source=compact(source, row.import_id), original_review=review)
        connection.execute(
            transactions.update()
            .where(transactions.c.id == row.id)
            .values(provenance=value)
        )


def downgrade():
    connection = op.get_bind()
    texts = {
        (row.import_id, row.number): row.text
        for row in connection.execute(
            sa.text("SELECT import_id,number,text FROM import_pages")
        )
    }

    def expand(source, import_id):
        if (
            isinstance(source, dict)
            and "original" not in source
            and (import_id, source.get("page")) in texts
        ):
            return {**source, "original": texts[(import_id, source["page"])]}
        return source

    imports = sa.table("imports", sa.column("id"), sa.column("rows", sa.JSON))
    for row in connection.execute(sa.select(imports)):
        rows = [
            {**item, "source": expand(item.get("source", {}), row.id)}
            for item in row.rows
        ]
        connection.execute(
            imports.update().where(imports.c.id == row.id).values(rows=rows)
        )
    transactions = sa.table(
        "transactions",
        sa.column("id"),
        sa.column("import_id"),
        sa.column("provenance", sa.JSON),
    )
    for row in connection.execute(
        sa.select(transactions).where(transactions.c.import_id.is_not(None))
    ):
        value = dict(row.provenance)
        source = expand(value.get("source", {}), row.import_id)
        review = dict(value.get("original_review", {}))
        review["source"] = expand(review.get("source", source), row.import_id)
        value.update(source=source, original_review=review)
        connection.execute(
            transactions.update()
            .where(transactions.c.id == row.id)
            .values(provenance=value)
        )
    op.drop_table("import_pages")
    op.drop_index("ix_transactions_account_date", table_name="transactions")
    op.drop_index("ix_transactions_import_id", table_name="transactions")
    op.drop_column("imports", "processing_token")

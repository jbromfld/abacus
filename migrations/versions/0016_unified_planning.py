"""One Planning page. Discard obsolete plans; preserve financial records."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    # Explicitly authorized reset of old planning data. Do not touch transactions,
    # imports, recurring bills, amount history, accounts, income or savings.
    for table in ("reserve_plans", "bill_estimates", "purchases"):
        op.execute(sa.text(f"DELETE FROM {table}"))
    op.create_table(
        "plan_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
    )
    op.bulk_insert(
        sa.table("plan_categories", sa.column("id"), sa.column("name")),
        [
            {"id": "tax", "name": "tax"},
            {"id": "vacation", "name": "vacation"},
            {"id": "purchase", "name": "purchase"},
        ],
    )
    op.create_table(
        "plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column(
            "category_id",
            sa.String(36),
            sa.ForeignKey("plan_categories.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "recurring_id",
            sa.String(36),
            sa.ForeignKey("recurring.id", ondelete="SET NULL"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0 AND amount <= 9000000000000"),
    )
    op.create_index("ix_plans_target_date", "plans", ["target_date"])


def downgrade():
    op.drop_index("ix_plans_target_date", table_name="plans")
    op.drop_table("plans")
    op.drop_table("plan_categories")

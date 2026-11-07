"""User-entered savings snapshots and draft monthly bill estimates."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "settings", sa.Column("savings_balance", sa.BigInteger(), nullable=True)
    )
    op.add_column("settings", sa.Column("savings_month", sa.String(7), nullable=True))
    op.add_column(
        "settings",
        sa.Column("savings_floor", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "bill_estimates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("start_month", sa.String(7), nullable=False),
        sa.Column("end_month", sa.String(7), nullable=True),
        sa.Column(
            "category_id", sa.String(36), sa.ForeignKey("categories.id"), nullable=False
        ),
        sa.Column("due_day", sa.Integer(), nullable=True),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "recurring_id",
            sa.String(36),
            sa.ForeignKey("recurring.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("amount > 0"),
        sa.CheckConstraint("due_day BETWEEN 1 AND 31", name="estimate_due_day_range"),
    )


def downgrade():
    op.drop_table("bill_estimates")
    for column in ("savings_floor", "savings_month", "savings_balance"):
        op.drop_column("settings", column)

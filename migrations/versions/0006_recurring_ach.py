"""Opt-in monthly ACH actuals and persistent occurrence identity."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "recurring",
        sa.Column(
            "ach_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column("recurring", sa.Column("ach_day", sa.Integer(), nullable=True))
    op.add_column(
        "recurring", sa.Column("ach_start_month", sa.String(7), nullable=True)
    )
    op.add_column(
        "recurring",
        sa.Column(
            "ach_account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=True
        ),
    )
    op.create_table(
        "recurring_debits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recurring_id",
            sa.String(36),
            sa.ForeignKey("recurring.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column(
            "transaction_id",
            sa.String(36),
            sa.ForeignKey("transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("recurring_id", "month"),
    )


def downgrade():
    op.drop_table("recurring_debits")
    for column in ("ach_account_id", "ach_start_month", "ach_day", "ach_enabled"):
        op.drop_column("recurring", column)

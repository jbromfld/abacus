"""Remove obsolete planning features. Downgrade restores empty tables only.

Deleted records cannot be recovered by downgrade; restore a backup if needed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    for table in (
        "purchases",
        "bill_estimates",
        "reserve_plans",
        "savings_observations",
    ):
        op.drop_table(table)
    op.drop_constraint("reserve_checkpoint_day_range", "settings", type_="check")
    op.drop_column("settings", "reserve_checkpoint_day")
    op.drop_column("settings", "reserve_alerts_enabled")


def downgrade():
    op.create_table(
        "purchases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column(
            "category_id", sa.String(36), sa.ForeignKey("categories.id"), nullable=False
        ),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("included", sa.Boolean, nullable=False),
        sa.CheckConstraint("amount > 0"),
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
    op.add_column(
        "settings",
        sa.Column(
            "reserve_alerts_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "settings",
        sa.Column(
            "reserve_checkpoint_day", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.create_check_constraint(
        "reserve_checkpoint_day_range",
        "settings",
        "reserve_checkpoint_day BETWEEN 1 AND 31",
    )
    op.create_table(
        "reserve_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("schedules", sa.JSON(), nullable=False),
        sa.Column("dismissed_until", sa.Date()),
        sa.CheckConstraint("amount >= 0"),
    )
    op.create_table(
        "savings_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("as_of", sa.Date(), nullable=False, unique=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("amount >= 0"),
    )

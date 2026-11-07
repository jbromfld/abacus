"""Manual savings observations and independent annual reserve funding targets."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
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
    # A saved opening balance is already an explicit manual observation.
    op.execute("""INSERT INTO savings_observations (id,as_of,amount)
        SELECT 'initial-savings', (savings_month || '-01')::date, savings_balance
        FROM settings WHERE savings_balance IS NOT NULL AND savings_month IS NOT NULL
        AND (savings_month || '-01')::date <= CURRENT_DATE""")


def downgrade():
    op.drop_table("savings_observations")
    op.drop_table("reserve_plans")
    op.drop_constraint("reserve_checkpoint_day_range", "settings", type_="check")
    op.drop_column("settings", "reserve_checkpoint_day")
    op.drop_column("settings", "reserve_alerts_enabled")

"""Persist reviewed forecast and actual-spending alerts by month and kind."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert_dismissals",
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("kind", sa.String(24), primary_key=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('forecast_deficit','actual_deficit')", name="alert_dismissal_kind"
        ),
    )


def downgrade():
    op.drop_table("alert_dismissals")

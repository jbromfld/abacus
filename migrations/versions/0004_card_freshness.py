"""Opt-in UI alerts for card information older than one cycle."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "accounts",
        sa.Column(
            "stale_alert_enabled", sa.Boolean, nullable=False, server_default=sa.false()
        ),
    )


def downgrade():
    op.drop_column("accounts", "stale_alert_enabled")

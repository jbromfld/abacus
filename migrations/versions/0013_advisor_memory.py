"""Optional advisor memory; financial advisor privileges remain unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "settings",
        sa.Column(
            "advisor_memory_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade():
    op.drop_column("settings", "advisor_memory_enabled")

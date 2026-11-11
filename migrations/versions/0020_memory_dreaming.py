"""Optional, persistent memory consolidation jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "settings",
        sa.Column(
            "advisor_dreaming_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "memory_dreams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("memory_dreams")
    op.drop_column("settings", "advisor_dreaming_enabled")

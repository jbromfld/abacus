"""User-approved merchant groups. Existing payee labels and expenses are retained."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payee_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.CheckConstraint("kind IN ('purchase','refund','fee')"),
    )
    op.add_column(
        "payee_rules",
        sa.Column(
            "group_id",
            sa.String(36),
            sa.ForeignKey("payee_groups.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_payee_rules_group_id", "payee_rules", ["group_id"])
    op.create_table(
        "payee_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("suggestions", sa.JSON(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(500), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("payee_reviews")
    op.drop_index("ix_payee_rules_group_id", table_name="payee_rules")
    op.drop_column("payee_rules", "group_id")
    op.drop_table("payee_groups")

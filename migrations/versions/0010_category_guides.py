"""Informational category planning guides, excluded from forecast expenses."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "categories", sa.Column("monthly_guide", sa.BigInteger(), nullable=True)
    )


def downgrade():
    op.drop_column("categories", "monthly_guide")

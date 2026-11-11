"""Optional annual income estimates, separate from recurring deposits."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "annual_income",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False, server_default="false"),
        sa.CheckConstraint("year BETWEEN 1900 AND 9998"),
        sa.CheckConstraint("amount > 0 AND amount <= 9000000000000"),
    )
    op.create_index("ix_annual_income_year", "annual_income", ["year"])


def downgrade():
    op.drop_index("ix_annual_income_year", table_name="annual_income")
    op.drop_table("annual_income")

"""Allow annual payables to be distributed or counted fully in their due month."""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('recurring', sa.Column('distribute_annual', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column('recurring', 'distribute_annual')

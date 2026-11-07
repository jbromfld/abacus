"""Optional local budget advisor, disabled by default."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('settings', sa.Column('advisor_enabled', sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('settings', 'advisor_enabled')

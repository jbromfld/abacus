"""Optional contractual due dates and separate payment confirmations."""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('recurring', sa.Column('due_day', sa.Integer(), nullable=True))
    op.add_column('recurring', sa.Column('due_month', sa.Integer(), nullable=True))
    op.add_column('recurring', sa.Column('payment_tracking_start', sa.Date(), nullable=True))
    op.create_check_constraint('recurring_due_day_range', 'recurring', 'due_day BETWEEN 1 AND 31')
    op.create_check_constraint('recurring_due_month_range', 'recurring', 'due_month BETWEEN 1 AND 12')
    op.create_table('bill_payments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('recurring_id', sa.String(36), sa.ForeignKey('recurring.id', ondelete='CASCADE'), nullable=False),
        sa.Column('period', sa.String(7), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('paid_on', sa.Date(), nullable=True),
        sa.UniqueConstraint('recurring_id', 'period'), sa.CheckConstraint('amount > 0'))


def downgrade():
    op.drop_table('bill_payments')
    op.drop_constraint('recurring_due_month_range', 'recurring', type_='check')
    op.drop_constraint('recurring_due_day_range', 'recurring', type_='check')
    for column in ('payment_tracking_start', 'due_month', 'due_day'):
        op.drop_column('recurring', column)

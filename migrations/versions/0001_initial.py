"""Initial budget schema and starter categories."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('categories', sa.Column('id', sa.String(36), primary_key=True), sa.Column('name', sa.String(80), nullable=False, unique=True))
    op.create_table('settings', sa.Column('id', sa.Integer, primary_key=True), sa.Column('currency', sa.String(3), nullable=False), sa.Column('model', sa.String(200), nullable=False))
    op.create_table('accounts', sa.Column('id', sa.String(36), primary_key=True), sa.Column('name', sa.String(120), nullable=False, unique=True))
    op.create_table('recurring', sa.Column('id', sa.String(36), primary_key=True), sa.Column('name', sa.String(160), nullable=False), sa.Column('kind', sa.String(12), nullable=False), sa.Column('frequency', sa.String(10), nullable=False), sa.Column('category_id', sa.String(36), sa.ForeignKey('categories.id')), sa.Column('start_month', sa.String(7), nullable=False), sa.Column('end_month', sa.String(7)), sa.CheckConstraint("kind IN ('payable','receivable')"), sa.CheckConstraint("frequency IN ('monthly','annual')"), sa.CheckConstraint("kind != 'payable' OR category_id IS NOT NULL"))
    op.create_table('amount_changes', sa.Column('id', sa.String(36), primary_key=True), sa.Column('recurring_id', sa.String(36), sa.ForeignKey('recurring.id', ondelete='CASCADE'), nullable=False), sa.Column('month', sa.String(7), nullable=False), sa.Column('amount', sa.BigInteger, nullable=False), sa.Column('override', sa.Boolean, nullable=False), sa.UniqueConstraint('recurring_id', 'month', 'override'), sa.CheckConstraint('amount > 0'))
    op.create_table('purchases', sa.Column('id', sa.String(36), primary_key=True), sa.Column('name', sa.String(160), nullable=False), sa.Column('amount', sa.BigInteger, nullable=False), sa.Column('month', sa.String(7), nullable=False), sa.Column('category_id', sa.String(36), sa.ForeignKey('categories.id'), nullable=False), sa.Column('notes', sa.String(2000), nullable=False), sa.Column('included', sa.Boolean, nullable=False), sa.CheckConstraint('amount > 0'))
    op.create_table('imports', sa.Column('id', sa.String(36), primary_key=True), sa.Column('account_id', sa.String(36), sa.ForeignKey('accounts.id'), nullable=False), sa.Column('period', sa.String(7), nullable=False), sa.Column('file_hash', sa.String(64), nullable=False), sa.Column('filename', sa.String(200), nullable=False), sa.Column('status', sa.String(20), nullable=False), sa.Column('error', sa.String(2000), nullable=False), sa.Column('source', sa.JSON, nullable=False), sa.Column('rows', sa.JSON, nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint('account_id', 'file_hash'))
    op.create_table('transactions', sa.Column('id', sa.String(36), primary_key=True), sa.Column('date', sa.Date, nullable=False), sa.Column('description', sa.String(500), nullable=False), sa.Column('amount', sa.BigInteger, nullable=False), sa.Column('kind', sa.String(16), nullable=False), sa.Column('category_id', sa.String(36), sa.ForeignKey('categories.id')), sa.Column('account_id', sa.String(36), sa.ForeignKey('accounts.id'), nullable=False), sa.Column('import_id', sa.String(36), sa.ForeignKey('imports.id')), sa.Column('provenance', sa.JSON, nullable=False), sa.CheckConstraint('amount > 0'), sa.CheckConstraint("kind IN ('purchase','refund','fee','payment','transfer')"), sa.CheckConstraint("kind IN ('payment','transfer') OR category_id IS NOT NULL"))
    op.create_index('ix_transactions_date', 'transactions', ['date'])
    op.create_table('month_status', sa.Column('month', sa.String(7), primary_key=True), sa.Column('complete', sa.Boolean, nullable=False))
    from uuid import uuid4
    categories = sa.table('categories', sa.column('id'), sa.column('name'))
    op.bulk_insert(categories, [dict(id=str(uuid4()), name=name) for name in ['Groceries','Entertainment','Housing','Utilities','Transport','Health','Other']])
    op.bulk_insert(sa.table('settings', sa.column('id'), sa.column('currency'), sa.column('model')), [dict(id=1,currency='USD',model='')])


def downgrade():
    for table in ['month_status', 'transactions', 'imports', 'purchases', 'amount_changes', 'recurring', 'accounts', 'settings', 'categories']:
        op.drop_table(table)

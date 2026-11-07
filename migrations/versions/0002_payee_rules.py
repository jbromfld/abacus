"""Remember reviewed payee categories and seed unambiguous existing labels."""
import re
import unicodedata
from collections import defaultdict
from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table('payee_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('payee', sa.String(500), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('category_id', sa.String(36), sa.ForeignKey('categories.id', ondelete='CASCADE'), nullable=False),
        sa.UniqueConstraint('payee', 'kind'),
        sa.CheckConstraint("kind IN ('purchase','refund','fee')"))
    labels = defaultdict(set)
    for row in op.get_bind().execute(sa.text("SELECT description, kind, category_id FROM transactions WHERE category_id IS NOT NULL AND kind IN ('purchase','refund','fee')")):
        payee = re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', row.description).casefold()).strip()
        if payee:
            labels[(payee, row.kind)].add(row.category_id)
    records = [dict(id=str(uuid4()), payee=payee, kind=kind, category_id=next(iter(categories))) for (payee, kind), categories in labels.items() if len(categories) == 1]
    if records:
        op.bulk_insert(table, records)


def downgrade():
    op.drop_table('payee_rules')

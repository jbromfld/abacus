"""Remember CSV column and date-format settings per card."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('accounts', sa.Column('csv_mapping', sa.JSON, nullable=True))
    # Older uncommitted reviews retain their mappings. Prefer the newest valid
    # available layout; older committed imports may have discarded this metadata.
    connection = op.get_bind()
    seen = set()
    formats = {'%Y-%m-%d','%m/%d/%Y','%d/%m/%Y','%m/%d/%y','%m/%d'}
    for account_id, source in connection.execute(sa.text('SELECT account_id, source FROM imports ORDER BY created_at DESC, id DESC')):
        mapping = source.get('mapping') if source.get('type') == 'csv' else None
        if account_id in seen or not isinstance(mapping, dict):
            continue
        if not all(isinstance(mapping.get(k), str) and mapping[k] for k in ('date_column','description_column','amount_column')):
            continue
        if mapping.get('date_format') not in formats or mapping.get('positive_is') not in (None,'purchase','refund'):
            continue
        fields = {k:mapping.get(k) for k in ('date_column','description_column','amount_column','date_format','positive_is')}
        statement = sa.text('UPDATE accounts SET csv_mapping = :mapping WHERE id = :id').bindparams(sa.bindparam('mapping', type_=sa.JSON))
        connection.execute(statement, {'mapping':fields,'id':account_id})
        seen.add(account_id)


def downgrade():
    op.drop_column('accounts', 'csv_mapping')

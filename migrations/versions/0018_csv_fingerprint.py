"""Index exact CSV identity without loading account-wide provenance."""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "transactions", sa.Column("csv_fingerprint", sa.String(64), nullable=True)
    )
    connection = op.get_bind()
    last = ""
    while True:
        rows = connection.execute(
            sa.text(
                "SELECT id, provenance FROM transactions WHERE id > :last ORDER BY id LIMIT 500"
            ),
            {"last": last},
        ).all()
        if not rows:
            break
        for id, provenance in rows:
            original = (provenance or {}).get("source", {}).get("original")
            if (
                isinstance(original, dict)
                and original
                and all(
                    isinstance(k, str) and isinstance(v, str)
                    for k, v in original.items()
                )
            ):
                key = json.dumps(
                    original, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                )
                connection.execute(
                    sa.text(
                        "UPDATE transactions SET csv_fingerprint = :value WHERE id = :id"
                    ),
                    {
                        "id": id,
                        "value": hashlib.sha256(key.encode("utf-8")).hexdigest(),
                    },
                )
        last = rows[-1].id
    op.create_index(
        "ix_transactions_account_csv", "transactions", ["account_id", "csv_fingerprint"]
    )


def downgrade():
    op.drop_index("ix_transactions_account_csv", table_name="transactions")
    op.drop_column("transactions", "csv_fingerprint")

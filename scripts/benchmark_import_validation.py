"""Compare duplicate matching on synthetic data in a disposable test database."""

import json
import os
import time
from datetime import date

url = os.environ.get("TEST_DATABASE_URL")
if not url:
    raise SystemExit("Set TEST_DATABASE_URL to a disposable abacus_test database.")
os.environ["DATABASE_URL"] = url


def main():
    from abacus.db import Session, engine
    from abacus.imports import validate_rows
    from abacus.models import Account, Category, Transaction
    from sqlalchemy import event, select

    if not engine.url.database or not engine.url.database.startswith("abacus_test"):
        raise SystemExit(
            "Refusing a database whose name does not start with abacus_test."
        )
    with Session() as db:
        account = Account(name="Synthetic benchmark")
        db.add(account)
        db.flush()
        category = db.scalar(select(Category.id).limit(1))
        rows = [
            dict(
                date="2026-01-01",
                description=f"Benchmark {i}",
                amount=i + 1,
                kind="purchase",
                category_id=category,
            )
            for i in range(5000)
        ]
        db.add_all(
            [
                Transaction(
                    date=date(2026, 1, 1),
                    description=r["description"],
                    amount=r["amount"],
                    kind="purchase",
                    category_id=category,
                    account_id=account.id,
                )
                for r in rows
            ]
        )
        db.flush()
        count = 0

        def counted(*args):
            nonlocal count
            count += 1

        event.listen(engine, "before_cursor_execute", counted)
        try:
            start = time.perf_counter()
            for row in rows:
                assert db.scalar(
                    select(Transaction.id)
                    .where(
                        Transaction.account_id == account.id,
                        Transaction.date == date(2026, 1, 1),
                        Transaction.description.ilike(row["description"]),
                        Transaction.amount == row["amount"],
                        Transaction.kind == "purchase",
                    )
                    .limit(1)
                )
            before = dict(
                queries=count,
                milliseconds=round((time.perf_counter() - start) * 1000, 2),
            )
            count = 0
            start = time.perf_counter()
            result = validate_rows(db, rows, account.id)
            assert all(r["duplicate"] for r in result)
            after = dict(
                queries=count,
                milliseconds=round((time.perf_counter() - start) * 1000, 2),
            )
            print(json.dumps(dict(rows=len(rows), before=before, after=after)))
        finally:
            event.remove(engine, "before_cursor_execute", counted)
            db.rollback()


if __name__ == "__main__":
    main()

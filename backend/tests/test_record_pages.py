from datetime import date

from abacus.models import Transaction


def test_transaction_cursor_ties_filters_and_bounds(
    client, db, account_id, category_id
):
    db.add_all(
        [
            Transaction(
                id=f"{i:036}",
                date=date(2026, 1, 1),
                description="Literal %_ match",
                amount=100,
                kind="purchase",
                account_id=account_id,
                category_id=category_id,
            )
            for i in range(205)
        ]
    )
    db.commit()
    seen = []
    params = {"month": "2026-01", "q": "%_", "category_id": category_id}
    while True:
        response = client.get("/api/transactions", params=params)
        assert response.status_code == 200
        page = response.json()
        assert len(page["items"]) <= 100
        seen.extend(row["id"] for row in page["items"])
        if not page["next_cursor"]:
            break
        params["cursor"] = page["next_cursor"]
    assert seen == sorted(set(seen)) and len(seen) == 205
    assert client.get("/api/transactions?limit=201").status_code == 422
    assert client.get("/api/transactions?cursor=bad").status_code == 422
    assert client.get("/api/imports?cursor=bad").status_code == 422


def test_import_pages_keep_equal_timestamp_order(client, db, account_id):
    from datetime import UTC, datetime

    from abacus.models import StatementImport

    db.add_all(
        [
            StatementImport(
                id=f"{i:036}",
                account_id=account_id,
                filename="test.csv",
                file_hash=f"{i:064}",
                period="2026-01",
                source={},
                rows=[],
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
            for i in range(205)
        ]
    )
    db.commit()
    seen = []
    params = {"limit": 200}
    while True:
        page = client.get("/api/imports", params=params).json()
        seen.extend(item["id"] for item in page["items"])
        if not page["next_cursor"]:
            break
        params["cursor"] = page["next_cursor"]
    assert seen == sorted(set(seen)) and len(seen) == 205

from contextlib import contextmanager
from datetime import date

import pytest
from abacus.db import read_only_session
from abacus.models import Transaction
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def test_dismissals_are_permanent_idempotent_and_separate_by_month_and_type(
    client, db, account_id, category_id
):
    client.post(
        "/api/recurring",
        json={
            "name": "Income",
            "kind": "receivable",
            "frequency": "monthly",
            "amount": 100000,
            "start_month": "2026-09",
        },
    )
    db.add(
        Transaction(
            account_id=account_id,
            category_id=category_id,
            date=date(2026, 9, 1),
            amount=172320,
            kind="purchase",
            description="Synthetic reviewed spending",
        )
    )
    db.commit()
    before = client.get("/api/forecast?month=2026-09").json()
    assert before["actual_deficit"]
    body = {"month": "2026-09", "kind": "actual_deficit"}
    first = client.post("/api/alerts/dismissals", json=body)
    assert first.status_code == 200
    assert client.post("/api/alerts/dismissals", json=body).json() == first.json()
    rows = client.get("/api/alerts/dismissals").json()
    assert (
        len(rows) == 1
        and rows[0]["month"] == "2026-09"
        and rows[0]["kind"] == "actual_deficit"
    )
    client.post(
        "/api/alerts/dismissals", json={"month": "2026-10", "kind": "actual_deficit"}
    )
    client.post(
        "/api/alerts/dismissals", json={"month": "2026-09", "kind": "forecast_deficit"}
    )
    assert len(client.get("/api/alerts/dismissals").json()) == 3
    assert client.get("/api/forecast?month=2026-09").json() == before
    # Later changes never resurrect the permanently reviewed alert.
    db.add(
        Transaction(
            account_id=account_id,
            category_id=category_id,
            date=date(2026, 9, 2),
            amount=10000,
            kind="purchase",
            description="Later spending",
        )
    )
    db.commit()
    assert len(client.get("/api/alerts/dismissals").json()) == 3
    assert client.delete("/api/alerts/dismissals").json() == {"restored": 3}
    assert client.get("/api/alerts/dismissals").json() == []
    assert client.delete("/api/alerts/dismissals").json() == {"restored": 0}
    assert len(client.get("/api/transactions?month=2026-09").json()) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"month": "2026-13", "kind": "actual_deficit"},
        {"month": "2026-09", "kind": "everything"},
        {"month": "1899-09", "kind": "forecast_deficit"},
    ],
)
def test_invalid_dismissals_are_rejected(client, body):
    assert client.post("/api/alerts/dismissals", json=body).status_code == 422
    assert client.get("/api/alerts/dismissals").json() == []


def test_advisor_has_no_access_to_dismissal_records():
    with contextmanager(read_only_session)() as reader:
        with pytest.raises(DBAPIError) as error:
            reader.execute(text("SELECT * FROM alert_dismissals"))
        assert error.value.orig.sqlstate == "42501"

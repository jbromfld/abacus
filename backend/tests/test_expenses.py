from datetime import date

import pytest
from abacus.models import Category
from sqlalchemy import select


def add(client, account, category, day, amount, kind="purchase", name="Expense"):
    response = client.post(
        "/api/transactions",
        json=dict(
            date=day,
            description=name,
            amount=amount,
            kind=kind,
            category_id=category,
            account_id=account,
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()


def breakdown(client, start, end, basis="actual"):
    response = client.get(
        "/api/expenses/breakdown", params={"start": start, "end": end, "basis": basis}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_actual_inclusive_range_categories_refunds_and_payment_exclusion(
    client, account_id, category_id, db
):
    other = db.scalar(select(Category.id).where(Category.id != category_id))
    add(client, account_id, category_id, "2025-01-31", 9999, name="Outside before")
    first = add(client, account_id, category_id, "2025-02-01", 10000, name="Groceries")
    add(
        client,
        account_id,
        category_id,
        "2025-02-15",
        2000,
        kind="refund",
        name="Grocery refund",
    )
    last = add(client, account_id, other, "2025-02-28", 5000, name="Movie")
    add(client, account_id, other, "2025-02-28", 100, kind="fee", name="Fee")
    add(
        client,
        account_id,
        None,
        "2025-02-10",
        100000,
        kind="payment",
        name="Card payment",
    )
    add(
        client, account_id, None, "2025-02-20", 100000, kind="transfer", name="Transfer"
    )
    add(client, account_id, category_id, "2025-03-01", 8888, name="Outside after")
    result = breakdown(client, "2025-02-01", "2025-02-28")
    assert (
        result["charges"] == 15100
        and result["refunds"] == 2000
        and result["net"] == 13100
    )
    assert result["entry_count"] == 4 and len(result["entries"]) == 4
    assert result["entries"][0]["date"] == "2025-02-28"
    assert {e["record_id"] for e in result["entries"]} >= {first["id"], last["id"]}
    assert all(e["account_name"] == "Test card" for e in result["entries"])
    assert sum(c["net"] for c in result["categories"]) == result["net"]
    assert sum(e["signed_amount"] for e in result["entries"]) == result["net"]
    groceries = next(c for c in result["categories"] if c["category_id"] == category_id)
    assert (
        groceries["charges"] == 10000
        and groceries["refunds"] == 2000
        and groceries["net"] == 8000
    )
    assert result["months"] == [
        {"month": "2025-02", "status": "partial", "partial_range": False}
    ]
    assert (
        result["net"]
        == client.get("/api/forecast?month=2025-02").json()["actual"]["expenses"]
    )


def test_single_day_leap_day_and_net_credit_category(client, account_id, category_id):
    add(client, account_id, category_id, "2024-02-28", 500, name="Not selected")
    add(
        client,
        account_id,
        category_id,
        "2024-02-29",
        200,
        kind="refund",
        name="Credit only",
    )
    result = breakdown(client, "2024-02-29", "2024-02-29")
    assert result["entry_count"] == 1 and result["net"] == -200
    assert result["charges"] == 0 and result["refunds"] == 200
    assert result["categories"][0]["net"] == -200
    assert result["months"][0]["partial_range"] is True


def test_zero_net_category_stays_in_complete_breakdown(client, account_id, category_id):
    add(client, account_id, category_id, "2025-02-01", 500)
    add(client, account_id, category_id, "2025-02-02", 500, kind="refund")
    result = breakdown(client, "2025-02-01", "2025-02-28")
    assert result["net"] == 0 and result["entry_count"] == 2
    assert len(result["categories"]) == 1 and result["categories"][0]["net"] == 0


def test_missing_complete_and_current_month_status(client):
    result = breakdown(client, "2025-01-01", "2025-03-31")
    assert result["entries"] == [] and result["categories"] == [] and result["net"] == 0
    assert all(m["status"] == "missing" for m in result["months"])
    client.put("/api/months/2025-02", json={"complete": True})
    result = breakdown(client, "2025-01-01", "2025-03-31")
    assert [m["status"] for m in result["months"]] == ["missing", "complete", "missing"]
    current = date.today().strftime("%Y-%m")
    client.put("/api/months/" + current, json={"complete": True})
    result = breakdown(client, current + "-01", current + "-01")
    assert result["months"][0]["status"] == "partial"


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2025-02-20", "end": "2025-02-01"},
        {"start": "bad", "end": "2025-02-28"},
        {"start": "2025-02-01", "end": "2025-02-29"},
        {"start": "2025-02-01", "end": "2025-02-28", "basis": "unknown"},
        {"start": "1899-12-01", "end": "1900-01-01"},
        {"start": "2025-02-02", "end": "2025-02-28", "basis": "forecast"},
        {"start": "2025-02-01", "end": "2025-02-20", "basis": "forecast"},
    ],
)
def test_breakdown_invalid_range_returns_validation_error(client, params):
    assert client.get("/api/expenses/breakdown", params=params).status_code == 422

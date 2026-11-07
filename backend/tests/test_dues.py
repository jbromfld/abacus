from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime

import pytest
from abacus.models import BillPayment, Transaction
from sqlalchemy import func, select


@pytest.fixture
def clock(monkeypatch):
    value = [date(2026, 11, 7)]
    for module in (
        "abacus.dues.local_today",
        "abacus.main.local_today",
        "abacus.ach.today_local",
    ):
        monkeypatch.setattr(module, lambda: value[0])
    return value


def bill(client, category_id, **changes):
    values = dict(
        name="Monthly bill",
        kind="payable",
        frequency="monthly",
        amount=12000,
        category_id=category_id,
        start_month="2025-01",
        due_day=7,
    )
    values.update(changes)
    result = client.post("/api/recurring", json=values)
    assert result.status_code == 201, result.text
    return result.json()


def dues(client):
    response = client.get("/api/recurring/dues")
    assert response.status_code == 200, response.text
    return response.json()


def mark(client, item, period, paid=True, **changes):
    return client.put(
        f"/api/recurring/{item['id']}/payments/{period}", json={"paid": paid, **changes}
    )


def test_inclusive_window_cross_month_sort_and_missing_dates(
    client, category_id, clock, db
):
    bill(client, category_id, name="Boundary", due_day=7)
    bill(client, category_id, name="Tomorrow", due_day=8)
    bill(client, category_id, name="Undated", due_day=None)
    bill(client, category_id, name="Income", kind="receivable", due_day=None)
    data = dues(client)
    assert data["today"] == "2026-11-07" and data["through"] == "2026-12-07"
    assert [(r["name"], r["due_date"]) for r in data["monthly_upcoming"]] == [
        ("Boundary", "2026-11-07"),
        ("Tomorrow", "2026-11-08"),
        ("Boundary", "2026-12-07"),
    ]
    assert data["monthly_upcoming"][0]["status"] == "today"
    assert data["monthly_overdue"] == []
    assert db.scalar(select(func.count()).select_from(BillPayment)) == 0


def test_tracking_defaults_today_and_preserves_start_on_edit(
    client, category_id, clock
):
    item = bill(client, category_id, due_day=1)
    assert item["payment_tracking_start"] == "2026-11-07"
    assert dues(client)["monthly_overdue"] == []
    clock[0] = date(2026, 12, 2)
    assert dues(client)["monthly_overdue"][0]["due_date"] == "2026-12-01"
    response = client.put(
        "/api/recurring/" + item["id"],
        json={**item, "due_day": 2, "payment_tracking_start": None},
    )
    assert response.status_code == 200, response.text
    assert response.json()["payment_tracking_start"] == "2026-11-07"


def test_explicit_lookback_end_and_future_boundaries(client, category_id, clock):
    bill(
        client,
        category_id,
        name="Ended",
        start_month="2026-10",
        end_month="2026-10",
        due_day=20,
        payment_tracking_start="2026-10-01",
    )
    bill(client, category_id, name="Future", start_month="2026-12", due_day=5)
    bill(client, category_id, name="Beyond window", start_month="2026-12", due_day=8)
    data = dues(client)
    assert [(r["name"], r["due_date"]) for r in data["monthly_overdue"]] == [
        ("Ended", "2026-10-20")
    ]
    assert [(r["name"], r["due_date"]) for r in data["monthly_upcoming"]] == [
        ("Future", "2026-12-05")
    ]


@pytest.mark.parametrize(
    "today,expected",
    [
        ("2024-02-01", "2024-02-29"),
        ("2025-02-01", "2025-02-28"),
        ("2026-04-01", "2026-04-30"),
        ("2026-12-20", "2026-12-31"),
    ],
)
def test_month_end_clamps_and_year_boundary(
    client, category_id, clock, today, expected
):
    clock[0] = date.fromisoformat(today)
    bill(client, category_id, start_month="2024-01", due_day=31)
    assert dues(client)["monthly_upcoming"][0]["due_date"] == expected


def test_annual_full_amounts_separate_from_monthly_and_far_future(
    client, category_id, clock
):
    bill(
        client,
        category_id,
        name="Taxes",
        frequency="annual",
        due_month=11,
        due_day=7,
        distribute_annual=True,
        amount=120000,
    )
    bill(
        client,
        category_id,
        name="Subscription",
        frequency="annual",
        due_month=5,
        due_day=20,
        distribute_annual=False,
        amount=24000,
    )
    bill(client, category_id, name="No annual date", frequency="annual", due_day=None)
    bill(
        client,
        category_id,
        name="Expired annual",
        frequency="annual",
        due_day=7,
        end_month="2026-10",
    )
    data = dues(client)
    assert data["monthly_upcoming"] == []
    by_name = {a["name"]: a for a in data["annual"]}
    assert set(by_name) == {"Taxes", "Subscription", "No annual date"}
    assert by_name["Taxes"]["next"]["amount"] == 120000
    assert by_name["Taxes"]["next"]["due_date"] == "2026-11-07"
    assert by_name["Subscription"]["next"]["due_date"] == "2027-05-20"
    assert by_name["Subscription"]["next"]["amount"] == 24000
    assert by_name["No annual date"]["allowance"]
    assert by_name["No annual date"]["annual_amount"] == 12000
    assert by_name["No annual date"]["monthly_allocation"] == 1000
    assert by_name["No annual date"]["next"] is None
    assert client.get("/api/forecast?month=2026-11").json()["expenses"] == 11000
    assert client.get("/api/forecast?month=2027-05").json()["expenses"] == 35000


def test_annual_overdue_oldest_count_and_next_date(client, category_id, clock):
    item = bill(
        client,
        category_id,
        frequency="annual",
        due_month=2,
        due_day=28,
        start_month="2024-01",
        payment_tracking_start="2024-01-01",
    )
    data = dues(client)["annual"][0]
    assert data["overdue_count"] == 3
    assert data["overdue"][0]["due_date"] == "2024-02-28"
    assert data["next"]["due_date"] == "2027-02-28"
    assert mark(client, item, "2024").status_code == 200
    assert dues(client)["annual"][0]["overdue_count"] == 2
    assert dues(client)["annual"][0]["overdue"][0]["period"] == "2025"


def test_annual_effective_amount_override_and_due_month_forecast(
    client, category_id, clock
):
    item = bill(
        client,
        category_id,
        frequency="annual",
        due_month=12,
        due_day=1,
        distribute_annual=False,
        amount=12000,
    )
    endpoint = "/api/recurring/" + item["id"] + "/amount"
    assert (
        client.put(endpoint, json=dict(month="2026-06", amount=24000)).status_code
        == 200
    )
    assert (
        client.put(
            endpoint, json=dict(month="2026-12", amount=30000, override=True)
        ).status_code
        == 200
    )
    assert (
        client.put(
            endpoint, json=dict(month="2026-01", amount=9000, override=True)
        ).status_code
        == 422
    )
    row = dues(client)["annual"][0]["next"]
    assert row["amount"] == 30000 and row["due_date"] == "2026-12-01"
    assert client.get("/api/forecast?month=2026-01").json()["expenses"] == 0
    assert client.get("/api/forecast?month=2026-12").json()["expenses"] == 30000
    assert client.get("/api/forecast?month=2027-12").json()["expenses"] == 24000


def test_payment_status_idempotent_early_correctable_and_actuals_unchanged(
    client, category_id, clock, db
):
    item = bill(client, category_id, due_day=20)
    baseline = client.get("/api/forecast?month=2026-11").json()
    assert mark(client, item, "2026-11", paid_on="2026-11-06").status_code == 200
    assert mark(client, item, "2026-11").json()["paid_on"] == "2026-11-06"
    assert db.scalar(select(func.count()).select_from(BillPayment)) == 1
    assert dues(client)["monthly_upcoming"][0]["paid"]
    assert (
        mark(client, item, "2026-11", paid_on="2026-11-05").json()["paid_on"]
        == "2026-11-05"
    )
    assert client.get("/api/forecast?month=2026-11").json() == baseline
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0
    assert mark(client, item, "2026-11", False).json()["paid"] is False
    assert mark(client, item, "2026-11", False).status_code == 200
    assert not dues(client)["monthly_upcoming"][0]["paid"]
    assert dues(client)["paid_history"] == []


def test_payment_confirmation_history_survives_schedule_edits(
    client, category_id, clock, db
):
    item = bill(client, category_id, due_day=10, amount=12000)
    assert mark(client, item, "2026-11").status_code == 200
    response = client.put("/api/recurring/" + item["id"], json={**item, "due_day": 15})
    assert response.status_code == 200, response.text
    client.put(
        "/api/recurring/" + item["id"] + "/amount",
        json=dict(month="2026-11", amount=24000),
    )
    row = dues(client)["monthly_upcoming"][0]
    assert row["paid"] and row["due_date"] == "2026-11-15"
    assert row["amount"] == 12000 and row["confirmed_due_date"] == "2026-11-10"
    history = dues(client)["paid_history"][0]
    assert history["due_date"] == "2026-11-10" and history["amount"] == 12000
    # Even disabling dates cannot erase or prevent correcting a saved confirmation.
    client.put(
        "/api/recurring/" + item["id"], json={**response.json(), "due_day": None}
    )
    assert mark(client, item, "2026-11", paid_on="2026-11-06").status_code == 200
    assert dues(client)["paid_history"][0]["paid_on"] == "2026-11-06"
    assert db.scalar(select(BillPayment)).due_date == date(2026, 11, 10)


def test_annual_confirmation_covers_year_after_due_month_change(
    client, category_id, clock
):
    item = bill(client, category_id, frequency="annual", due_month=11, due_day=20)
    mark(client, item, "2026")
    client.put("/api/recurring/" + item["id"], json={**item, "due_month": 12})
    row = dues(client)["annual"][0]["next"]
    assert row["period"] == "2026" and row["paid"]
    assert row["confirmed_due_date"] == "2026-11-20"


def test_ach_recorded_marks_paid_without_confirmation(
    client, category_id, account_id, clock, db
):
    item = bill(
        client,
        category_id,
        due_day=7,
        ach_enabled=True,
        ach_day=5,
        ach_start_month="2026-11",
        ach_account_id=account_id,
    )
    row = dues(client)["monthly_upcoming"][0]
    assert row["ach_recorded"] and row["paid"] and row["automatic"]
    assert row["paid_source"] == "ach" and row["paid_on"] == "2026-11-05"
    transactions = client.get("/api/transactions?month=2026-11").json()
    assert len(transactions) == 1 and transactions[0]["date"] == "2026-11-05"
    assert mark(client, item, "2026-11").status_code == 409
    assert client.get("/api/transactions?month=2026-11").json() == transactions
    assert db.scalar(select(func.count()).select_from(BillPayment)) == 0
    assert dues(client)["paid_history"][0]["paid_source"] == "ach"


@pytest.mark.parametrize(
    "changes",
    [
        {"due_day": 0},
        {"due_day": 32},
        {"due_month": 13},
        {"due_month": 2},
        {"due_month": 2, "due_day": None, "frequency": "annual"},
        {"kind": "receivable"},
        {"payment_tracking_start": "1800-01-01"},
    ],
)
def test_due_validation(client, category_id, changes):
    data = dict(
        name="Invalid",
        kind="payable",
        frequency="monthly",
        amount=12000,
        category_id=category_id,
        start_month="2025-01",
        due_day=7,
    )
    assert client.post("/api/recurring", json={**data, **changes}).status_code == 422


@pytest.mark.parametrize(
    "period", ["2026", "2026-00", "2026-13", "2026-10", "1899-11", "bad"]
)
def test_invalid_or_untracked_occurrence_rejected(client, category_id, clock, period):
    item = bill(client, category_id)
    assert mark(client, item, period).status_code == 422


def test_future_paid_date_and_missing_or_income_schedule_rejected(
    client, category_id, clock
):
    item = bill(client, category_id)
    assert mark(client, item, "2026-11", paid_on="2026-11-08").status_code == 422
    assert mark(client, {"id": "missing"}, "2026-11").status_code == 404
    income = bill(client, category_id, kind="receivable", due_day=None)
    assert mark(client, income, "2026-11").status_code == 422


def test_concurrent_paid_updates_do_not_duplicate_confirmation(
    client, category_id, clock, db
):
    item = bill(client, category_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: mark(client, item, "2026-11"), range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert db.scalar(select(func.count()).select_from(BillPayment)) == 1


def test_local_timezone_drives_due_window_and_tracking_start(
    client, category_id, monkeypatch
):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 1, 2, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("abacus.clock.datetime", FrozenDatetime)
    monkeypatch.setenv("APP_TIMEZONE", "America/Detroit")
    item = bill(client, category_id, due_day=31)
    assert item["payment_tracking_start"] == "2025-12-31"
    assert dues(client)["today"] == "2025-12-31"
    assert dues(client)["through"] == "2026-01-30"


def test_existing_undated_schedule_forecast_unchanged(client, category_id, clock):
    item = bill(
        client, category_id, frequency="annual", due_day=None, distribute_annual=False
    )
    assert item["due_day"] is None and item["payment_tracking_start"] is None
    assert client.get("/api/forecast?month=2026-01").json()["expenses"] == 12000
    assert client.get("/api/forecast?month=2026-11").json()["expenses"] == 0
    assert dues(client)["annual"][0]["allowance"]


def test_manual_actual_does_not_confirm_bill_and_annual_period_validation(
    client, category_id, account_id, clock
):
    item = bill(client, category_id)
    response = client.post(
        "/api/transactions",
        json=dict(
            date="2026-11-07",
            description=item["name"],
            amount=12000,
            kind="purchase",
            category_id=category_id,
            account_id=account_id,
        ),
    )
    assert response.status_code == 201, response.text
    assert not dues(client)["monthly_upcoming"][0]["paid"]
    annual = bill(client, category_id, frequency="annual", due_month=12, due_day=31)
    assert mark(client, annual, "2026-12").status_code == 422
    assert mark(client, annual, "2026", paid_on="2026-11-06").status_code == 200
    assert dues(client)["annual"][0]["next"]["paid"]


def test_first_due_in_future_tracking_year_and_short_final_schedule(
    client, category_id, clock
):
    bill(
        client,
        category_id,
        frequency="annual",
        start_month="2028-03",
        end_month="2028-10",
        due_month=2,
        due_day=29,
        payment_tracking_start="2028-03-01",
    )
    summary = dues(client)["annual"][0]
    assert summary["next"] is None and summary["overdue"] == []


def test_ach_without_contractual_due_date_uses_debit_day(
    client, category_id, account_id, clock
):
    item = bill(
        client,
        category_id,
        due_day=None,
        ach_enabled=True,
        ach_day=7,
        ach_start_month="2026-11",
        ach_account_id=account_id,
    )
    assert item["payment_tracking_start"] is None
    row = dues(client)["monthly_upcoming"][0]
    assert row["due_date"] == "2026-11-07" and row["automatic"] and row["paid"]
    assert mark(client, item, "2026-11", False).status_code == 409


def test_scheduled_ach_not_recorded_is_not_overdue(
    client, category_id, account_id, clock
):
    bill(
        client,
        category_id,
        due_day=5,
        payment_tracking_start="2026-11-01",
        ach_enabled=True,
        ach_day=15,
        ach_start_month="2026-11",
        ach_account_id=account_id,
    )
    data = dues(client)
    assert data["monthly_overdue"] == []
    assert data["monthly_upcoming"][0]["automatic"]
    assert data["monthly_upcoming"][0]["status"] == "automatic"
    assert data["paid_history"] == []
    clock[0] = date(2026, 11, 15)
    assert client.post("/api/recurring/record-due").json()["added"] == 1
    history = dues(client)["paid_history"][0]
    assert history["period"] == "2026-11" and history["paid_source"] == "ach"
    assert dues(client)["monthly_overdue"] == []


def test_disabling_ach_keeps_recorded_debits_paid(
    client, category_id, account_id, clock
):
    item = bill(
        client,
        category_id,
        due_day=7,
        ach_enabled=True,
        ach_day=5,
        ach_start_month="2026-11",
        ach_account_id=account_id,
    )
    assert (
        client.put(
            "/api/recurring/" + item["id"], json={**item, "ach_enabled": False}
        ).status_code
        == 200
    )
    row = dues(client)["monthly_upcoming"][0]
    assert row["paid"] and row["paid_source"] == "ach" and row["automatic"]
    assert dues(client)["paid_history"][0]["paid_source"] == "ach"
    assert mark(client, item, "2026-11", False).status_code == 409


def test_budget_allowances_do_not_generate_payment_prompts_or_actuals(
    client, category_id, clock, db
):
    for name in ["Pet", "Groceries", "Entertainment"]:
        bill(client, category_id, name=name, due_day=None, amount=12000)
    bill(
        client,
        category_id,
        name="Medical copay",
        frequency="annual",
        due_day=None,
        amount=60000,
        distribute_annual=True,
    )
    data = dues(client)
    assert data["monthly_upcoming"] == [] and data["monthly_overdue"] == []
    allowance = data["annual"][0]
    assert allowance["allowance"] and not allowance["missing_due_date"]
    assert (
        allowance["annual_amount"] == 60000 and allowance["monthly_allocation"] == 5000
    )
    assert allowance["next"] is None and allowance["overdue_count"] == 0
    assert client.get("/api/forecast?month=2026-11").json()["expenses"] == 41000
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0
    assert db.scalar(select(func.count()).select_from(BillPayment)) == 0


def test_periods_before_ach_activation_keep_manual_tracking(
    client, category_id, account_id, clock
):
    item = bill(
        client,
        category_id,
        due_day=7,
        payment_tracking_start="2026-10-01",
        ach_enabled=True,
        ach_day=15,
        ach_start_month="2026-11",
        ach_account_id=account_id,
    )
    row = dues(client)["monthly_overdue"][0]
    assert row["period"] == "2026-10" and not row["automatic"]
    assert mark(client, item, "2026-10", paid_on="2026-10-07").status_code == 200
    assert dues(client)["monthly_overdue"] == []
    assert dues(client)["paid_history"][0]["paid_source"] == "manual"

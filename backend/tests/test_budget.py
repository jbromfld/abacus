from datetime import date
from types import SimpleNamespace as Obj

import pytest
from abacus.budget import scheduled_amount, shift_month


def test_annual_expense_allocations_bounds_and_effective_changes():
    item = Obj(
        id="r",
        start_month="2025-12",
        end_month="2027-12",
        frequency="annual",
        kind="payable",
        distribute_annual=True,
    )
    changes = [
        Obj(recurring_id="r", month="2025-12", amount=1200, override=False),
        Obj(recurring_id="r", month="2026-06", amount=2400, override=False),
        Obj(recurring_id="r", month="2026-12", amount=3000, override=True),
    ]
    assert scheduled_amount(item, changes, "2025-11") == 0
    assert scheduled_amount(item, changes, "2025-12") == 100
    assert scheduled_amount(item, changes, "2026-01") == 100
    assert scheduled_amount(item, changes, "2026-12") == 250
    assert scheduled_amount(item, changes, "2027-12") == 200
    assert scheduled_amount(item, changes, "2028-12") == 0


def test_month_shift_year_boundary():
    assert shift_month("2026-01", -1) == "2025-12"
    assert shift_month("2025-12", 1) == "2026-01"


def test_forecast_no_carry_drafts_preview_and_overrides(client, category_id):
    def recurring(name, kind, amount):
        response = client.post(
            "/api/recurring",
            json=dict(
                name=name,
                kind=kind,
                frequency="monthly",
                amount=amount,
                category_id=category_id if kind == "payable" else None,
                start_month="2025-01",
            ),
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    recurring("Income", "receivable", 10000)
    bill = recurring("Groceries", "payable", 4000)
    draft = client.post(
        "/api/purchases",
        json=dict(name="Trip", amount=7000, month="2025-02", category_id=category_id),
    ).json()
    assert not draft["included"]
    f = client.get("/api/forecast?month=2025-02").json()
    assert f["remaining"] == 6000 and not f["deficit"]
    preview = client.get(
        "/api/forecast", params={"month": "2025-02", "preview": draft["id"]}
    ).json()
    assert preview["remaining"] == -1000 and preview["deficit"]
    client.put("/api/purchases/" + draft["id"], json={**draft, "included": True})
    assert (
        client.get(
            "/api/forecast", params={"month": "2025-02", "preview": draft["id"]}
        ).json()["expenses"]
        == 11000
    )
    assert client.get("/api/forecast?month=2025-03").json()["remaining"] == 6000
    assert (
        client.put(
            f"/api/recurring/{bill}/amount", json={"month": "2025-03", "amount": 5000}
        ).status_code
        == 200
    )
    client.put(
        f"/api/recurring/{bill}/amount",
        json={"month": "2025-04", "amount": 10000, "override": True},
    )
    assert client.get("/api/forecast?month=2025-02").json()["expenses"] == 11000
    assert client.get("/api/forecast?month=2025-03").json()["expenses"] == 5000
    exact = client.get("/api/forecast?month=2025-04").json()
    assert exact["remaining"] == 0 and not exact["deficit"]
    assert client.get("/api/forecast?month=2025-05").json()["expenses"] == 5000
    assert (
        client.put(
            f"/api/recurring/{bill}/amount", json={"month": "2024-12", "amount": 100}
        ).status_code
        == 422
    )


def test_actuals_refunds_payments_categories_and_missing(
    client, category_id, account_id
):
    for kind, amount in [
        ("purchase", 1000),
        ("refund", 300),
        ("fee", 50),
        ("payment", 99999),
        ("transfer", 99999),
    ]:
        response = client.post(
            "/api/transactions",
            json=dict(
                date="2025-12-02",
                description=kind,
                amount=amount,
                kind=kind,
                category_id=category_id,
                account_id=account_id,
            ),
        )
        assert response.status_code == 201, response.text
    f = client.get("/api/forecast?month=2025-12").json()
    assert f["actual"]["expenses"] == 750 and f["actual_deficit"]
    assert f["expenses"] == 0
    points = client.get(
        "/api/trends", params={"end": "2026-01", "category_ids": category_id}
    ).json()
    assert len(points) == 12 and points[0]["month"] == "2025-02"
    december = points[-2]
    assert (
        december["actual"] == 750
        and december["categories"][category_id]["actual"] == 750
        and december["status"] == "partial"
    )
    assert points[-1]["actual"] is None and points[-1]["status"] == "missing"
    client.put("/api/months/2026-01", json={"complete": True})
    assert client.get("/api/trends?end=2026-01").json()[-1]["actual"] == 0
    assert client.get("/api/trends?end=2026-01").json()[-1]["status"] == "complete"
    current = date.today().strftime("%Y-%m")
    client.put("/api/months/" + current, json={"complete": True})
    assert (
        client.get("/api/forecast", params={"month": current}).json()["actual"][
            "status"
        ]
        == "partial"
    )


@pytest.mark.parametrize("amount", [0, -1, 1.5, "10"])
def test_money_validation(client, category_id, amount):
    assert (
        client.post(
            "/api/purchases",
            json=dict(
                name="Invalid", amount=amount, month="2026-01", category_id=category_id
            ),
        ).status_code
        == 422
    )


def test_settings_currency_locked_and_foreign_keys(client, category_id):
    assert (
        client.put("/api/settings", json={"currency": "JPY", "model": ""}).status_code
        == 200
    )
    p = client.post(
        "/api/purchases",
        json=dict(name="Book", amount=300, month="2026-01", category_id=category_id),
    )
    assert p.status_code == 201
    assert (
        client.put("/api/settings", json={"currency": "USD", "model": ""}).status_code
        == 409
    )
    assert client.delete("/api/categories/" + category_id).status_code == 409
    assert client.get("/api/categories").status_code == 200


def test_cross_origin_rejected(client):
    assert (
        client.post(
            "/api/accounts",
            json={"name": "Unexpected"},
            headers={"origin": "https://elsewhere.invalid"},
        ).status_code
        == 403
    )
    assert (
        client.get("/api/settings", headers={"host": "elsewhere.invalid"}).status_code
        == 403
    )


@pytest.mark.parametrize("frequency", ["monthly", "annual"])
def test_edit_first_month_earlier_and_later_preserves_amount_history(
    client, category_id, frequency
):
    annual = frequency == "annual"
    initial = 12000 if annual else 1000
    changed = 24000 if annual else 2000
    override = 42000 if annual else 3500
    payload = dict(
        name="Bill",
        kind="payable",
        frequency=frequency,
        amount=initial,
        category_id=category_id,
        start_month="2025-06",
        end_month="2027-12",
    )
    response = client.post("/api/recurring", json=payload)
    assert response.status_code == 201
    item = response.json()
    id = item["id"]
    client.put(
        f"/api/recurring/{id}/amount", json=dict(month="2025-12", amount=changed)
    )
    client.put(
        f"/api/recurring/{id}/amount",
        json=dict(month="2026-02", amount=override, override=True),
    )
    assert (
        client.put(
            f"/api/recurring/{id}", json={**item, "start_month": "2025-03"}
        ).status_code
        == 200
    )
    assert client.get("/api/forecast?month=2025-02").json()["expenses"] == 0
    assert client.get("/api/forecast?month=2025-03").json()["expenses"] == 1000
    if frequency == "annual":
        assert client.get("/api/forecast?month=2025-06").json()["expenses"] == 1000
        assert client.get("/api/forecast?month=2026-03").json()["expenses"] == 2000
    else:
        assert client.get("/api/forecast?month=2026-02").json()["expenses"] == 3500
    # Moving forward picks the applicable default, not the month's override.
    assert (
        client.put(
            f"/api/recurring/{id}", json={**item, "start_month": "2026-02"}
        ).status_code
        == 200
    )
    assert client.get("/api/forecast?month=2026-01").json()["expenses"] == 0
    assert client.get("/api/forecast?month=2026-02").json()["expenses"] == 3500
    assert (
        client.get(
            "/api/forecast?month="
            + ("2026-03" if frequency == "monthly" else "2027-02")
        ).json()["expenses"]
        == 2000
    )
    saved = next(r for r in client.get("/api/recurring").json() if r["id"] == id)
    assert any(
        c["month"] == "2025-12" and c["amount"] == changed for c in saved["changes"]
    )
    assert any(
        c["month"] == "2026-02" and not c["override"] and c["amount"] == changed
        for c in saved["changes"]
    )
    baseline = next(
        c for c in saved["changes"] if c["month"] == "2026-02" and not c["override"]
    )
    assert (
        client.delete(f"/api/recurring/{id}/amount/" + baseline["id"]).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/recurring/{id}", json={**item, "start_month": "2028-01"}
        ).status_code
        == 422
    )


def test_edit_first_month_to_existing_default_avoids_duplicate(client, category_id):
    item = client.post(
        "/api/recurring",
        json=dict(
            name="Bill",
            kind="payable",
            frequency="monthly",
            amount=1000,
            category_id=category_id,
            start_month="2025-01",
        ),
    ).json()
    client.put(
        "/api/recurring/" + item["id"] + "/amount",
        json=dict(month="2025-06", amount=2500),
    )
    for _ in range(2):
        assert (
            client.put(
                "/api/recurring/" + item["id"], json={**item, "start_month": "2025-06"}
            ).status_code
            == 200
        )
    saved = client.get("/api/recurring").json()[0]
    assert len(saved["changes"]) == 2
    assert client.get("/api/forecast?month=2025-06").json()["expenses"] == 2500


@pytest.mark.parametrize("amount", [1, 11, 12, 13, 10000, 10001, 120000])
def test_annual_expense_rounding_preserves_exact_yearly_total(amount):
    item = Obj(
        id="annual",
        kind="payable",
        frequency="annual",
        distribute_annual=True,
        start_month="2025-03",
        end_month=None,
    )
    changes = [
        Obj(recurring_id=item.id, month=item.start_month, amount=amount, override=False)
    ]
    for cycle in (0, 12, 24):
        shares = [
            scheduled_amount(item, changes, shift_month(item.start_month, cycle + i))
            for i in range(12)
        ]
        assert sum(shares) == amount
        assert max(shares) - min(shares) <= 1


def test_annual_expense_effective_rate_and_override_rounding():
    item = Obj(
        id="annual",
        kind="payable",
        frequency="annual",
        distribute_annual=True,
        start_month="2025-01",
        end_month="2026-12",
    )
    changes = [
        Obj(recurring_id=item.id, month="2025-01", amount=10000, override=False),
        Obj(recurring_id=item.id, month="2025-07", amount=20000, override=False),
        Obj(recurring_id=item.id, month="2025-09", amount=30000, override=True),
    ]
    assert scheduled_amount(item, changes, "2025-01") == 834
    assert scheduled_amount(item, changes, "2025-05") == 833
    assert scheduled_amount(item, changes, "2025-07") == 1667
    assert scheduled_amount(item, changes, "2025-09") == 2500
    assert scheduled_amount(item, changes, "2025-10") == 1667
    assert scheduled_amount(item, changes, "2026-03") == 1666
    assert scheduled_amount(item, changes, "2027-01") == 0


def test_annual_income_keeps_full_scheduled_payment():
    item = Obj(
        id="income",
        kind="receivable",
        frequency="annual",
        start_month="2025-05",
        end_month=None,
    )
    changes = [
        Obj(recurring_id=item.id, month=item.start_month, amount=120000, override=False)
    ]
    assert scheduled_amount(item, changes, "2025-05") == 120000
    assert scheduled_amount(item, changes, "2025-06") == 0
    assert scheduled_amount(item, changes, "2026-05") == 120000


def test_annual_expense_forecast_trends_breakdown_and_actuals(
    client, category_id, account_id
):
    client.post(
        "/api/recurring",
        json=dict(
            name="Insurance",
            kind="payable",
            frequency="annual",
            distribute_annual=True,
            start_month="2025-01",
            amount=120000,
            category_id=category_id,
        ),
    )
    client.post(
        "/api/transactions",
        json=dict(
            date="2025-01-15",
            description="Insurance payment to merchant",
            amount=120000,
            kind="purchase",
            category_id=category_id,
            account_id=account_id,
        ),
    )
    january = client.get("/api/forecast?month=2025-01").json()
    assert january["expenses"] == 10000 and january["actual"]["expenses"] == 120000
    assert client.get("/api/forecast?month=2025-02").json()["expenses"] == 10000
    points = client.get("/api/trends?end=2025-12").json()
    assert all(point["forecast"] == 10000 for point in points)
    report = client.get(
        "/api/expenses/breakdown",
        params={"start": "2025-01-01", "end": "2025-12-31", "basis": "forecast"},
    ).json()
    assert report["net"] == 120000 and report["entry_count"] == 12
    assert all(entry["amount"] == 10000 for entry in report["entries"])


def test_annual_due_month_boundaries_effective_changes_and_override():
    item = Obj(
        id="subscription",
        kind="payable",
        frequency="annual",
        distribute_annual=False,
        start_month="2025-12",
        end_month="2027-12",
    )
    changes = [
        Obj(recurring_id=item.id, month="2025-12", amount=12000, override=False),
        Obj(recurring_id=item.id, month="2026-04", amount=15000, override=False),
        Obj(recurring_id=item.id, month="2026-12", amount=9000, override=True),
    ]
    assert scheduled_amount(item, changes, "2025-11") == 0
    assert scheduled_amount(item, changes, "2025-12") == 12000
    assert all(
        scheduled_amount(item, changes, f"2026-{m:02d}") == 0 for m in range(1, 12)
    )
    assert scheduled_amount(item, changes, "2026-12") == 9000
    assert scheduled_amount(item, changes, "2027-12") == 15000
    assert scheduled_amount(item, changes, "2028-12") == 0


def test_annual_distribution_toggle_forecast_breakdown_trends_and_actuals(
    client, category_id, account_id
):
    data = dict(
        name="Digital subscription",
        kind="payable",
        frequency="annual",
        start_month="2025-03",
        amount=12000,
        category_id=category_id,
        distribute_annual=False,
    )
    result = client.post("/api/recurring", json=data)
    assert result.status_code == 201, result.text
    item = result.json()
    assert item["distribute_annual"] is False
    assert client.get("/api/recurring").json()[0]["distribute_annual"] is False
    assert client.get("/api/forecast?month=2025-03").json()["expenses"] == 12000
    assert client.get("/api/forecast?month=2025-04").json()["expenses"] == 0
    assert client.get("/api/forecast?month=2026-03").json()["expenses"] == 12000
    breakdown = client.get(
        "/api/expenses/breakdown?start=2025-03-01&end=2026-02-28&basis=forecast"
    ).json()
    assert breakdown["net"] == 12000 and breakdown["entry_count"] == 1
    assert breakdown["entries"][0]["month"] == "2025-03"
    trends = client.get("/api/trends?end=2026-02").json()
    assert [point["forecast"] for point in trends] == [12000] + [0] * 11
    actual = client.post(
        "/api/transactions",
        json=dict(
            date="2025-03-02",
            description="Subscription",
            amount=12000,
            kind="purchase",
            category_id=category_id,
            account_id=account_id,
        ),
    ).json()
    assert (
        client.put(
            "/api/recurring/" + item["id"], json={**item, "distribute_annual": True}
        ).status_code
        == 200
    )
    assert client.get("/api/forecast?month=2025-03").json()["expenses"] == 1000
    assert client.get("/api/forecast?month=2025-04").json()["expenses"] == 1000
    assert (
        client.get("/api/forecast?month=2025-03").json()["actual"]["expenses"] == 12000
    )
    assert client.get("/api/transactions").json()[0]["id"] == actual["id"]


def test_annual_distribution_defaults_true_and_is_ignored_for_income_and_monthly(
    client, category_id
):
    for kind, frequency, amount, expected in [
        ("payable", "annual", 12000, 1000),
        ("payable", "monthly", 12000, 12000),
        ("receivable", "annual", 12000, 0),
    ]:
        data = dict(
            name=kind + frequency,
            kind=kind,
            frequency=frequency,
            start_month="2025-03",
            amount=amount,
            category_id=category_id,
        )
        if frequency == "monthly" or kind == "receivable":
            data["distribute_annual"] = False
        response = client.post("/api/recurring", json=data)
        assert response.status_code == 201, response.text
        item = response.json()
        result = client.get("/api/forecast?month=2025-04").json()
        line = next(
            (line for line in result["lines"] if line["id"] == item["id"]), None
        )
        assert (line["amount"] if line else 0) == expected
        if kind == "payable" and frequency == "annual":
            assert item["distribute_annual"] is True
        if kind == "receivable":
            assert client.get("/api/forecast?month=2026-03").json()["income"] == 12000


def test_due_month_only_overrides_and_midyear_rate_change(client, category_id):
    item = client.post(
        "/api/recurring",
        json=dict(
            name="Annual subscription",
            kind="payable",
            frequency="annual",
            start_month="2025-05",
            amount=12000,
            category_id=category_id,
            distribute_annual=False,
        ),
    ).json()
    endpoint = "/api/recurring/" + item["id"] + "/amount"
    assert (
        client.put(
            endpoint, json=dict(month="2025-07", amount=9000, override=True)
        ).status_code
        == 422
    )
    assert (
        client.put(
            endpoint, json=dict(month="2025-07", amount=15000, override=False)
        ).status_code
        == 200
    )
    assert client.get("/api/forecast?month=2025-05").json()["expenses"] == 12000
    assert client.get("/api/forecast?month=2025-07").json()["expenses"] == 0
    assert client.get("/api/forecast?month=2026-05").json()["expenses"] == 15000
    assert (
        client.put(
            endpoint, json=dict(month="2026-05", amount=18000, override=True)
        ).status_code
        == 200
    )
    assert client.get("/api/forecast?month=2026-05").json()["expenses"] == 18000
    assert client.get("/api/forecast?month=2027-05").json()["expenses"] == 15000


@pytest.mark.parametrize(
    "savings,combined,deficit",
    [
        (20000, 10000, False),
        (10000, 0, False),
        (9999, -1, True),
        (0, -10000, True),
        (None, -10000, True),
    ],
)
def test_forecast_window_flags_deficits_after_current_savings_without_carry_forward(
    client, db, category_id, savings, combined, deficit
):
    from abacus.models import Settings

    db.get(Settings, 1).savings_balance = savings
    db.commit()
    for name, kind, amount in [
        ("Income", "receivable", 10000),
        ("Bill", "payable", 20000),
    ]:
        response = client.post(
            "/api/recurring",
            json={
                "name": name,
                "kind": kind,
                "frequency": "monthly",
                "amount": amount,
                "start_month": "2026-01",
                "category_id": category_id if kind == "payable" else None,
            },
        )
        assert response.status_code == 201
    rows = client.get(
        "/api/forecasts",
        params={"start": "2026-01", "months": 12, "include_savings": True},
    ).json()
    assert len(rows) == 12
    for row in rows:
        assert row["remaining"] == -10000 and row["deficit"] is True
        assert row["savings_balance"] == savings
        assert row["remaining_with_savings"] == combined
        assert row["savings_adjusted_deficit"] is deficit
    # The ordinary monthly forecast and user-entered savings are untouched.
    assert client.get("/api/forecast?month=2026-01").json()["deficit"] is True
    assert db.get(Settings, 1).savings_balance == savings

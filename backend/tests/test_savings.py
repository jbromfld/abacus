import json

import pytest
from abacus.models import Settings, Transaction
from abacus.savings import infer_monthly_bill
from sqlalchemy import func, select


def recurring(client, category_id, name, amount, **changes):
    data = dict(
        name=name,
        kind="payable",
        frequency="monthly",
        start_month="2026-01",
        amount=amount,
        category_id=category_id,
    )
    data.update(changes)
    result = client.post("/api/recurring", json=data)
    assert result.status_code == 201, result.text
    return result.json()


def baseline(client, category_id, annual=False):
    recurring(client, category_id, "Income", 100000, kind="receivable")
    recurring(client, category_id, "Ordinary expenses", 55000 if annual else 65000)
    if annual:
        recurring(
            client,
            category_id,
            "Summer tax",
            120000,
            frequency="annual",
            distribute_annual=True,
            due_day=15,
            due_month=7,
        )


def project(
    client, amount=500000, start="2026-01", floor=0, months=24, bill=None, **extra
):
    if bill is None:
        bill = {"amount": 20000, "start_month": start}
    response = client.post(
        "/api/savings/projection",
        json=dict(
            savings={"amount": amount, "month": start, "floor": floor},
            months=months,
            bill=bill,
            **extra,
        ),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_example_is_deterministic_read_only_and_monthly_budgets_stay_independent(
    client, category_id, db, monkeypatch
):
    baseline(client, category_id)
    monkeypatch.setattr(
        "abacus.advisor.chat_with_model",
        lambda *a: pytest.fail("Preview must not use a model"),
    )
    before = client.get("/api/forecast?month=2026-01").json()
    result = project(client)
    assert result["first_bill_month_remaining"] == 15000
    assert (
        result["ending_savings"] == 860000
        and result["baseline_ending_savings"] == 1340000
    )
    assert result["total_new_bill_cost"] == 480000 and result["status"] == "fits"
    assert result["lowest_savings"] == 500000
    assert client.get("/api/forecast?month=2026-01").json() == before
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0
    assert db.get(Settings, 1).savings_balance is None


def test_annual_payment_replaces_allocations_once_and_can_break_savings(
    client, category_id
):
    baseline(client, category_id, annual=True)
    result = project(client, amount=50000, start="2026-06", months=12)
    june, july = result["months"][:2]
    assert june["forecast_expenses"] == 65000 and june["cash_expenses"] == 55000
    assert june["distributed_allocation_removed"] == 10000
    assert july["cash_expenses"] == 175000
    assert july["annual_payments"] == [{"name": "Summer tax", "amount": 120000}]
    assert june["scenario_savings"] == 75000 and july["scenario_savings"] == -20000
    assert (
        result["first_negative_month"] == "2026-07"
        and result["status"] == "negative_savings"
    )
    assert result["budget_deficit_months"] == []
    assert result["ending_savings"] == 230000
    assert sum(p["cash_expenses"] for p in result["months"]) == 780000


def test_non_distributed_annual_and_undated_allowance_are_not_double_counted(
    client, category_id
):
    recurring(client, category_id, "Income", 100000, kind="receivable")
    recurring(
        client,
        category_id,
        "Subscription",
        24000,
        frequency="annual",
        distribute_annual=False,
        due_day=20,
        due_month=3,
    )
    recurring(
        client,
        category_id,
        "Medical copay",
        12000,
        frequency="annual",
        distribute_annual=True,
    )
    result = project(client, months=12)
    assert result["months"][0]["cash_expenses"] == 1000
    assert result["months"][2]["cash_expenses"] == 25000
    assert sum(p["cash_expenses"] for p in result["months"]) == 36000


def test_exact_rounding_and_annual_rate_changes(client, category_id):
    recurring(client, category_id, "Income", 100000, kind="receivable")
    item = recurring(
        client, category_id, "Tax", 120005, frequency="annual", due_day=1, due_month=7
    )
    endpoint = "/api/recurring/" + item["id"] + "/amount"
    client.put(endpoint, json={"month": "2026-06", "amount": 240007})
    client.put(endpoint, json={"month": "2026-07", "amount": 360009, "override": True})
    result = project(client, months=12)
    assert result["months"][6]["cash_expenses"] == 360009
    assert result["months"][6]["annual_payments"][0]["amount"] == 360009
    assert sum(p["cash_expenses"] for p in result["months"]) == 360009
    assert all(
        p["cash_expenses"] == 0 for i, p in enumerate(result["months"]) if i != 6
    )


def test_bill_dates_end_month_floor_and_missing_income(client, category_id):
    baseline(client, category_id)
    result = project(
        client,
        months=12,
        bill={"amount": 40000, "start_month": "2026-03", "end_month": "2026-04"},
        floor=500001,
    )
    assert (
        result["months"][0]["extra_bill"] == 0
        and result["months"][2]["extra_bill"] == 40000
    )
    assert (
        result["months"][4]["extra_bill"] == 0
        and result["total_new_bill_cost"] == 80000
    )
    assert (
        result["status"] == "below_floor"
        and result["first_below_floor_month"] == "2026-01"
    )
    future = project(
        client, months=12, bill={"amount": 20000, "start_month": "2028-01"}
    )
    assert (
        future["status"] == "outside_horizon"
        and future["first_bill_month_remaining"] is None
    )
    income = next(
        r for r in client.get("/api/recurring").json() if r["kind"] == "receivable"
    )
    client.put(
        "/api/recurring/" + income["id"], json={**income, "end_month": "2026-06"}
    )
    result = project(client, months=12)
    assert (
        result["status"] == "missing_income"
        and result["missing_income_months"][0] == "2026-07"
    )


def test_savings_snapshot_persists_and_does_not_reset_with_other_settings(client):
    assert client.get("/api/savings").json()["amount"] is None
    payload = {"amount": 500000, "month": "2026-01", "floor": 100000}
    assert client.put("/api/savings", json=payload).json() == payload
    assert (
        client.put(
            "/api/settings",
            json={"currency": "USD", "model": "", "advisor_enabled": False},
        ).status_code
        == 200
    )
    assert client.get("/api/savings").json() == payload
    assert (
        client.put(
            "/api/settings",
            json={"currency": "EUR", "model": "", "advisor_enabled": False},
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"savings": {"amount": -1, "month": "2026-01"}},
        {"savings": {"amount": 1.5, "month": "2026-01"}},
        {"savings": {"amount": 0, "month": "2026-13"}},
        {"months": 36},
        {"savings": {"amount": 0, "month": "9998-12"}},
        {"bill": {"amount": 0, "start_month": "2026-01"}},
        {"bill": {"amount": 1, "start_month": "2026-02", "end_month": "2026-01"}},
        {"bill": {"amount": 1, "start_month": "2026-01"}, "estimate_id": "x"},
    ],
)
def test_projection_validation(client, changes):
    payload = {"savings": {"amount": 0, "month": "2026-01"}, **changes}
    assert client.post("/api/savings/projection", json=payload).status_code == 422


@pytest.mark.parametrize(
    "message",
    [
        "Could I take on another $200 monthly bill?",
        "Could I pay a 200 monthly expense?",
        "Try USD 200 bill per month",
    ],
)
def test_plain_monthly_bill_phrase_is_parsed_deterministically(message):
    bill = infer_monthly_bill(message, "2026-01", "USD")
    assert bill and bill.amount == 20000 and bill.start_month == "2026-01"


@pytest.mark.parametrize(
    "message",
    [
        "A $200 monthly bill and a $300 monthly bill",
        "A $200 monthly bill starting July 2027",
        "A $200 monthly bill next month",
        "A -$200 monthly bill",
        "A €200 monthly bill",
        "A $1,2 monthly bill",
        "A $200 per month saving goal",
        "A $200 monthly bill for 3 months",
    ],
)
def test_ambiguous_bill_phrases_abstain(message):
    assert infer_monthly_bill(message, "2026-01", "USD") is None


def test_advisor_uses_same_projection_for_inferred_and_structured_bill(
    client, category_id, db, monkeypatch
):
    baseline(client, category_id, annual=True)
    client.put("/api/savings", json={"amount": 50000, "month": "2026-06", "floor": 0})
    setting = db.get(Settings, 1)
    setting.model = "local-test"
    setting.advisor_enabled = True
    db.commit()
    captured = []
    monkeypatch.setattr(
        "abacus.advisor.chat_with_model",
        lambda model, messages: (
            captured.append(messages) or "The projection drops below zero in July."
        ),
    )
    response = client.post(
        "/api/advisor/chat",
        json={
            "month": "2026-06",
            "message": "Could I take on another $200 monthly bill?",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["context"]["savings_projection"]
    assert result["bill"]["amount"] == 20000 and result["bill_inferred_from_question"]
    assert result["first_negative_month"] == "2026-07"
    sent = json.loads(captured[0][0]["content"].split("BUDGET SNAPSHOT:\n")[1])
    assert "ending_savings" not in sent["savings_projection"]
    assert sent["savings_projection"]["display_summary"]["ending_savings"].startswith(
        "USD "
    )
    assert sent["savings_projection"]["display_summary"]["monthly_bill"] == "USD 200.00"
    assert (
        sent["savings_projection"]["display_summary"]["starting_savings"]
        == "USD 500.00"
    )
    assert (
        sent["savings_projection"]["annual_payments"][0]["payments"][0]["name"]
        == "Summer tax"
    )
    payload = {
        "month": "2026-06",
        "message": "Explain this estimate",
        "savings": {"amount": 50000, "month": "2026-06"},
        "monthly_bill": {"amount": 20000, "start_month": "2026-06"},
    }
    structured = client.post("/api/advisor/chat", json=payload).json()["context"][
        "savings_projection"
    ]
    assert structured["ending_savings"] == result["ending_savings"]
    assert client.get("/api/forecast?month=2026-06").json()["remaining"] == 35000


def test_savings_floor_includes_start_even_if_later_months_recover_then_fall(
    client, category_id
):
    baseline(client, category_id)
    result = project(
        client,
        months=12,
        floor=500001,
        bill={"amount": 60000, "start_month": "2026-03"},
    )
    assert result["months"][0]["scenario_savings"] > 500001
    assert result["months"][4]["scenario_savings"] < 500001
    assert result["first_below_floor_month"] == "2026-01"


def existing_change(
    client, id, action, amount=None, start="2026-01", end=None, savings=True
):
    change = {
        "recurring_id": id,
        "action": action,
        "start_month": start,
        "end_month": end,
    }
    if amount is not None:
        change["amount"] = amount
    payload = {"recurring_change": change, "months": 12}
    if savings:
        payload["savings"] = {"amount": 500000, "month": "2026-01"}
    else:
        payload["start_month"] = "2026-01"
    response = client.post("/api/savings/projection", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_modify_and_remove_recurring_are_read_only(client, category_id, db):
    baseline(client, category_id)
    item = next(
        r for r in client.get("/api/recurring").json() if r["kind"] == "payable"
    )
    before = client.get("/api/recurring").json()
    changed = existing_change(client, item["id"], "modify", 70000)
    assert changed["first_bill_month_remaining"] == 30000
    assert changed["first_active_month"] == "2026-01"
    assert changed["total_budget_change"] == 60000
    assert changed["ending_savings"] == 860000
    removed = existing_change(client, item["id"], "remove")
    assert removed["first_bill_month_remaining"] == 100000
    assert removed["total_budget_change"] == -780000
    assert removed["ending_savings"] == 1700000
    assert client.get("/api/recurring").json() == before
    assert client.get("/api/forecast?month=2026-01").json()["remaining"] == 35000
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0


def test_change_effective_window_preserves_overrides_and_later_rates(
    client, category_id
):
    baseline(client, category_id)
    item = next(
        r for r in client.get("/api/recurring").json() if r["kind"] == "payable"
    )
    endpoint = "/api/recurring/" + item["id"] + "/amount"
    client.put(endpoint, json={"month": "2026-04", "amount": 80000, "override": True})
    client.put(endpoint, json={"month": "2026-08", "amount": 60000})
    result = existing_change(
        client, item["id"], "modify", 70000, start="2026-03", end="2026-06"
    )
    rows = {p["month"]: p for p in result["months"]}
    assert rows["2026-01"]["budget_remaining_after_bill"] == 35000
    assert rows["2026-03"]["budget_remaining_after_bill"] == 30000
    assert rows["2026-04"]["budget_remaining_after_bill"] == 20000
    assert rows["2026-06"]["budget_remaining_after_bill"] == 30000
    assert rows["2026-07"]["budget_remaining_after_bill"] == 35000
    assert rows["2026-08"]["budget_remaining_after_bill"] == 40000
    assert result["total_budget_change"] == 15000
    permanent = existing_change(client, item["id"], "modify", 70000, start="2026-03")
    assert permanent["months"][7]["budget_remaining_after_bill"] == 40000


def test_remove_or_modify_distributed_annual_bill_uses_full_cash_payment_once(
    client, category_id
):
    baseline(client, category_id, annual=True)
    item = next(
        r for r in client.get("/api/recurring").json() if r["frequency"] == "annual"
    )
    payload = {
        "savings": {"amount": 50000, "month": "2026-06"},
        "months": 12,
        "recurring_change": {
            "recurring_id": item["id"],
            "action": "remove",
            "start_month": "2026-06",
        },
    }
    result = client.post("/api/savings/projection", json=payload).json()
    assert result["months"][0]["budget_remaining_after_bill"] == 45000
    assert result["months"][1]["annual_payments"] == []
    assert result["months"][1]["scenario_cash_expenses"] == 55000
    assert result["ending_savings"] == 590000
    assert result["total_budget_change"] == -120000
    payload["recurring_change"].update(action="modify", amount=240000)
    result = client.post("/api/savings/projection", json=payload).json()
    assert result["months"][0]["budget_remaining_after_bill"] == 25000
    assert result["months"][1]["annual_payments"] == [
        {"name": "Summer tax", "amount": 240000}
    ]
    assert result["months"][1]["scenario_cash_expenses"] == 295000
    assert result["first_negative_month"] == "2026-07"
    assert result["ending_savings"] == 350000


def test_temporary_removal_restores_original_account_after_window(client, category_id):
    baseline(client, category_id)
    item = next(
        r for r in client.get("/api/recurring").json() if r["kind"] == "payable"
    )
    result = existing_change(
        client, item["id"], "remove", start="2026-03", end="2026-04"
    )
    assert result["months"][1]["budget_remaining_after_bill"] == 35000
    assert result["months"][2]["budget_remaining_after_bill"] == 100000
    assert result["months"][4]["budget_remaining_after_bill"] == 35000
    assert result["total_budget_change"] == -130000


def test_budget_impact_works_without_savings_and_does_not_invent_balances(
    client, category_id
):
    baseline(client, category_id)
    payload = {
        "start_month": "2026-01",
        "bill": {"amount": 20000, "start_month": "2026-01"},
    }
    response = client.post("/api/savings/projection", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "budget_only" and not result["savings_known"]
    assert result["first_bill_month_remaining"] == 15000
    assert result["starting_savings"] is None and result["ending_savings"] is None
    assert result["lowest_savings"] is None
    assert all(p["scenario_savings"] is None for p in result["months"])
    item = next(
        r for r in client.get("/api/recurring").json() if r["kind"] == "payable"
    )
    removed = existing_change(client, item["id"], "remove", savings=False)
    assert removed["first_bill_month_remaining"] == 100000
    assert removed["ending_savings"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"recurring_id": "missing", "action": "modify", "start_month": "2026-01"},
        {
            "recurring_id": "missing",
            "action": "remove",
            "start_month": "2026-01",
            "amount": 100,
        },
        {
            "recurring_id": "missing",
            "action": "remove",
            "start_month": "2026-02",
            "end_month": "2026-01",
        },
    ],
)
def test_recurring_scenario_validation(client, change):
    assert (
        client.post(
            "/api/savings/projection",
            json={"start_month": "2026-01", "recurring_change": change},
        ).status_code
        == 422
    )


def test_recurring_scenario_reference_and_exclusivity_validation(client, category_id):
    baseline(client, category_id)
    data = {
        "start_month": "2026-01",
        "recurring_change": {
            "recurring_id": "missing",
            "action": "remove",
            "start_month": "2026-01",
        },
    }
    assert client.post("/api/savings/projection", json=data).status_code == 404
    income = next(
        r for r in client.get("/api/recurring").json() if r["kind"] == "receivable"
    )
    data["recurring_change"]["recurring_id"] = income["id"]
    assert client.post("/api/savings/projection", json=data).status_code == 422
    data["bill"] = {"amount": 20000, "start_month": "2026-01"}
    assert client.post("/api/savings/projection", json=data).status_code == 422


def test_advisor_monthly_budget_context_without_saved_savings(
    client, category_id, db, monkeypatch
):
    baseline(client, category_id)
    setting = db.get(Settings, 1)
    setting.model = "local-test"
    setting.advisor_enabled = True
    db.commit()
    monkeypatch.setattr(
        "abacus.advisor.chat_with_model",
        lambda *a: "The monthly budget has room; savings is not set.",
    )
    response = client.post(
        "/api/advisor/chat",
        json={"month": "2026-01", "message": "Could I add a $200 monthly bill?"},
    )
    assert response.status_code == 200, response.text
    context = response.json()["context"]
    assert context["savings_projection"]["first_bill_month_remaining"] == 15000
    assert not context["savings_projection"]["savings_known"]
    assert context["rules"]["bank_balances_and_savings_are_unknown"]


def test_as_is_projection_without_savings_shows_cash_flow_only(client, category_id):
    baseline(client, category_id, annual=True)
    response = client.post(
        "/api/savings/projection", json={"start_month": "2026-06", "months": 12}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "budget_only" and not result["savings_known"]
    assert result["months"][0]["forecast_remaining"] == 35000
    assert result["months"][0]["cash_remaining_after_bill"] == 45000
    assert result["months"][1]["cash_remaining_after_bill"] == -75000
    assert result["ending_savings"] is None and result["lowest_savings"] is None
    assert result["bill"] is None and result["recurring_change"] is None

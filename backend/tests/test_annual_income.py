"""Yearly estimates stay opt-in and sum exactly across calendar months."""

import pytest
from abacus.budget import ForecastInputs
from abacus.models import AnnualIncome, Recurring, Transaction
from sqlalchemy import func, select


def test_yearly_sources_are_opt_in_exact_and_do_not_repeat(client, db):
    payload = dict(year=2026, name="Expected tax refund", amount=100001)
    response = client.post("/api/annual-income", json=payload)
    assert response.status_code == 201, response.text
    source = response.json()
    assert not source["included"]
    assert sum(source["monthly_amounts"]) == 100001
    assert client.get("/api/forecast?month=2026-01").json()["income"] == 0
    assert (
        client.put(
            "/api/annual-income/" + source["id"], json=payload | {"included": True}
        ).status_code
        == 200
    )
    client.post(
        "/api/annual-income",
        json=dict(year=2026, name="Sale proceeds", amount=120000, included=True),
    )
    summary = client.get("/api/annual-income?year=2026").json()
    assert summary["total"] == summary["included_total"] == 220001
    assert sum(summary["monthly_amounts"]) == 220001
    inputs = ForecastInputs(db)
    assert [
        inputs.forecast(f"2026-{number:02d}")["income"] for number in range(1, 13)
    ] == summary["monthly_amounts"]
    assert inputs.forecast("2025-12")["income"] == 0
    assert inputs.forecast("2027-01")["income"] == 0
    assert client.delete("/api/annual-income/" + source["id"]).status_code == 200
    assert client.get("/api/annual-income?year=2026").json()["total"] == 120000
    assert db.scalar(select(func.count()).select_from(Recurring)) == 0
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0


def test_estimates_add_to_regular_income_and_are_labelled_in_advisor_context(
    client, db
):
    from abacus.advisor import budget_context, model_snapshot
    from abacus.schemas import AdvisorIn

    client.post(
        "/api/recurring",
        json=dict(
            name="Salary",
            kind="receivable",
            frequency="monthly",
            start_month="2026-01",
            amount=300000,
        ),
    )
    source = client.post(
        "/api/annual-income",
        json=dict(year=2026, name="Tax refund", amount=120000, included=True),
    ).json()
    request = AdvisorIn(month="2026-11", message="What is my income?")
    context = budget_context(db, request)
    assert context["monthly_forecasts"][0]["income_minor"] == 310000
    assert context["annual_income_estimates"][0]["included"]
    assert "not verified receipts" in context["annual_income_estimates"][0]["basis"]
    assert (
        model_snapshot(context)["annual_income_estimates"][0]["amount_display"]
        == "USD 1,200.00"
    )
    # A first-year estimate is a forecast change, not an included purchase.
    change = next(
        row
        for row in budget_context(
            db, AdvisorIn(month="2026-01", message="What changed?")
        )["forecast_comparison"]["changes"]
        if row["name"] == "Tax refund"
    )
    assert change["source"] == "annual_income_estimate"
    updated = client.put(
        "/api/annual-income/" + source["id"],
        json=dict(year=2026, name="Tax refund", amount=120000, included=False),
    )
    assert updated.status_code == 200
    assert client.get("/api/forecast?month=2026-11").json()["income"] == 300000


@pytest.mark.parametrize(
    "invalid",
    [
        dict(year=1899),
        dict(year=9999),
        dict(amount=0),
        dict(amount=-1),
        dict(amount=1.5),
        dict(amount=9000000000001),
        dict(name=" "),
    ],
)
def test_estimate_validation_does_not_create_invalid_sources(client, db, invalid):
    response = client.post(
        "/api/annual-income",
        json=dict(year=2026, name="Estimate", amount=1000) | invalid,
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(AnnualIncome)) == 0

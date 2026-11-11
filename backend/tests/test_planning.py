from datetime import date

import pytest
from abacus.models import Plan, Settings, Transaction
from sqlalchemy import func, select


def goal(client, name="Fall vacation", amount=240000, target="2027-10-01", **extra):
    response = client.post(
        "/api/planning",
        json=dict(name=name, amount=amount, target_date=target, **extra),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_goals_share_savings_once_and_are_permanently_deletable(client, db):
    client.put("/api/savings", json=dict(amount=800000, month="2026-11", floor=0))
    winter = goal(client, "Winter tax", 300000, "2027-02-15", category_id="tax")
    goal(client, "Summer tax", 600000, "2027-07-15", category_id="tax")
    goal(client)
    result = client.get("/api/planning").json()
    assert [row["set_aside"] for row in result["plans"]] == [300000, 500000, 0]
    assert result["set_aside"] == 800000 and result["free_savings"] == 0
    assert result["total_planned"] == 1140000
    assert result["plans"][-1]["category"] == "purchase"
    client.delete("/api/planning/" + winter["id"])
    assert client.get("/api/planning/" + winter["id"]).status_code == 404
    assert client.delete("/api/planning/" + winter["id"]).status_code == 200
    assert client.get("/api/savings").json()["amount"] == 800000
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0
    assert db.scalar(select(func.count()).select_from(Plan)) == 2


@pytest.mark.parametrize("dated", [True, False])
def test_linked_tax_payment_is_counted_once_with_dated_or_undated_annual_bills(
    client, category_id, dated
):
    bill = client.post(
        "/api/recurring",
        json=dict(
            name="Winter tax",
            kind="payable",
            frequency="annual",
            start_month="2026-01",
            amount=120000,
            category_id=category_id,
            distribute_annual=True,
            **(dict(due_month=12, due_day=15) if dated else {}),
        ),
    ).json()
    client.put("/api/savings", json=dict(amount=200000, month="2026-01", floor=0))
    before = client.get("/api/recurring").json()
    goal(
        client,
        "Winter tax",
        120000,
        "2026-12-15",
        category_id="tax",
        recurring_id=bill["id"],
    )
    data = client.get("/api/planning").json()
    december = next(
        row for row in data["projection"]["months"] if row["month"] == "2026-12"
    )
    assert december["balance"] == 80000
    assert december["plan_payments"] == 120000
    assert client.get("/api/recurring").json() == before
    duplicate = client.post(
        "/api/planning",
        json=dict(
            name="Duplicate tax",
            amount=120000,
            target_date="2026-12-20",
            recurring_id=bill["id"],
        ),
    )
    assert duplicate.status_code == 409


def test_categories_can_be_renamed_and_deleted_without_erasing_goals(client):
    category = client.post("/api/planning/categories", json=dict(name="garden")).json()
    item = goal(client, category_id=category["id"])
    assert (
        client.put(
            "/api/planning/categories/" + category["id"], json=dict(name="home")
        ).status_code
        == 200
    )
    assert client.get("/api/planning/" + item["id"]).json()["category"] == "home"
    client.delete("/api/planning/categories/" + category["id"])
    result = client.get("/api/planning/" + item["id"]).json()
    assert result["category_id"] is None and result["name"] == "Fall vacation"


@pytest.mark.parametrize(
    "invalid",
    [
        dict(amount=0),
        dict(amount=1.2),
        dict(target_date="2026-02-30"),
        dict(name=" "),
        dict(category_id="missing"),
        dict(recurring_id="missing"),
    ],
)
def test_goal_validation(client, invalid):
    response = client.post(
        "/api/planning",
        json=dict(name="Trip", amount=10000, target_date="2027-10-01") | invalid,
    )
    assert response.status_code == 422


def test_advisor_context_resolves_fresh_goal_and_rejects_deleted_inflight_goal(
    client, db, monkeypatch
):
    from abacus.advisor import budget_context, model_snapshot
    from abacus.db import Session
    from abacus.schemas import AdvisorIn

    item = goal(client)
    settings = db.get(Settings, 1)
    settings.model = "local-test"
    settings.advisor_enabled = True
    db.commit()
    request = AdvisorIn(month="2026-11", message="Can I fund this?", plan_id=item["id"])
    snapshot = model_snapshot(budget_context(db, request))
    assert snapshot["selected_plan"]["amount_display"] == "USD 2,400.00"

    def answer(*args):
        with Session() as write:
            write.delete(write.get(Plan, item["id"]))
            write.commit()
        return "A stale answer must not be displayed."

    monkeypatch.setattr("abacus.advisor.chat_with_model", answer)
    response = client.post("/api/advisor/chat", json=request.model_dump())
    assert response.status_code == 409, response.text
    assert "changed or was deleted" in response.json()["detail"]


def test_review_draft_never_saves_a_goal(client, db, monkeypatch):
    setting = db.get(Settings, 1)
    setting.model = "local-test"
    setting.advisor_enabled = True
    db.commit()
    monkeypatch.setattr(
        "abacus.planning.chat_with_model",
        lambda *a, **k: (
            '{"name":"Trip","amount":"1234.56","target_date":"2027-10-01","category":"vacation"}'
        ),
    )
    result = client.post(
        "/api/planning/draft",
        json=dict(user_message="Trip", assistant_message="USD 1,234.56 by 2027-10-01"),
    ).json()
    assert result["amount"] == 123456 and result["category_id"] == "vacation"
    assert db.scalar(select(func.count()).select_from(Plan)) == 0


def test_reset_migration_preserves_imported_expenses_and_recurring_bills(
    client, db, category_id, account_id, advisor_credentials
):
    from abacus.advisor_setup import provision_advisor
    from abacus.db import engine
    from abacus.models import BillEstimate, Purchase, ReservePlan, StatementImport
    from alembic import command
    from alembic.config import Config

    bill = client.post(
        "/api/recurring",
        json=dict(
            name="Regular bill",
            kind="payable",
            frequency="monthly",
            start_month="2026-01",
            amount=10000,
            category_id=category_id,
        ),
    ).json()
    job = StatementImport(
        account_id=account_id,
        period="2026-11",
        file_hash="synthetic",
        filename="synthetic.csv",
        status="committed",
        source={},
        rows=[],
    )
    db.add(job)
    db.flush()
    tx = Transaction(
        date=date(2026, 11, 1),
        description="Imported expense",
        amount=1234,
        kind="purchase",
        category_id=category_id,
        account_id=account_id,
        import_id=job.id,
        provenance={"row": 1},
    )
    db.add(tx)
    db.commit()
    tx_id = tx.id
    job_id = job.id
    before = client.get("/api/recurring").json()
    db.close()
    config = Config("alembic.ini")
    try:
        command.downgrade(config, "0015")
        db.add(
            Purchase(
                name="Obsolete draft",
                amount=1000,
                month="2027-01",
                category_id=category_id,
            )
        )
        db.add(
            BillEstimate(
                name="Obsolete bill draft",
                amount=1000,
                start_month="2027-01",
                category_id=category_id,
            )
        )
        db.add(
            ReservePlan(id=1, amount=1000, start_date=date(2026, 11, 1), schedules=[])
        )
        db.commit()
        db.close()
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        db.expire_all()
        assert db.get(Transaction, tx_id).amount == 1234
        assert db.get(Transaction, tx_id).import_id == job_id
        assert db.get(Transaction, tx_id).provenance == {"row": 1}
        assert client.get("/api/recurring").json() == before
        assert bill["id"] in [row["id"] for row in before]
        assert all(
            db.scalar(select(func.count()).select_from(model)) == 0
            for model in [Purchase, BillEstimate, ReservePlan, Plan]
        )
    finally:
        db.close()
        command.upgrade(config, "head")
        provision_advisor(engine.url, advisor_credentials[0], advisor_credentials[1])


def test_retrying_a_save_does_not_create_another_goal(client, db):
    from uuid import uuid4

    payload = dict(
        name="Trip", amount=120000, target_date="2027-10-01", request_id=str(uuid4())
    )
    first = client.post("/api/planning", json=payload)
    second = client.post("/api/planning", json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert db.scalar(select(func.count()).select_from(Plan)) == 1


def annual_tax(client, category_id, **extra):
    response = client.post(
        "/api/recurring",
        json=dict(
            name="Winter tax",
            kind="payable",
            frequency="annual",
            start_month="2026-01",
            amount=150000,
            category_id=category_id,
            distribute_annual=True,
            due_month=12,
            due_day=31,
            payment_tracking_start="2026-01-01",
        )
        | extra,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_winter_tax_coverage_and_running_cash_agree_everywhere(
    client, db, category_id, monkeypatch
):
    from abacus.advisor import budget_context
    from abacus.schemas import AdvisorIn

    monkeypatch.setattr("abacus.planning.local_today", lambda: date(2026, 11, 11))
    bill = annual_tax(client, category_id)
    # Income exactly covers the budget allocation: two $125 contributions remain.
    client.post(
        "/api/recurring",
        json=dict(
            name="Income",
            kind="receivable",
            frequency="monthly",
            start_month="2026-01",
            amount=12500,
        ),
    )
    client.put("/api/savings", json=dict(amount=50000, month="2026-11", floor=0))
    linked = client.post("/api/planning/annual/" + bill["id"]).json()
    assert (
        client.post("/api/planning/annual/" + bill["id"]).json()["id"] == linked["id"]
    )
    assert db.scalar(select(func.count()).select_from(Plan)) == 1
    row = client.get("/api/planning/" + linked["id"]).json()
    assert row["set_aside"] == 50000
    assert row["monthly_allocation"] == 12500
    assert row["contributions"] == [
        dict(month="2026-11", amount=12500),
        dict(month="2026-12", amount=12500),
    ]
    assert row["projected_contributions"] == 25000
    assert row["projected_funding"] == 75000
    assert row["funding_gap"] == 75000
    assert row["monthly_needed"] == 37500  # extra per contribution, beyond $125
    normal = client.get("/api/forecast?month=2026-12").json()
    assert normal["expenses"] == 12500 and normal["remaining"] == 0
    year = client.get(
        "/api/forecasts?start=2026-01&months=12&include_savings=true"
    ).json()
    assert year[9]["projected_savings"] is None  # no invented historical balances
    assert year[10]["projected_savings"] == 62500
    assert year[11]["projected_savings"] == -75000
    assert year[11]["cash_expenses"] == 150000
    assert year[11]["funding_gap"] == 75000
    overview = client.get("/api/planning?month=2026-12").json()
    assert overview["projection"]["months"][0]["balance"] == -75000
    context = budget_context(
        db,
        AdvisorIn(month="2026-12", message="Can I afford taxes?", plan_id=linked["id"]),
    )
    assert context["selected_plan"]["funding_gap_minor"] == 75000
    assert (
        context["planning_goals"]["projection"]["months"][1]["balance_minor"] == -75000
    )
    # An actual later balance replaces the old one; November is not added twice.
    client.put("/api/savings", json=dict(amount=62500, month="2026-12", floor=0))
    newer = client.get("/api/planning/" + linked["id"]).json()
    assert newer["projected_contributions"] == 12500
    assert newer["projected_funding"] == newer["funding_gap"] == 75000
    assert client.get("/api/savings").json()["amount"] == 62500


def test_funding_gap_does_not_assume_other_budget_room_is_reassigned(
    client, category_id, monkeypatch
):
    monkeypatch.setattr("abacus.planning.local_today", lambda: date(2026, 11, 11))
    bill = annual_tax(client, category_id)
    client.post(
        "/api/recurring",
        json=dict(
            name="Income",
            kind="receivable",
            frequency="monthly",
            start_month="2026-01",
            amount=200000,
        ),
    )
    client.put("/api/savings", json=dict(amount=50000, month="2026-11", floor=0))
    client.post("/api/planning/annual/" + bill["id"])
    december = client.get(
        "/api/forecasts?start=2026-12&months=1&include_savings=true"
    ).json()[0]
    assert december["projected_savings"] == 300000
    assert december["savings_adjusted_deficit"] is False
    assert december["funding_gap"] == 75000


def test_linked_plan_follows_bill_changes_and_can_link_an_existing_goal(
    client, category_id
):
    bill = annual_tax(client, category_id)
    item = goal(client, "Taxes", 100000, "2026-12-31")
    response = client.put(
        "/api/planning/" + item["id"],
        json=dict(
            name="Taxes",
            amount=99999,
            target_date="2026-06-01",
            recurring_id=bill["id"],
        ),
    )
    assert response.status_code == 200
    client.put(
        "/api/recurring/" + bill["id"] + "/amount",
        json=dict(month="2026-01", amount=180000, override=False),
    )
    row = client.get("/api/planning/" + item["id"]).json()
    assert row["amount"] == 180000 and row["target_date"] == "2026-12-31"
    assert client.post("/api/planning/annual/" + bill["id"]).json()["id"] == item["id"]
    client.delete("/api/recurring/" + bill["id"])
    independent = client.get("/api/planning/" + item["id"]).json()
    assert independent["amount"] == 180000 and independent["recurring_id"] is None


def test_overdue_unpaid_bill_does_not_roll_forward_or_project_late_contributions(
    client, category_id, monkeypatch
):
    from abacus.db import Session
    from abacus.models import BillPayment

    monkeypatch.setattr("abacus.planning.local_today", lambda: date(2026, 12, 20))
    bill = annual_tax(client, category_id, due_day=15)
    client.put("/api/savings", json=dict(amount=50000, month="2026-12", floor=0))
    item = client.post("/api/planning/annual/" + bill["id"]).json()
    assert item["target_date"] == "2026-12-15" and item["status"] == "overdue"
    assert item["projected_contributions"] == 0 and item["funding_gap"] == 100000
    with Session() as db:
        db.add(
            BillPayment(
                recurring_id=bill["id"],
                period="2026",
                due_date=date(2026, 12, 15),
                amount=150000,
                paid_on=date(2026, 12, 15),
            )
        )
        db.commit()
    paid = client.get("/api/planning/" + item["id"]).json()
    assert paid["status"] == "paid" and paid["set_aside"] == 0
    assert "funding_gap" not in paid
    assert (
        client.get("/api/planning").json()["annual_expenses"][0]["target_date"]
        == "2027-12-15"
    )


def test_later_annual_cycle_does_not_reuse_this_year_contributions(
    client, category_id, monkeypatch
):
    monkeypatch.setattr("abacus.planning.local_today", lambda: date(2026, 11, 11))
    bill = annual_tax(client, category_id)
    client.put("/api/savings", json=dict(amount=50000, month="2026-11", floor=0))
    goal(client, "Winter 2026", 150000, "2026-12-31", recurring_id=bill["id"])
    later = goal(client, "Winter 2027", 150000, "2027-12-31", recurring_id=bill["id"])
    row = client.get("/api/planning/" + later["id"]).json()
    assert row["projected_contributions"] == 150000
    assert row["contributions"][0]["month"] == "2027-01"
    assert row["set_aside"] == 0 and row["funding_gap"] == 0


def test_linked_deadline_follows_the_bill_and_monthly_conversion_deactivates_it(
    client, db, category_id
):
    from abacus.models import Recurring

    bill = annual_tax(client, category_id)
    item = client.post("/api/planning/annual/" + bill["id"]).json()
    source = db.get(Recurring, bill["id"])
    source.due_month, source.due_day = 11, 30
    db.commit()
    assert (
        client.get("/api/planning/" + item["id"]).json()["target_date"] == "2026-11-30"
    )
    source.frequency = "monthly"
    db.commit()
    row = client.get("/api/planning/" + item["id"]).json()
    assert row["status"] == "inactive" and "funding_gap" not in row


def test_advisor_rejects_a_linked_bill_changed_during_the_answer(
    client, db, category_id, monkeypatch
):
    from abacus.db import Session
    from abacus.models import AmountChange

    bill = annual_tax(client, category_id)
    item = client.post("/api/planning/annual/" + bill["id"]).json()
    settings = db.get(Settings, 1)
    settings.model, settings.advisor_enabled = "local-test", True
    db.commit()

    def answer(*args):
        with Session() as write:
            change = write.scalar(
                select(AmountChange).where(AmountChange.recurring_id == bill["id"])
            )
            change.amount = 180000
            write.commit()
        return "This answer used the old bill."

    monkeypatch.setattr("abacus.advisor.chat_with_model", answer)
    response = client.post(
        "/api/advisor/chat",
        json=dict(month="2026-12", message="Can I fund this?", plan_id=item["id"]),
    )
    assert response.status_code == 409, response.text

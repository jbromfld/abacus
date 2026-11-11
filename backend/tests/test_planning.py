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

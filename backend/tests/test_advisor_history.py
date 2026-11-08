"""Local spending evidence, read-only enforcement, and the web privacy boundary."""

import json
from contextlib import contextmanager
from datetime import date

import pytest
from abacus import research
from abacus.advisor_history import spending_history
from abacus.db import read_only_session
from abacus.models import Category, MonthStatus, Settings, Transaction
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError


def add(
    db,
    account_id,
    category_id,
    day,
    amount,
    description="Panera Bread #600874 k",
    kind="purchase",
):
    db.add(
        Transaction(
            account_id=account_id,
            category_id=category_id,
            date=date.fromisoformat(day),
            amount=amount,
            description=description,
            kind=kind,
            provenance={"original": "DO_NOT_SEND_STATEMENT_PROVENANCE"},
        )
    )


def history(db, month="2026-11"):
    return spending_history(
        db, month, date(2026, 11, 8), db.scalars(select(Category)).all()
    )


def test_exact_local_category_and_payee_differences_refunds_and_payment_exclusion(
    db, account_id, category_id
):
    category_name = db.get(Category, category_id).name
    for day, amount in [
        ("2026-08-03", 10000),
        ("2026-09-03", 15000),
        ("2026-10-03", 22000),
    ]:
        add(
            db,
            account_id,
            category_id,
            day,
            amount,
            description="Panera Bread #600878 k",
        )
    add(db, account_id, category_id, "2026-10-04", 2000, kind="refund")
    add(db, account_id, category_id, "2026-10-05", 900000, kind="payment")
    add(db, account_id, category_id, "2026-10-06", 800000, kind="transfer")
    add(db, account_id, category_id, "2026-11-01", 999999)
    db.commit()
    result = history(db)
    assert result["start_month"] == "2025-11" and result["end_month"] == "2026-10"
    row = next(row for row in result["categories"] if row["category"] == category_name)
    assert row["monthly_net_minor"][-3:] == [10000, 15000, 20000]
    assert [change["change_minor"] for change in row["comparisons"]] == [5000, 10000]
    assert row["comparisons"][0]["from_month"] == "2026-09"
    assert row["comparisons"][0]["partial_month_count"] == 2
    assert len(result["payees"]) == 1
    assert result["payees"][0]["payee"] == "panera bread"
    assert result["payees"][0]["monthly_net_minor"][-3:] == [10000, 15000, 20000]
    assert "DO_NOT_SEND_STATEMENT_PROVENANCE" not in json.dumps(result)
    assert account_id not in json.dumps(result)


def test_missing_month_prevents_claiming_an_increase_and_complete_zero_is_known(
    db, account_id, category_id
):
    add(db, account_id, category_id, "2026-08-03", 10000)
    add(db, account_id, category_id, "2026-10-03", 20000)
    db.commit()
    row = history(db)["payees"][0]
    assert row["monthly_net_minor"][-3:] == [10000, None, 20000]
    assert all(value["change_minor"] is None for value in row["comparisons"])
    assert row["comparisons"][1]["missing_month_count"] == 1
    db.add(MonthStatus(month="2026-09", complete=True))
    db.commit()
    row = history(db)["payees"][0]
    assert row["monthly_net_minor"][-3:] == [10000, 0, 20000]
    assert row["comparisons"][1]["change_minor"] == 10000
    assert row["comparisons"][1]["partial_month_count"] == 2


def test_merchant_selection_is_bounded_and_prioritizes_increases(
    db, account_id, category_id
):
    for number in range(25):
        add(
            db,
            account_id,
            category_id,
            "2026-09-02",
            1000,
            description=f"Store {number}",
        )
        add(
            db,
            account_id,
            category_id,
            "2026-10-02",
            1000 + number,
            description=f"Store {number}",
        )
    db.commit()
    result = history(db)
    assert len(result["payees"]) == 20 and result["additional_payees_omitted"] == 5
    assert result["payees"][0]["payee"] == "store 24"


@pytest.mark.parametrize(
    "selected,end,start",
    [
        ("2024-01", "2024-01", "2023-02"),
        ("2027-01", "2026-10", "2025-11"),
        ("1900-01", "1900-01", "1900-01"),
    ],
)
def test_history_boundaries_exclude_future_and_current_months(db, selected, end, start):
    result = history(db, selected)
    assert result["end_month"] == end and result["start_month"] == start
    assert len(result["months"]) <= 12


def test_advisor_database_transaction_is_enforced_read_only(db):
    original = db.get(Settings, 1).currency
    db.close()
    with contextmanager(read_only_session)() as readonly:
        assert readonly.scalar(text("SHOW transaction_read_only")) == "on"
        assert readonly.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        with pytest.raises(DBAPIError):
            readonly.execute(text("UPDATE settings SET currency='JPY' WHERE id=1"))
    assert db.get(Settings, 1).currency == original


def test_private_history_reaches_only_local_model_and_never_brave(
    client, db, account_id, category_id, monkeypatch
):
    setting = db.get(Settings, 1)
    setting.advisor_enabled = True
    setting.model = "local-test"
    add(
        db,
        account_id,
        category_id,
        "2026-09-02",
        11111,
        description="PRIVATE_PAYEE_CANARY",
    )
    add(
        db,
        account_id,
        category_id,
        "2026-10-02",
        22222,
        description="PRIVATE_PAYEE_CANARY",
    )
    db.commit()
    monkeypatch.setattr("abacus.advisor.local_today", lambda: date(2026, 11, 8))
    monkeypatch.setattr(
        research, "local_config", lambda: {"BRAVE_SEARCH_API_KEY": "synthetic-key"}
    )
    captured_search = []
    captured_model = []

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def get(self, url, **kwargs):
            import httpx

            captured_search.append({"url": url, **kwargs})
            return httpx.Response(
                200, json={"web": {"results": []}}, request=httpx.Request("GET", url)
            )

    monkeypatch.setattr(research.httpx, "Client", Client)

    def model(_model, messages):
        captured_model.extend(messages)
        return "## Savings\n\nReview the recorded increases. Do not search PRIVATE_PAYEE_CANARY."

    monkeypatch.setattr("abacus.advisor.chat_with_model", model)
    topic = "Miami July 2027 weekend"
    plan = research.plan_research(topic, "2026-11-08")
    response = client.post(
        "/api/advisor/chat",
        json={
            "month": "2026-11",
            "message": "My private balance is 7654321. What could I do to increase savings?",
            "history": [{"role": "assistant", "content": "PRIVATE_HISTORY_CANARY"}],
            "use_web": True,
            "research_topic": topic,
            "research_confirmation": research.confirmation_for(plan, topic),
        },
    )
    assert response.status_code == 200, response.text
    assert len(captured_search) == 3
    outbound = json.dumps(captured_search).casefold()
    for private in [
        "private_payee_canary",
        "7654321",
        "11111",
        "22222",
        "private_history_canary",
        "do_not_send_statement_provenance",
        account_id,
    ]:
        assert private not in outbound
    assert [item["params"]["q"] for item in captured_search] == plan.queries
    local = json.dumps(captured_model).casefold()
    assert "private payee canary" in local and "7654321" in local and "11111" in local
    assert "do_not_send_statement_provenance" not in local and account_id not in local
    prompt = json.loads(captured_model[0]["content"].split("BUDGET SNAPSHOT:\n", 1)[1])
    compact = prompt["spending_history"]
    assert compact["comparison_windows"][0]["partial_month_count"] == 2
    assert compact["payees"][0]["comparisons"][0] == {
        "months": 2,
        "change_display": "USD 111.11",
    }
    assert (
        response.json()["context"]["spending_history"]["payees"][0]["comparisons"][0][
            "change_minor"
        ]
        == 11111
    )
    assert len(client.get("/api/transactions").json()) == 2


def test_search_adapter_receives_only_public_request_fields(client, db, monkeypatch):
    setting = db.get(Settings, 1)
    setting.advisor_enabled = True
    setting.model = "local-test"
    db.commit()

    def search(request, _date):
        assert isinstance(request, research.PublicResearchRequest)
        assert set(request.model_dump()) == {
            "use_web",
            "research_topic",
            "research_confirmation",
        }
        assert not hasattr(request, "message") and not hasattr(request, "history")
        return {"status": "disabled"}

    monkeypatch.setattr("abacus.advisor.gather_research", search)
    monkeypatch.setattr(
        "abacus.advisor.chat_with_model", lambda *_: "Read-only local answer"
    )
    response = client.post(
        "/api/advisor/chat",
        json={"month": "2026-11", "message": "Private savings question"},
    )
    assert response.status_code == 200, response.text
    assert "spending_history" in response.json()["context"]


def test_actual_comparison_ignores_forecast_edits_and_excludes_repayments(
    client, db, account_id, category_id, monkeypatch
):
    from abacus.advisor_history import spending_comparison
    from abacus.models import Account

    response = client.post(
        "/api/recurring",
        json={
            "name": "Test card",
            "kind": "payable",
            "frequency": "monthly",
            "amount": 15000,
            "start_month": "2026-01",
            "category_id": category_id,
        },
    )
    assert response.status_code == 201
    for day, amount, kind in [
        ("2026-09-01", 10000, "purchase"),
        ("2026-09-30", 20000, "purchase"),
        ("2026-10-01", 65000, "purchase"),
        ("2026-10-02", 2000, "fee"),
        ("2026-10-03", 7000, "refund"),
        ("2026-10-04", 990000, "payment"),
        ("2026-10-05", 980000, "transfer"),
        ("2026-11-01", 50000, "purchase"),
    ]:
        add(db, account_id, category_id, day, amount, kind=kind)
    db.add_all(
        [
            MonthStatus(month="2026-09", complete=True),
            MonthStatus(month="2026-10", complete=True),
        ]
    )
    db.commit()
    result = spending_comparison(db, history(db))
    expected = {
        "name": db.get(Account, account_id).name,
        "previous_minor": 30000,
        "current_minor": 60000,
        "change_minor": 30000,
    }
    assert result["previous_month"] == "2026-09" and result["month"] == "2026-10"
    assert result["accounts"] == [expected]
    assert result["totals"]["change_minor"] == 30000
    assert account_id not in json.dumps(result)
    assert all(row["average_minor"] is not None for row in history(db)["payees"])
    income = client.post(
        "/api/recurring",
        json={
            "name": "Salary",
            "kind": "receivable",
            "frequency": "monthly",
            "amount": 600000,
            "start_month": "2026-01",
        },
    )
    assert income.status_code == 201
    setting = db.get(Settings, 1)
    setting.advisor_enabled, setting.model = True, "local-test"
    db.commit()
    monkeypatch.setattr("abacus.advisor.local_today", lambda: date(2026, 11, 8))
    captured = []
    from abacus.local_model import ModelReply

    monkeypatch.setattr(
        "abacus.advisor.chat_with_model",
        lambda model, messages: (
            captured.extend(messages)
            or ModelReply("An incomplete sentence", truncated=True)
        ),
    )
    response = client.post(
        "/api/advisor/chat", json={"month": "2026-11", "message": "What changed?"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply_truncated"] is True
    impact = response.json()["context"]["spending_comparison"]["budget_impact"]
    assert impact == [
        {
            "month": "2026-09",
            "planned_income_minor": 600000,
            "actual_spending_minor": 30000,
            "room_after_recorded_spending_minor": 570000,
        },
        {
            "month": "2026-10",
            "planned_income_minor": 600000,
            "actual_spending_minor": 60000,
            "room_after_recorded_spending_minor": 540000,
        },
    ]
    prompt = json.loads(captured[0]["content"].split("BUDGET SNAPSHOT:\n", 1)[1])
    assert (
        prompt["spending_comparison"]["accounts"][0]["change_display"] == "USD 300.00"
    )
    assert (
        prompt["spending_comparison"]["budget_impact"][1]["actual_spending_display"]
        == "USD 600.00"
    )


def test_actual_comparison_missing_zero_and_year_boundary(db, account_id, category_id):
    from abacus.advisor_history import spending_comparison

    add(db, account_id, category_id, "2025-12-31", 27000)
    db.commit()
    categories = db.scalars(select(Category)).all()
    value = spending_history(db, "2026-01", date(2026, 3, 8), categories)
    comparison = spending_comparison(db, value)
    assert comparison["previous_month"] == "2025-12"
    assert comparison["totals"]["current_minor"] is None
    assert comparison["totals"]["change_minor"] is None
    db.add(MonthStatus(month="2026-01", complete=True))
    db.commit()
    value = spending_history(db, "2026-01", date(2026, 3, 8), categories)
    comparison = spending_comparison(db, value)
    assert comparison["totals"]["change_minor"] == -27000
    assert value["payees"][0]["average_minor"] == 13500
    assert value["payees"][0]["sample_count"] == 2

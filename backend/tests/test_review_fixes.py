"""Regression cases for the pre-merge privacy, data-loss, and query-cost review."""

from datetime import date, datetime, timezone

import pytest
from abacus import clock, imports, research
from abacus.budget import actual
from abacus.db import Session, engine
from abacus.models import (
    ImportPage,
    MonthStatus,
    StatementImport,
    Transaction,
)
from abacus.schemas import AdvisorIn
from sqlalchemy import event, func, select


@pytest.mark.parametrize(
    "private",
    [
        "I owe 12000 on my credit card.",
        "SSN 123-45-6789.",
        "My savings balance is 8000.",
        "routing 123 456 789.",
    ],
)
def test_private_chat_never_becomes_a_search(private, monkeypatch):
    monkeypatch.setattr(
        research, "local_config", lambda: {"BRAVE_SEARCH_API_KEY": "test"}
    )
    monkeypatch.setattr(
        research, "search_query", lambda _: pytest.fail("Private chat searched")
    )
    body = AdvisorIn(
        month="2026-11",
        message="Weekend in Miami. " + private,
        use_web=True,
        history=[{"role": "user", "content": private}],
    )
    assert research.gather_research(body, "2026-11-07")["status"] == "needs_details"
    assert not research.plan_research(
        "Weekend in Miami. " + private, "2026-11-07"
    ).queries


def test_search_requires_matching_preview_and_explicit_topic(client, monkeypatch):
    monkeypatch.setattr(
        research, "local_config", lambda: {"BRAVE_SEARCH_API_KEY": "test"}
    )
    sent = []
    monkeypatch.setattr(
        research, "search_query", lambda query: sent.append(query) or []
    )
    topic = " Miami July 2027 weekend "
    preview = client.post("/api/advisor/research-preview", json={"topic": topic}).json()
    body = AdvisorIn(
        month="2026-11",
        message="I owe 12000 on my credit card.",
        use_web=True,
        research_topic=topic,
    )
    assert (
        research.gather_research(body, "2026-11-07")["status"] == "needs_confirmation"
    )
    assert sent == []
    body.research_confirmation = preview["confirmation"]
    assert research.gather_research(body, "2026-11-07")["status"] == "empty"
    assert sent == preview["queries"]
    body.research_topic = "Detroit July 2027 weekend"
    assert (
        research.gather_research(body, "2026-11-07")["status"] == "needs_confirmation"
    )
    assert len(sent) == 3


@pytest.mark.parametrize(
    "value,status",
    [
        ("1899-12-31", 422),
        ("1900-01-01", 201),
        ("9998-12-31", 201),
        ("9999-01-01", 422),
    ],
)
def test_transaction_calendar_bounds(client, account_id, category_id, value, status):
    result = client.post(
        "/api/transactions",
        json={
            "date": value,
            "description": "Synthetic store",
            "amount": 100,
            "kind": "purchase",
            "category_id": category_id,
            "account_id": account_id,
        },
    )
    assert result.status_code == status, result.text


def test_import_dates_follow_same_calendar(client, account_id):
    result = client.post(
        "/api/imports",
        data={"account_id": account_id, "period": "2026-11"},
        files={
            "file": (
                "dates.csv",
                b"Date,Description,Amount\n1899-12-31,Store,1.00\n9999-01-01,Store,2.00\n",
            )
        },
    )
    job = result.json()
    mapped = client.put(
        f"/api/imports/{job['id']}/mapping",
        json={
            "date_column": "Date",
            "description_column": "Description",
            "amount_column": "Amount",
            "date_format": "%Y-%m-%d",
        },
    ).json()
    assert all(row["errors"] for row in mapped["rows"])
    assert client.post(f"/api/imports/{job['id']}/commit").status_code == 422


def pdf_job(db, account_id, category_id, status="processing"):
    row = {
        "date": "2026-11-01",
        "description": "Manually corrected store",
        "amount": 1234,
        "kind": "fee",
        "category_id": category_id,
        "selected": True,
        "source": {"page": 1, "original": "Synthetic page text"},
    }
    job = StatementImport(
        account_id=account_id,
        period="2026-11",
        filename="synthetic.pdf",
        file_hash="synthetic",
        source={"type": "pdf", "pages": [{"page": 1, "text": "Synthetic page text"}]},
        rows=[row],
        status=status,
        processing_token="generation",
    )
    db.add(job)
    db.commit()
    return job


def test_failed_pdf_retry_keeps_manual_review_and_releases_connection(
    db, account_id, category_id, monkeypatch
):
    job = pdf_job(db, account_id, category_id)
    id = job.id
    db.close()
    before = engine.pool.checkedout()

    def unavailable(*_):
        assert engine.pool.checkedout() == before
        raise TimeoutError("Synthetic model timeout")

    monkeypatch.setattr(imports, "ask_model", unavailable)
    imports.process_import(id, "generation")
    with Session() as check:
        saved = check.get(StatementImport, id)
        assert saved.status == "failed" and "timeout" in saved.error
        assert saved.rows[0]["description"] == "Manually corrected store"
        assert (
            saved.rows[0]["kind"] == "fee"
            and saved.rows[0]["category_id"] == category_id
        )
        assert check.scalar(select(func.count()).select_from(Transaction)) == 0


def test_stale_pdf_worker_cannot_replace_newer_review(
    db, account_id, category_id, monkeypatch
):
    job = pdf_job(db, account_id, category_id)
    id = job.id
    db.close()

    def model(*_):
        with Session() as other:
            newer = other.get(StatementImport, id)
            newer.processing_token = "newer"
            newer.rows = [{**newer.rows[0], "description": "Newer review"}]
            other.commit()
        return {
            "rows": [
                {
                    "date": "2026-11-01",
                    "description": "Stale proposal",
                    "amount": 200,
                    "kind": "purchase",
                    "page": 1,
                }
            ]
        }

    monkeypatch.setattr(imports, "ask_model", model)
    imports.process_import(id, "generation")
    with Session() as check:
        assert check.get(StatementImport, id).rows[0]["description"] == "Newer review"


def test_pdf_reextraction_needs_explicit_replacement(
    client, db, account_id, category_id, monkeypatch
):
    job = pdf_job(db, account_id, category_id, status="failed")
    id = job.id
    db.close()
    calls = []
    monkeypatch.setattr(imports.executor, "submit", lambda *args: calls.append(args))
    assert client.post(f"/api/imports/{id}/process").status_code == 409
    assert calls == []
    assert (
        client.post(
            f"/api/imports/{id}/process", json={"replace_review": True}
        ).status_code
        == 200
    )
    assert calls[0][1] == id and calls[0][2]


def test_pdf_provenance_stored_once_and_expanded_on_detail(
    client, db, account_id, category_id
):
    job = pdf_job(db, account_id, category_id, status="review")
    id = job.id
    job.rows = [job.rows[0], {**job.rows[0], "description": "Second store"}]
    db.commit()
    saved = client.post(f"/api/imports/{id}/commit")
    assert saved.status_code == 200, saved.text
    assert saved.json()["rows"][0]["source"]["original"] == "Synthetic page text"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(ImportPage)) == 1
    assert "original" not in db.get(StatementImport, id).rows[0]["source"]
    for transaction in db.scalars(select(Transaction)):
        assert transaction.provenance["source"] == {"page": 1}
        assert "source" not in transaction.provenance["original_review"]
    rows = client.get("/api/transactions").json()
    assert all(row["provenance"] == {} for row in rows)
    details = client.get("/api/transactions/" + rows[0]["id"]).json()
    assert details["provenance"]["source"]["original"] == "Synthetic page text"
    assert client.post(f"/api/imports/{id}/undo").status_code == 200
    assert client.delete(f"/api/imports/{id}").status_code == 200
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(ImportPage)) == 0


def test_trends_constant_query_count_and_no_provenance(client):
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/trends?end=2026-10")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 12
    # Includes one request-scoped read of annual income estimates, not one per month.
    assert len(statements) <= 7
    assert all("provenance" not in statement for statement in statements)


def test_batch_forecasts_match_individual_requests(client, category_id):
    client.post(
        "/api/recurring",
        json={
            "name": "Tax",
            "kind": "payable",
            "frequency": "annual",
            "start_month": "2026-01",
            "amount": 10000,
            "category_id": category_id,
        },
    )
    values = client.get("/api/forecasts?start=2026-01&months=12").json()
    assert len(values) == 12
    assert values == [
        client.get("/api/forecast?month=" + item["month"]).json() for item in values
    ]
    assert client.get("/api/forecasts?start=9998-12&months=2").status_code == 422


@pytest.mark.parametrize("basis", ["actual", "forecast"])
def test_breakdown_range_bound_before_loading_data(client, basis):
    statements = []

    def capture(*args):
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(
            f"/api/expenses/breakdown?start=1900-01-01&end=2099-12-31&basis={basis}"
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 422 and "120" in response.text
    assert statements == []


@pytest.mark.parametrize(
    "utc_now,local_date",
    [
        (datetime(2026, 12, 1, 2, tzinfo=timezone.utc), date(2026, 11, 30)),
        (datetime(2027, 1, 1, 2, tzinfo=timezone.utc), date(2026, 12, 31)),
    ],
)
def test_application_clock_controls_ach_and_completeness(
    client, db, account_id, category_id, monkeypatch, utc_now, local_date
):
    class FixedDateTime:
        @staticmethod
        def now(zone):
            return utc_now.astimezone(zone)

    monkeypatch.setattr(clock, "datetime", FixedDateTime)
    monkeypatch.setattr(
        clock, "local_config", lambda: {"APP_TIMEZONE": "America/Los_Angeles"}
    )
    assert clock.local_today() == local_date
    local_month = local_date.strftime("%Y-%m")
    host_month = utc_now.strftime("%Y-%m")
    db.add(MonthStatus(month=local_month, complete=True))
    db.commit()
    assert actual(db, local_month)["status"] == "partial"
    response = client.post(
        "/api/recurring",
        json={
            "name": "Synthetic ACH",
            "kind": "payable",
            "frequency": "monthly",
            "start_month": host_month,
            "amount": 100,
            "category_id": category_id,
            "ach_enabled": True,
            "ach_day": 1,
            "ach_start_month": host_month,
            "ach_account_id": account_id,
        },
    )
    assert response.status_code == 201, response.text
    assert client.get("/api/transactions").json() == []


def test_pdf_provenance_migration_round_trip(
    db, account_id, category_id, advisor_credentials
):
    """Exercise legacy JSON backfill and restoration, not just an empty schema."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    job = pdf_job(db, account_id, category_id, status="committed")
    source = job.rows[0]["source"]
    transaction = Transaction(
        account_id=account_id,
        category_id=category_id,
        import_id=job.id,
        date=date(2026, 11, 1),
        description="Synthetic legacy PDF",
        amount=1234,
        kind="purchase",
        provenance={
            "source": source,
            "original_review": {"source": source, "description": "Reviewed"},
        },
    )
    db.add(transaction)
    db.commit()
    id = job.id
    transaction_id = transaction.id
    db.close()
    config = Config("alembic.ini")
    try:
        command.downgrade(config, "0011")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            pages = connection.execute(
                text("SELECT number,text FROM import_pages WHERE import_id=:id"),
                {"id": id},
            ).all()
            assert pages == [(1, "Synthetic page text")]
            value = connection.execute(
                text("SELECT provenance FROM transactions WHERE id=:id"),
                {"id": transaction_id},
            ).scalar_one()
            assert value["source"] == {"page": 1}
            assert "source" not in value["original_review"]
        command.downgrade(config, "0011")
        with engine.connect() as connection:
            value = connection.execute(
                text("SELECT provenance FROM transactions WHERE id=:id"),
                {"id": transaction_id},
            ).scalar_one()
            assert value["source"]["original"] == "Synthetic page text"
            assert value["original_review"]["source"] == value["source"]
    finally:
        command.upgrade(config, "head")
        # Later migrations can recreate allowlisted tables. Restore the reader
        # grants just as the production updater does after applying migrations.
        from abacus.advisor_setup import provision_advisor

        provision_advisor(engine.url, advisor_credentials[0], advisor_credentials[1])

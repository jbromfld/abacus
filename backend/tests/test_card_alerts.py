from datetime import UTC, date, datetime

import pytest
from abacus.models import StatementImport

TODAY = date(2026, 11, 6)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("abacus.card_alerts.local_today", lambda: TODAY)


def monitor(client, account, enabled=True):
    response = client.patch(
        "/api/accounts/" + account + "/monitoring",
        json={"stale_alert_enabled": enabled},
    )
    assert response.status_code == 200, response.text
    return response.json()


def card(client, account):
    return next(a for a in client.get("/api/accounts").json() if a["id"] == account)


def record(client, account, category, day):
    response = client.post(
        "/api/transactions",
        json=dict(
            date=day,
            description="Card activity",
            amount=1000,
            kind="purchase",
            category_id=category,
            account_id=account,
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()


def statement(db, account, period, status="committed", uploaded=None):
    from uuid import uuid4

    job = StatementImport(
        account_id=account,
        period=period,
        status=status,
        file_hash=uuid4().hex,
        filename="test.csv",
        source={"type": "csv"},
        rows=[],
        created_at=uploaded or datetime(2026, 11, 6, 17, tzinfo=UTC),
    )
    db.add(job)
    db.commit()
    return job


def test_monitoring_opt_in_and_missing_information(client, account_id):
    initial = card(client, account_id)
    assert initial["stale_alert_enabled"] is False and initial["stale"] is False
    assert initial["last_information_date"] is None
    enabled = monitor(client, account_id)
    assert enabled["stale"] is True and enabled["days_since_update"] is None
    assert monitor(client, account_id, False)["stale"] is False
    assert client.get("/api/accounts").status_code == 200


@pytest.mark.parametrize(
    "day,age,stale",
    [
        ("2026-11-06", 0, False),
        ("2026-10-07", 30, False),
        ("2026-10-06", 31, True),
        ("2025-01-01", 674, True),
    ],
)
def test_strict_thirty_day_boundary(client, account_id, category_id, day, age, stale):
    record(client, account_id, category_id, day)
    status = monitor(client, account_id)
    assert status["last_information_date"] == day
    assert status["days_since_update"] == age and status["stale"] is stale


def test_current_statement_refreshes_coverage_without_recent_spending(
    client, account_id, category_id, db
):
    record(client, account_id, category_id, "2026-09-01")
    statement(db, account_id, "2026-10")
    status = monitor(client, account_id)
    assert status["last_information_date"] == "2026-10-31"
    assert status["days_since_update"] == 6 and not status["stale"]
    # Current-month statement evidence is capped at its upload date, not a future month end.
    statement(db, account_id, "2026-11", uploaded=datetime(2026, 11, 3, 17, tzinfo=UTC))
    assert card(client, account_id)["last_information_date"] == "2026-11-03"


def test_old_statement_uploaded_now_does_not_hide_staleness(client, account_id, db):
    statement(db, account_id, "2026-09")
    status = monitor(client, account_id)
    assert status["last_information_date"] == "2026-09-30"
    assert status["days_since_update"] == 37 and status["stale"]


@pytest.mark.parametrize(
    "status", ["prepared", "processing", "review", "failed", "interrupted", "undone"]
)
def test_uncommitted_or_undone_imports_do_not_refresh_information(
    client, account_id, category_id, db, status
):
    record(client, account_id, category_id, "2026-10-01")
    statement(db, account_id, "2026-11", status=status)
    result = monitor(client, account_id)
    assert result["last_information_date"] == "2026-10-01" and result["stale"]


def test_future_records_and_future_statement_periods_do_not_clear_alert(
    client, account_id, category_id, db
):
    record(client, account_id, category_id, "2026-12-01")
    statement(db, account_id, "2026-12")
    status = monitor(client, account_id)
    assert status["last_information_date"] is None and status["stale"]


def test_committed_import_undo_restores_stale_state(
    client, account_id, category_id, db
):
    record(client, account_id, category_id, "2026-09-01")
    job = statement(db, account_id, "2026-10")
    assert not monitor(client, account_id)["stale"]
    assert client.post("/api/imports/" + job.id + "/undo").status_code == 200
    assert card(client, account_id)["stale"]


def test_card_preferences_independent_and_name_edit_preserves_monitoring(
    client, account_id
):
    other = client.post("/api/accounts", json={"name": "Unmonitored card"}).json()["id"]
    monitor(client, account_id)
    assert (
        client.put(
            "/api/accounts/" + account_id, json={"name": "Renamed card"}
        ).status_code
        == 200
    )
    first = card(client, account_id)
    assert (
        first["stale_alert_enabled"]
        and first["stale"]
        and first["name"] == "Renamed card"
    )
    assert not card(client, other)["stale"]
    assert (
        client.put(
            "/api/accounts/" + account_id,
            json={"name": "Renamed card", "stale_alert_enabled": False},
        ).status_code
        == 200
    )
    assert not card(client, account_id)["stale"]


def test_timezone_controls_upload_date_without_future_coverage(client, account_id, db):
    # 01:00 UTC Nov 6 is still Nov 5 in Detroit.
    statement(db, account_id, "2026-11", uploaded=datetime(2026, 11, 6, 1, tzinfo=UTC))
    status = monitor(client, account_id)
    assert (
        status["last_information_date"] == "2026-11-05"
        and status["days_since_update"] == 1
    )


def test_invalid_monitoring_requests(client):
    assert (
        client.patch(
            "/api/accounts/missing/monitoring", json={"stale_alert_enabled": True}
        ).status_code
        == 404
    )
    assert client.patch("/api/accounts/missing/monitoring", json={}).status_code == 422

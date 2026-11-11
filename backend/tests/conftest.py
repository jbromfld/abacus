import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, update

# Deliberately refuse to run against a personal/development budget database.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost/abacus_test"
)
from abacus.db import Session, engine
from abacus.main import app
from abacus.models import (
    Account,
    AlertDismissal,
    AmountChange,
    AnnualIncome,
    Category,
    ImportPage,
    MemoryDream,
    MonthStatus,
    PayeeGroup,
    PayeeReview,
    PayeeRule,
    Plan,
    PlanCategory,
    Recurring,
    Settings,
    StatementImport,
    Transaction,
)
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def advisor_credentials():
    from abacus.advisor_setup import provision_advisor
    from abacus.db import dispose_advisor_engine
    from psycopg import sql

    if not engine.url.database or not engine.url.database.startswith("abacus_test"):
        pytest.fail("Disposable advisor roles require an abacus_test database.")
    role = "abacus_test_advisor_" + uuid4().hex[:12]
    password = provision_advisor(engine.url, role)
    try:
        yield role, password
    finally:
        dispose_advisor_engine()
        with engine.begin() as connection:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.fixture(autouse=True)
def clean_database(monkeypatch, tmp_path, advisor_credentials):
    from abacus import dreaming

    dreaming.start()
    from abacus import config

    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "isolated.env")
    monkeypatch.setenv("ADVISOR_USER", advisor_credentials[0])
    monkeypatch.setenv("ADVISOR_PASS", advisor_credentials[1])
    if not engine.url.database or not engine.url.database.startswith("abacus_test"):
        pytest.fail(
            "TEST_DATABASE_URL database must start with abacus_test; tests delete its app data."
        )
    with Session() as db:
        for model in [
            MemoryDream,
            Plan,
            AnnualIncome,
            AlertDismissal,
            ImportPage,
            PayeeRule,
            PayeeGroup,
            PayeeReview,
            Transaction,
            StatementImport,
            AmountChange,
            Recurring,
            Account,
            MonthStatus,
        ]:
            db.execute(delete(model))
        setting = db.get(Settings, 1)
        setting.model, setting.currency, setting.advisor_enabled = "", "USD", False
        setting.advisor_dreaming_enabled = False
        setting.advisor_memory_enabled = False
        setting.savings_balance, setting.savings_month, setting.savings_floor = (
            None,
            None,
            0,
        )
        db.execute(update(Category).values(monthly_guide=None))
        # Custom planning categories are isolated, while migration defaults persist.
        db.execute(
            delete(PlanCategory).where(
                PlanCategory.id.not_in(["tax", "vacation", "purchase"])
            )
        )
        db.commit()
    yield


@pytest.fixture
def db():
    with Session() as s:
        yield s


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def category_id(db):
    from sqlalchemy import select

    return db.scalar(select(Category.id).where(Category.name == "Groceries"))


@pytest.fixture
def account_id(client):
    response = client.post("/api/accounts", json={"name": "Test card"})
    assert response.status_code == 201
    return response.json()["id"]

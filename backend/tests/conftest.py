import os
import pytest
from sqlalchemy import delete, update

# Deliberately refuse to run against a personal/development budget database.
os.environ['DATABASE_URL'] = os.environ.get('TEST_DATABASE_URL', 'postgresql+psycopg://localhost/abacus_test')
from abacus.db import engine, Session
from abacus.models import Transaction, StatementImport, AmountChange, Recurring, Purchase, Account, MonthStatus, Settings, Category, PayeeRule, BillEstimate, ReservePlan, SavingsObservation
from abacus.main import app
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def clean_database(monkeypatch, tmp_path):
    from abacus import config
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "isolated.env")
    if not engine.url.database or not engine.url.database.startswith('abacus_test'):
        pytest.fail('TEST_DATABASE_URL database must start with abacus_test; tests delete its app data.')
    with Session() as db:
        for model in [ReservePlan, SavingsObservation, BillEstimate, PayeeRule, Transaction, StatementImport, AmountChange, Recurring, Purchase, Account, MonthStatus]:
            db.execute(delete(model))
        setting = db.get(Settings, 1)
        setting.model, setting.currency, setting.advisor_enabled = '', 'USD', False
        setting.reserve_alerts_enabled, setting.reserve_checkpoint_day = True, 1
        setting.savings_balance, setting.savings_month, setting.savings_floor = None, None, 0
        db.execute(update(Category).values(monthly_guide=None))
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
    return db.scalar(select(Category.id).where(Category.name == 'Groceries'))

@pytest.fixture
def account_id(client):
    response = client.post('/api/accounts', json={'name':'Test card'})
    assert response.status_code == 201
    return response.json()['id']

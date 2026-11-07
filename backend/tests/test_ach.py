from datetime import date
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from abacus.ach import record_due
from abacus.db import Session
from abacus.models import RecurringDebit, Transaction


@pytest.fixture
def clock(monkeypatch):
    value = [date(2026, 1, 10)]
    monkeypatch.setattr('abacus.ach.today_local', lambda: value[0])
    return value


def bill(client, account_id, category_id, **overrides):
    data = dict(name='Internet ACH', kind='payable', frequency='monthly',
        category_id=category_id, amount=5000, start_month='2025-01',
        ach_enabled=True, ach_day=15, ach_start_month='2026-01', ach_account_id=account_id)
    data.update(overrides)
    result = client.post('/api/recurring', json=data)
    assert result.status_code == 201, result.text
    return result.json()


def test_due_date_actuals_and_independent_forecast(client, account_id, category_id, clock):
    bill(client, account_id, category_id)
    assert client.get('/api/transactions').json() == []
    assert client.get('/api/forecast?month=2026-01').json()['expenses'] == 5000
    clock[0] = date(2026, 1, 15)
    assert client.post('/api/recurring/record-due').json() == {'added': 1}
    assert client.post('/api/recurring/record-due').json() == {'added': 0}
    rows = client.get('/api/transactions').json()
    assert len(rows) == 1
    assert rows[0]['kind'] == 'purchase' and rows[0]['amount'] == 5000
    assert rows[0]['date'] == '2026-01-15'
    assert rows[0]['provenance']['type'] == 'scheduled_ach'
    assert rows[0]['account_id'] == account_id and rows[0]['category_id'] == category_id
    forecast = client.get('/api/forecast?month=2026-01').json()
    assert forecast['expenses'] == 5000 and forecast['actual']['expenses'] == 5000
    trend = client.get('/api/trends?end=2026-01').json()[-1]
    assert trend['actual'] == 5000 and trend['categories'][category_id]['actual'] == 5000


def test_catch_up_start_end_and_short_months(client, account_id, category_id, clock):
    clock[0] = date(2024, 1, 1)
    bill(client, account_id, category_id, start_month='2023-01', ach_start_month='2024-02',
         ach_day=31, end_month='2024-03')
    clock[0] = date(2024, 2, 28)
    assert client.post('/api/recurring/record-due').json()['added'] == 0
    clock[0] = date(2024, 4, 30)
    assert client.post('/api/recurring/record-due').json()['added'] == 2
    assert sorted(r['date'] for r in client.get('/api/transactions').json()) == ['2024-02-29', '2024-03-31']


def test_effective_amounts_overrides_and_already_posted_edits(client, account_id, category_id, clock):
    item = bill(client, account_id, category_id)
    for month, amount, override in [('2026-02', 6000, False), ('2026-03', 7000, True)]:
        assert client.put('/api/recurring/'+item['id']+'/amount', json=dict(month=month, amount=amount, override=override)).status_code == 200
    clock[0] = date(2026, 4, 16)
    assert client.post('/api/recurring/record-due').json()['added'] == 4
    rows = client.get('/api/transactions').json()
    assert {r['date'][5:7]:r['amount'] for r in rows} == {'01':5000, '02':6000, '03':7000, '04':6000}
    original = rows[-1]
    assert client.put('/api/transactions/'+original['id'], json={**original, 'amount':4500}).status_code == 200
    client.put('/api/recurring/'+item['id']+'/amount', json=dict(month='2026-01', amount=9999))
    assert client.post('/api/recurring/record-due').json()['added'] == 0
    assert next(r for r in client.get('/api/transactions').json() if r['id']==original['id'])['amount'] == 4500


def test_deleted_actual_is_not_recreated_and_delete_schedule_keeps_actuals(client, account_id, category_id, clock, db):
    clock[0] = date(2026, 1, 20)
    item = bill(client, account_id, category_id)
    txn = client.get('/api/transactions').json()[0]
    assert client.delete('/api/transactions/'+txn['id']).status_code == 200
    assert client.post('/api/recurring/record-due').json()['added'] == 0
    occurrence = db.scalar(select(RecurringDebit))
    assert occurrence.transaction_id is None
    clock[0] = date(2026, 2, 20)
    assert client.post('/api/recurring/record-due').json()['added'] == 1
    assert client.delete('/api/recurring/'+item['id']).status_code == 200
    assert len(client.get('/api/transactions').json()) == 1


def test_disable_and_reenable_do_not_duplicate(client, account_id, category_id, clock):
    clock[0] = date(2026, 1, 20)
    item = bill(client, account_id, category_id)
    assert client.put('/api/recurring/'+item['id'], json={**item, 'ach_enabled':False}).status_code == 200
    clock[0] = date(2026, 2, 20)
    assert client.post('/api/recurring/record-due').json()['added'] == 0
    assert len(client.get('/api/transactions').json()) == 1
    assert client.put('/api/recurring/'+item['id'], json={**item, 'ach_enabled':True}).status_code == 200
    assert len(client.get('/api/transactions').json()) == 2


@pytest.mark.parametrize('overrides', [
    {'ach_day':0}, {'ach_day':32}, {'ach_day':None}, {'ach_account_id':None},
    {'ach_start_month':None}, {'frequency':'annual'}, {'kind':'receivable'},
])
def test_invalid_ach_configuration(client, account_id, category_id, overrides):
    data = dict(name='Invalid', kind='payable', frequency='monthly', category_id=category_id,
        amount=5000, start_month='2026-01', ach_enabled=True, ach_day=15,
        ach_start_month='2026-01', ach_account_id=account_id)
    assert client.post('/api/recurring', json={**data, **overrides}).status_code == 422
    assert client.get('/api/transactions').json() == []


def test_default_schedules_do_not_record_and_missing_account_rejected(client, account_id, category_id, clock):
    bill(client, account_id, category_id, ach_enabled=False)
    clock[0] = date(2026, 2, 20)
    assert client.post('/api/recurring/record-due').json()['added'] == 0
    data = dict(name='No account', kind='payable', frequency='monthly', category_id=category_id,
        amount=100, start_month='2026-01', ach_enabled=True, ach_day=1,
        ach_start_month='2026-01', ach_account_id='missing')
    assert client.post('/api/recurring', json=data).status_code == 404


def test_concurrent_passes_record_once(client, account_id, category_id, clock, db):
    bill(client, account_id, category_id)
    def run():
        with Session() as session:
            return record_due(session, date(2026, 1, 20))
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sum(workers.map(lambda _:run(), range(2))) == 1
    assert db.scalar(select(func.count()).select_from(Transaction)) == 1
    assert db.scalar(select(func.count()).select_from(RecurringDebit)) == 1


def test_restart_records_missed_due_dates(client, account_id, category_id, clock):
    from fastapi.testclient import TestClient
    from abacus.main import app
    bill(client, account_id, category_id)
    clock[0] = date(2026, 3, 20)
    with TestClient(app) as restarted:
        rows = restarted.get('/api/transactions').json()
        assert len(rows) == 3
        assert restarted.post('/api/recurring/record-due').json()['added'] == 0

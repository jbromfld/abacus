from datetime import date
import pytest
from sqlalchemy import select,func
from abacus.models import ReservePlan,SavingsObservation,Transaction,BillPayment,Settings


def today(monkeypatch,value):
    monkeypatch.setattr('abacus.reserves.local_today',lambda:date.fromisoformat(value))
    monkeypatch.setattr('abacus.main.local_today',lambda:date.fromisoformat(value))


def bill(client,category_id,name='Winter tax',amount=150000,**extra):
    response=client.post('/api/recurring',json=dict(name=name,kind='payable',frequency='annual',
        start_month='2026-11',amount=amount,category_id=category_id,distribute_annual=True,due_month=12,due_day=1,**extra))
    assert response.status_code==201,response.text
    return response.json()


def plan(client,amount=50000,month='2026-11'):
    response=client.put('/api/reserve-check/plan',json={'amount':amount,'month':month})
    assert response.status_code==200,response.text
    return response.json()


def record(client,amount,as_of):
    response=client.post('/api/reserve-check/balances',json={'amount':amount,'as_of':as_of})
    assert response.status_code==200,response.text
    return response.json()


def test_manual_balance_drift_has_fixed_target_excludes_surplus_and_never_writes_spending(client,category_id,db,monkeypatch):
    today(monkeypatch,'2026-11-07')
    bill(client,category_id)
    client.post('/api/recurring',json=dict(name='Summer tax',kind='payable',frequency='annual',start_month='2026-11',amount=800000,category_id=category_id,distribute_annual=True,due_month=7,due_day=1))
    client.post('/api/recurring',json=dict(name='Income',kind='receivable',frequency='monthly',start_month='2026-11',amount=600000))
    client.post('/api/recurring',json=dict(name='Other expenses',kind='payable',frequency='monthly',start_month='2026-11',amount=515200,category_id=category_id))
    client.put('/api/savings',json={'amount':50000,'month':'2026-11'})
    result=plan(client)
    assert result['next_checkpoint']=='2026-12-01' and result['next_target']==129167
    assert result['checkpoints'][0]['allocation']==79167
    assert result['status']=='payment_risk' # 1291.67 does not cover a 1500 payment due at this checkpoint.
    assert result['upcoming'][0]['shortfall']==20833
    assert result['upcoming'][0]['assumes_future_allocations']
    frozen=db.get(ReservePlan,1).schedules
    today(monkeypatch,'2026-12-01')
    result=client.get('/api/reserve-check').json()
    assert result['status']=='needs_update' and result['shortfall'] is None
    assert result['checkpoint']=='2026-12-01' and result['target']==129167
    result=record(client,100000,'2026-12-01')
    assert result['status']=='below_target' and result['shortfall']==29167
    assert db.get(ReservePlan,1).amount==50000 and db.get(ReservePlan,1).schedules==frozen
    assert client.get('/api/savings').json()['amount']==50000
    result=record(client,129167,'2026-12-01')
    assert result['shortfall']==0 and result['status']=='payment_risk'
    assert result['upcoming'][0]['shortfall']==20833
    assert db.scalar(select(func.count()).select_from(Transaction))==0
    assert db.scalar(select(func.count()).select_from(BillPayment))==0
    # No observation or plan is written by simply reading alerts.
    before=db.scalar(select(func.count()).select_from(SavingsObservation))
    client.get('/api/reserve-check')
    assert db.scalar(select(func.count()).select_from(SavingsObservation))==before


def test_saving_projection_snapshot_records_balance_without_resetting_reserve_plan(client,category_id,db,monkeypatch):
    today(monkeypatch,'2026-12-01');bill(client,category_id);plan(client)
    client.put('/api/savings',json={'amount':10000,'month':'2026-12','floor':500})
    result=client.get('/api/reserve-check').json()
    assert result['latest']=={'amount':10000,'as_of':'2026-12-01'}
    assert result['target']==62500 and result['shortfall']==52500
    assert db.get(ReservePlan,1).amount==50000
    # A hypothetical future opening balance is not an actual observation.
    client.put('/api/savings',json={'amount':90000,'month':'2027-01'})
    assert client.get('/api/reserve-check').json()['latest']['amount']==10000


def test_checkpoint_clamping_leap_year_and_payments_before_asof(client,category_id,monkeypatch):
    today(monkeypatch,'2028-01-01')
    client.post('/api/recurring',json=dict(name='Tax',kind='payable',frequency='annual',start_month='2028-01',amount=120000,category_id=category_id,distribute_annual=True,due_month=2,due_day=29))
    client.put('/api/settings',json={'reserve_checkpoint_day':31})
    record(client,200000,'2028-01-01');result=plan(client,200000,'2028-01')
    assert result['next_checkpoint']=='2028-02-29' and result['next_target']==210000
    today(monkeypatch,'2028-02-29');result=record(client,210000,'2028-02-29')
    assert result['status']=='on_track' and result['target']==210000
    assert result['upcoming'][0]['due_date']=='2028-02-29'
    today(monkeypatch,'2028-03-01');result=record(client,90000,'2028-03-01')
    assert result['target']==90000 and result['shortfall']==0 # scheduled payment deducted after its due day
    assert result['next_checkpoint']=='2028-03-31'
    assert result['next_target']==100000


def test_due_window_is_inclusive_and_multiple_same_day_bills_share_available_funds(client,category_id,monkeypatch):
    today(monkeypatch,'2026-11-01')
    bill(client,category_id,name='Tax one',amount=120000)
    bill(client,category_id,name='Tax two',amount=120000)
    record(client,100000,'2026-11-01');result=plan(client,100000)
    assert len(result['upcoming'])==1 and len(result['upcoming'][0]['bills'])==2
    assert result['upcoming'][0]['amount']==240000
    assert result['upcoming'][0]['projected_before_payment']==120000
    assert result['upcoming'][0]['shortfall']==120000
    assert result['status']=='payment_risk'


def test_schedule_changes_require_explicit_replacement_and_keep_original_baseline(client,category_id,db,monkeypatch):
    today(monkeypatch,'2026-11-07');item=bill(client,category_id);record(client,50000,'2026-11-01')
    result=plan(client);assert result['next_target']==62500
    client.put('/api/recurring/'+item['id']+'/amount',json={'month':'2026-11','amount':240000})
    result=client.get('/api/reserve-check').json()
    assert result['plan']['schedule_changed'] and result['next_target']==62500
    result=plan(client)
    assert not result['plan']['schedule_changed'] and result['next_target']==70000
    record(client,12300,'2026-11-07');db.expire_all()
    assert db.get(ReservePlan,1).amount==50000


def test_dismissal_reappears_next_checkpoint_balance_updates_clear_it_settings_preserved(client,category_id,monkeypatch):
    today(monkeypatch,'2026-12-01');bill(client,category_id);plan(client)
    result=client.post('/api/reserve-check/dismiss').json()
    assert result['dismissed'] and result['plan']['dismissed_until']=='2027-01-01'
    today(monkeypatch,'2027-01-01');result=client.get('/api/reserve-check').json()
    assert not result['dismissed'] and result['status']=='needs_update'
    client.post('/api/reserve-check/dismiss')
    result=record(client,90000,'2027-01-01')
    assert not result['dismissed']
    client.put('/api/settings',json={'reserve_alerts_enabled':False,'reserve_checkpoint_day':15})
    assert not client.get('/api/reserve-check').json()['enabled']
    assert client.get('/api/settings').json()['reserve_checkpoint_day']==15
    client.put('/api/settings',json={'currency':'USD','model':'','advisor_enabled':False})
    assert not client.get('/api/reserve-check').json()['enabled']


def test_observation_corrections_history_and_freshness_without_mistaking_missing_for_zero(client,category_id,db,monkeypatch):
    today(monkeypatch,'2026-11-07');bill(client,category_id);result=plan(client)
    assert result['status']=='needs_update' and result['latest'] is None
    record(client,40000,'2026-11-01');record(client,50000,'2026-11-01')
    assert db.scalar(select(func.count()).select_from(SavingsObservation))==1
    assert client.get('/api/reserve-check').json()['status']=='payment_risk'
    today(monkeypatch,'2026-12-01')
    assert client.get('/api/reserve-check').json()['status']=='needs_update'
    result=record(client,0,'2026-12-01')
    assert result['status']=='below_target' and result['latest']['amount']==0
    assert len(result['observations'])==2


def test_only_dated_distributed_active_payables_contribute_and_effective_changes_are_frozen(client,category_id,monkeypatch):
    today(monkeypatch,'2026-11-07')
    item=bill(client,category_id)
    client.put('/api/recurring/'+item['id']+'/amount',json={'month':'2026-12','amount':240000})
    client.post('/api/recurring',json=dict(name='Undated allowance',kind='payable',frequency='annual',start_month='2026-11',amount=120000,category_id=category_id))
    client.post('/api/recurring',json=dict(name='Lump sum',kind='payable',frequency='annual',start_month='2026-11',amount=120000,category_id=category_id,distribute_annual=False,due_month=12,due_day=15))
    result=plan(client)
    assert result['eligible_bill_count']==1
    assert result['checkpoints'][0]['allocation']==12500
    assert result['checkpoints'][1]['allocation']==20000
    assert result['checkpoints'][1]['payments_to_date']==240000


def test_currency_lock_covers_reserve_records(client,category_id,monkeypatch):
    today(monkeypatch,'2026-11-07');record(client,50000,'2026-11-01')
    assert client.put('/api/settings',json={'currency':'EUR'}).status_code==409


@pytest.mark.parametrize('endpoint,data',[
    ('/api/reserve-check/plan',{'amount':-1,'month':'2026-11'}),
    ('/api/reserve-check/plan',{'amount':0,'month':'2027-01'}),
    ('/api/reserve-check/balances',{'amount':-1,'as_of':'2026-11-01'}),
    ('/api/reserve-check/balances',{'amount':10.5,'as_of':'2026-11-01'}),
    ('/api/reserve-check/balances',{'amount':100,'as_of':'2026-11-08'}),
])
def test_reserve_input_validation(client,monkeypatch,endpoint,data):
    today(monkeypatch,'2026-11-07')
    response=client.put(endpoint,json=data) if endpoint.endswith('plan') else client.post(endpoint,json=data)
    assert response.status_code==422,response.text


def test_missing_plan_and_no_bills_are_clear(client,monkeypatch):
    today(monkeypatch,'2026-11-07')
    assert client.get('/api/reserve-check').json()['status']=='no_bills'
    assert client.put('/api/reserve-check/plan',json={'amount':0,'month':'2026-11'}).status_code==422
    assert client.post('/api/reserve-check/dismiss').status_code==404
    assert client.put('/api/settings',json={'reserve_checkpoint_day':32}).status_code==422

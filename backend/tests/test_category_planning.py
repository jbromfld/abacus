from datetime import date
import json
import pytest
from sqlalchemy import select,func
from abacus.models import Category,Transaction,Recurring,Settings


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr('abacus.category_planning.local_today',lambda:date(2026,11,7))


def transaction(client,account_id,category_id,day,amount,kind='purchase'):
    response=client.post('/api/transactions',json=dict(date=day,amount=amount,kind=kind,
        description='Synthetic category spending',category_id=category_id if kind not in ('payment','transfer') else None,account_id=account_id))
    assert response.status_code==201,response.text


def test_recorded_month_means_include_zeros_and_flag_partial_data(client,category_id,account_id,db,clock):
    other=db.scalar(select(Category.id).where(Category.id!=category_id))
    transaction(client,account_id,category_id,'2026-01-02',10000)
    transaction(client,account_id,other,'2026-01-03',5000)
    transaction(client,account_id,category_id,'2026-02-02',30000)
    transaction(client,account_id,category_id,'2026-02-03',5000,'refund')
    transaction(client,account_id,category_id,'2026-02-04',99999,'payment')
    transaction(client,account_id,category_id,'2026-02-05',99999,'transfer')
    client.put('/api/months/2026-03',json={'complete':True})
    client.put('/api/months/2026-04',json={'complete':False})
    transaction(client,account_id,category_id,'2026-11-02',900000)
    transaction(client,account_id,category_id,'2026-12-02',900000)
    client.put('/api/months/2026-11',json={'complete':True})
    response=client.get('/api/spending/averages?end=2026-12')
    assert response.status_code==200,response.text
    result=response.json()
    assert result['included_months']==['2026-01','2026-02','2026-03']
    assert result['sample_count']==3 and result['partial_month_count']==2
    assert result['average']==13333
    entry=next(c for c in result['categories'] if c['id']==category_id)
    assert entry['average']==11667 and entry['suggested_guide']==11667
    selected=client.get('/api/spending/averages?end=2026-12&category_ids='+other).json()
    assert selected['average']==1667
    assert selected['window_start']=='2026-01' and selected['window_end']=='2026-12'


def test_missing_data_is_not_zero_and_explicit_complete_zero_counts(client,category_id,clock):
    result=client.get('/api/spending/averages?end=2026-10').json()
    assert result['average'] is None and result['sample_count']==0
    assert all(c['suggested_guide'] is None for c in result['categories'])
    client.put('/api/months/2026-10',json={'complete':True})
    result=client.get('/api/spending/averages?end=2026-10').json()
    assert result['average']==0 and result['sample_count']==1
    assert result['partial_month_count']==0


def test_refunds_negative_mean_suggests_zero_and_fees_count(client,category_id,account_id,clock):
    transaction(client,account_id,category_id,'2026-10-01',10000,'refund')
    transaction(client,account_id,category_id,'2026-10-02',1500,'fee')
    result=client.get('/api/spending/averages?end=2026-10').json()
    row=next(c for c in result['categories'] if c['id']==category_id)
    assert row['average']==-8500 and row['suggested_guide']==0


def test_minor_unit_means_round_half_up(client,category_id,account_id,clock):
    transaction(client,account_id,category_id,'2026-09-01',1)
    transaction(client,account_id,category_id,'2026-10-01',2)
    result=client.get('/api/spending/averages?end=2026-10').json()
    assert result['average']==2 and result['sample_count']==2


def test_category_guides_persist_but_never_change_budget_or_savings(client,category_id,db,clock):
    for kind,amount in [('receivable',100000),('payable',65000)]:
        client.post('/api/recurring',json=dict(name=kind,kind=kind,frequency='monthly',amount=amount,start_month='2026-01',category_id=category_id))
    before=client.get('/api/forecast?month=2026-11').json()
    payload={'savings':{'amount':500000,'month':'2026-11'},'bill':{'amount':20000,'start_month':'2026-11'}}
    cash=client.post('/api/savings/projection',json=payload).json()
    result=client.patch('/api/categories/'+category_id+'/guide',json={'monthly_guide':25000})
    assert result.status_code==200,result.text
    assert result.json()['monthly_guide']==25000
    entry=next(c for c in client.get('/api/spending/averages?end=2026-10').json()['categories'] if c['id']==category_id)
    assert entry['monthly_guide']==25000
    assert client.get('/api/forecast?month=2026-11').json()==before
    assert client.post('/api/savings/projection',json=payload).json()==cash
    assert db.scalar(select(func.count()).select_from(Transaction))==0
    assert db.scalar(select(func.count()).select_from(Recurring))==2
    client.patch('/api/categories/'+category_id+'/guide',json={'monthly_guide':None})
    assert db.get(Category,category_id).monthly_guide is None


@pytest.mark.parametrize('value',[-1,1.5,9000000000001,'100'])
def test_invalid_guide_amounts_are_rejected(client,category_id,value):
    assert client.patch('/api/categories/'+category_id+'/guide',json={'monthly_guide':value}).status_code==422


def test_zero_guide_locks_currency_until_cleared_and_rename_preserves_guide(client,category_id):
    assert client.patch('/api/categories/'+category_id+'/guide',json={'monthly_guide':0}).status_code==200
    assert client.put('/api/settings',json={'currency':'EUR','model':'','advisor_enabled':False}).status_code==409
    client.patch('/api/categories/'+category_id+'/guide',json={'monthly_guide':None})
    assert client.put('/api/settings',json={'currency':'EUR','model':'','advisor_enabled':False}).status_code==200
    item=client.post('/api/categories',json={'name':'Guide rename test'}).json()
    client.patch('/api/categories/'+item['id']+'/guide',json={'monthly_guide':100})
    renamed=client.put('/api/categories/'+item['id'],json={'name':'Guide renamed'}).json()
    assert renamed['monthly_guide']==100
    assert client.delete('/api/categories/'+item['id']).status_code==200


def test_average_window_boundaries_and_unknown_category(client,clock):
    assert client.get('/api/spending/averages?end=1900-01').status_code==422
    assert client.get('/api/spending/averages?end=9998-12').status_code==200
    assert client.get('/api/spending/averages?end=2026-10&category_ids=missing').status_code==404
    assert client.patch('/api/categories/missing/guide',json={'monthly_guide':100}).status_code==404


def test_advisor_treats_guides_as_information_not_added_expenses(client,category_id,account_id,db,clock,monkeypatch):
    transaction(client,account_id,category_id,'2026-10-01',10000)
    client.patch('/api/categories/'+category_id+'/guide',json={'monthly_guide':25000})
    setting=db.get(Settings,1);setting.model='local-test';setting.advisor_enabled=True;db.commit()
    captured=[]
    monkeypatch.setattr('abacus.advisor.chat_with_model',lambda model,messages:captured.append(messages) or 'Guides are references only.')
    response=client.post('/api/advisor/chat',json={'month':'2026-11','message':'What is my category guide?'})
    assert response.status_code==200,response.text
    context=response.json()['context']
    assert context['rules']['category_guides_are_informational_not_expenses']
    guide=next(g for g in context['category_guides'] if g['monthly_guide_minor']==25000)
    assert guide['recorded_average_minor']==10000
    assert context['monthly_forecasts'][0]['expenses_minor']==0
    assert 'double-count' in captured[0][0]['content']

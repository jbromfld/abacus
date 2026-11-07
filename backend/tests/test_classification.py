import pytest

import io
from sqlalchemy import select
from abacus.classification import normalize_payee, learn_labels, apply_payee_rules, predict_unknown
from abacus.models import PayeeRule, Settings, StatementImport, Category
from abacus.imports import process_import


def manual(client, account, category, description='Grocery Store', kind='purchase'):
    result = client.post('/api/transactions', json=dict(date='2025-12-01', description=description, amount=1000, kind=kind, category_id=category, account_id=account))
    assert result.status_code == 201, result.text
    return result.json()


def mapped_csv(client, account, descriptions):
    content = 'Date,Description,Amount\n' + ''.join(f'2025-12-02,{description},-12.50\n' for description in descriptions)
    response = client.post('/api/imports', data={'account_id':account, 'period':'2025-12'}, files={'file':('test.csv',content.encode())})
    assert response.status_code == 201, response.text
    job = response.json()
    response = client.put('/api/imports/'+job['id']+'/mapping', json=dict(date_column='Date',description_column='Description',amount_column='Amount'))
    assert response.status_code == 200, response.text
    return response.json()


def test_normalization_is_conservative():
    assert normalize_payee('  ＧＲＯＣＥＲＹ  Store\t') == 'grocery store'
    assert normalize_payee('Store #123') == normalize_payee('Store #124')
    assert normalize_payee('Route 66') != normalize_payee('Route 67')
    assert normalize_payee('A-B') != normalize_payee('AB')
    assert predict_unknown('Unknown merchant','purchase') is None


def test_manual_label_propagates_across_cards_without_model(client, account_id, category_id, db, monkeypatch):
    manual(client, account_id, category_id)
    account2 = client.post('/api/accounts',json={'name':'Second card'}).json()['id']
    job = mapped_csv(client, account2, ['GROCERY   STORE'])
    assert job['rows'][0]['category_id'] == category_id
    assert job['rows'][0]['kind'] == 'purchase'
    assert job['rows'][0]['classification'] == 'remembered_payee'
    assert not job['rows'][0]['errors']
    def no_model(*args): raise AssertionError('Known payees must never call Ollama')
    monkeypatch.setattr('abacus.imports.ask_model',no_model)
    db.get(Settings,1).model='configured-but-unreachable-model'
    saved=db.get(StatementImport,job['id']);saved.status='processing';db.commit()
    process_import(job['id'])
    assert client.get('/api/imports/'+job['id']).json()['status']=='review'


def test_commit_teaches_but_unsaved_review_does_not(client, account_id, category_id):
    job=mapped_csv(client, account_id, ['Online subscription'])
    assert client.get('/api/payee-rules').json()==[]
    rows=[{**job['rows'][0],'source_index':0,'category_id':category_id}]
    client.put('/api/imports/'+job['id']+'/review',json={'rows':rows})
    assert client.get('/api/payee-rules').json()==[]
    assert client.post('/api/imports/'+job['id']+'/commit').status_code==200
    assert client.get('/api/payee-rules').json()[0]['category_id']==category_id
    assert client.post('/api/imports/'+job['id']+'/undo').status_code==200
    assert client.delete('/api/imports/'+job['id']).status_code==200
    assert len(client.get('/api/payee-rules').json())==1


def test_correction_updates_rule_and_forgetting_stops_propagation(client, account_id, category_id, db):
    other=db.scalar(select(Category.id).where(Category.id != category_id))
    t=manual(client,account_id,category_id)
    assert client.put('/api/transactions/'+t['id'],json={**t,'category_id':other}).status_code==200
    rules=client.get('/api/payee-rules').json()
    assert rules[0]['category_id']==other
    assert client.put('/api/payee-rules/'+rules[0]['id'],json={'category_id':category_id}).status_code==200
    assert mapped_csv(client,account_id,['GROCERY STORE'])['rows'][0]['category_id']==category_id
    assert client.delete('/api/payee-rules/'+rules[0]['id']).status_code==200
    assert client.get('/api/payee-rules').json()==[]
    # Existing transactions are unaffected by forgetting or editing a future rule.
    assert client.get('/api/transactions').json()[0]['category_id']==other


def test_conflicts_abstain_and_refunds_keep_their_type(db, category_id):
    other=db.scalar(select(Category.id).where(Category.id != category_id))
    learn_labels(db,[dict(description='Store',kind='purchase',category_id=category_id)])
    learn_labels(db,[dict(description='Store',kind='purchase',category_id=category_id),dict(description='STORE',kind='purchase',category_id=other)])
    db.commit()
    assert db.scalars(select(PayeeRule)).all()==[]
    learn_labels(db,[dict(description='Store',kind='refund',category_id=other)])
    db.commit()
    rows=apply_payee_rules(db,[dict(description='Store',kind='purchase',category_id=None),dict(description='Store',kind='refund',category_id=None),dict(description='Store',kind='refund',category_id=category_id)])
    assert rows[0]['category_id'] is None
    assert rows[1]['category_id']==other and rows[1]['kind']=='refund'
    assert rows[2]['category_id']==category_id


def test_apply_rules_to_existing_review_preserves_edits(client, account_id, category_id, db):
    job=mapped_csv(client,account_id,['Grocery Store'])
    assert job['rows'][0]['category_id'] is None
    manual(client,account_id,category_id)
    response=client.post('/api/imports/'+job['id']+'/categorize')
    assert response.status_code==200
    assert response.json()['rows'][0]['category_id']==category_id
    other=db.scalar(select(Category.id).where(Category.id != category_id))
    edited={**response.json()['rows'][0],'source_index':0,'category_id':other}
    client.put('/api/imports/'+job['id']+'/review',json={'rows':[edited]})
    assert client.post('/api/imports/'+job['id']+'/categorize').json()['rows'][0]['category_id']==other
    assert client.post('/api/imports/'+job['id']+'/commit').status_code==200
    assert client.post('/api/imports/'+job['id']+'/categorize').status_code==409


def test_unknown_payees_need_no_model_when_not_configured(client,account_id,db,monkeypatch):
    job=mapped_csv(client,account_id,['Unseen store'])
    monkeypatch.setattr('abacus.imports.ask_model',lambda *args: (_ for _ in ()).throw(AssertionError('No model configured')))
    saved=db.get(StatementImport,job['id']);saved.status='processing';db.commit()
    process_import(job['id'])
    result=client.get('/api/imports/'+job['id']).json()
    assert result['status']=='review' and result['rows'][0]['errors']
    assert result['rows'][0]['category_id'] is None


def test_csv_processing_preserves_reviewed_labels_without_model(client,account_id,category_id,db,monkeypatch):
    manual(client,account_id,category_id)
    job=mapped_csv(client,account_id,['Grocery Store']+[f'Unknown {i}' for i in range(12)])
    rows=[{**r,'source_index':i} for i,r in enumerate(job['rows'])]
    rows[1]['category_id']=category_id
    client.put('/api/imports/'+job['id']+'/review',json={'rows':rows})
    def no_model(*args): raise AssertionError('CSV must never call the local model')
    monkeypatch.setattr('abacus.imports.ask_model',no_model)
    db.get(Settings,1).model='test-model'
    saved=db.get(StatementImport,job['id']);saved.status='processing';db.commit()
    process_import(job['id'])
    result=client.get('/api/imports/'+job['id']).json()
    assert result['status']=='review'
    assert sum(bool(r['category_id']) for r in result['rows'])==2
    assert len(client.get('/api/payee-rules').json())==1


def test_export_only_saved_examples(client,account_id,category_id,db):
    from abacus.classification import export_examples
    import json
    manual(client,account_id,category_id)
    manual(client,account_id,None,description='Payment',kind='payment')
    mapped_csv(client,account_id,['Not saved'])
    output=io.StringIO()
    assert export_examples(db,output)==1
    record=json.loads(output.getvalue())
    assert set(record)=={'description','payee','kind','category_id','date'}
    assert record['payee']=='grocery store'


@pytest.mark.parametrize('description', ['PAYMENT THANK YOU', 'Online Payment', 'payment received', 'AUTOPAYMENT'])
def test_payment_keyword_defaults_without_model(client, account_id, db, monkeypatch, description):
    job=mapped_csv(client,account_id,[description])
    row=job['rows'][0]
    assert row['kind']=='payment' and row['category_id'] is None
    assert row['classification']=='description_keyword' and not row['errors']
    monkeypatch.setattr('abacus.imports.ask_model',lambda *args: (_ for _ in ()).throw(AssertionError('Payment must bypass model')))
    db.get(Settings,1).model='unreachable-model'
    saved=db.get(StatementImport,job['id']);saved.status='processing';db.commit()
    process_import(job['id'])
    assert client.get('/api/imports/'+job['id']).json()['status']=='review'
    assert client.post('/api/imports/'+job['id']+'/commit').status_code==200
    assert client.get('/api/forecast?month=2025-12').json()['actual']['expenses']==0


def test_payment_keyword_review_override_is_preserved(client,account_id,category_id,db):
    job=mapped_csv(client,account_id,['Prepayment for groceries'])
    row={**job['rows'][0],'source_index':0,'kind':'purchase','category_id':category_id}
    assert client.put('/api/imports/'+job['id']+'/review',json={'rows':[row]}).status_code==200
    reviewed=client.post('/api/imports/'+job['id']+'/categorize').json()['rows'][0]
    assert reviewed['kind']=='purchase' and reviewed['category_id']==category_id


def test_payment_keyword_overrides_pdf_model_type(client,account_id,category_id,db,monkeypatch):
    from test_imports import prepare, pdf_bytes
    job=prepare(client,account_id,pdf_bytes('12/29/2025 PAYMENT THANK YOU $12.50'),'payment.pdf')
    monkeypatch.setattr('abacus.imports.ask_model',lambda *args:{'rows':[dict(date='2025-12-29',description='PAYMENT THANK YOU',amount=1250,kind='purchase',category_id=category_id,page=1)]})
    saved=db.get(StatementImport,job['id']);saved.status='processing';db.get(Settings,1).model='test-model';db.commit()
    process_import(job['id'])
    row=client.get('/api/imports/'+job['id']).json()['rows'][0]
    assert row['kind']=='payment' and row['category_id'] is None and not row['errors']


@pytest.mark.parametrize('first,second',[
    ('panera bread #600874 k','panera bread #600878 k'),
    ('2025 holiday hustle','2026 holiday hustle'),
    ('2025-12-01 Holiday Hustle','2026-12-02 Holiday Hustle'),
    ('12/01/2025 Holiday Hustle','12/02/2026 Holiday Hustle'),
    ('PANERA BREAD #600874 K','panera   bread #600878 k'),
])
def test_merchant_metadata_variants_share_a_category(client,account_id,category_id,first,second):
    original=manual(client,account_id,category_id,description=first)
    job=mapped_csv(client,account_id,[second])
    row=job['rows'][0]
    assert row['description']==second
    assert row['category_id']==category_id and row['classification']=='normalized_payee'
    assert client.get('/api/transactions').json()[0]['description']==original['description']


@pytest.mark.parametrize('first,second',[
    ('Route 66','Route 67'),('Studio 54','Studio 55'),('7-Eleven','8-Eleven'),
    ('2025vision','2026vision'),('Holiday Cafe','Holiday Hustle'),
])
def test_meaningful_names_and_unmarked_numbers_remain_distinct(first,second):
    assert normalize_payee(first)!=normalize_payee(second)


def test_normalized_conflicts_preserve_specific_labels_and_abstain_for_new_variants(client,account_id,category_id,db):
    other=db.scalar(select(Category.id).where(Category.id!=category_id))
    manual(client,account_id,category_id,description='panera bread #600874 k')
    manual(client,account_id,other,description='panera bread #600878 k')
    job=mapped_csv(client,account_id,['panera bread #600874 k','panera bread #600878 k','panera bread #600899 k'])
    assert job['rows'][0]['category_id']==category_id
    assert job['rows'][1]['category_id']==other
    assert job['rows'][2]['category_id'] is None
    assert job['rows'][2]['errors']


def test_existing_memory_rules_match_normalized_variants_without_migration(client,account_id,category_id,db):
    db.add(PayeeRule(payee='2025 holiday hustle',kind='purchase',category_id=category_id));db.commit()
    job=mapped_csv(client,account_id,['2026 holiday hustle'])
    assert job['rows'][0]['category_id']==category_id
    assert job['rows'][0]['classification']=='normalized_payee'


def test_normalized_categories_do_not_change_exact_csv_duplicate_identity(client,account_id,category_id):
    first=mapped_csv(client,account_id,['panera bread #600874 k'])
    row={**first['rows'][0],'source_index':0,'category_id':category_id}
    client.put('/api/imports/'+first['id']+'/review',json={'rows':[row]})
    assert client.post('/api/imports/'+first['id']+'/commit').status_code==200
    second=mapped_csv(client,account_id,['panera bread #600878 k'])
    assert second['rows'][0]['category_id']==category_id
    assert second['rows'][0]['skip_duplicate'] is False
    assert client.post('/api/imports/'+second['id']+'/commit').status_code==200
    assert len(client.get('/api/transactions').json())==2


@pytest.mark.parametrize('first,second', [
    ('Amazon.com*PH0J27603', 'Amazon.com*7G1TY39K3'),
    ('AMAZON MKTPL*Z14FV4LT3', 'AMAZON MKTPL*RI3DB1453'),
])
def test_amazon_order_codes_share_category(client, account_id, category_id, first, second):
    manual(client, account_id, category_id, description=first)
    row = mapped_csv(client, account_id, [second])['rows'][0]
    assert row['category_id'] == category_id
    assert row['classification'] == 'normalized_payee'
    assert row['description'] == second
    assert not row['skip_duplicate']


def test_amazon_channels_and_other_star_merchants_remain_distinct():
    assert normalize_payee('Amazon.com*ABC123') != normalize_payee('AMAZON MKTPL*ABC123')
    assert normalize_payee('Other*ABC123') != normalize_payee('Other*XYZ987')


def test_similarity_fallback_and_ambiguity(db, category_id):
    other = db.scalar(select(Category.id).where(Category.id != category_id))
    learn_labels(db, [dict(description='Neighborhood Grocery Market', kind='purchase', category_id=category_id)])
    row = dict(description='Neighborhood Grocery Marke', kind='purchase', category_id=None)
    assert apply_payee_rules(db, [row])[0]['category_id'] == category_id
    assert row['classification'] == 'similar_payee'
    learn_labels(db, [dict(description='Neighborhood Grocery Markets', kind='purchase', category_id=other)])
    assert apply_payee_rules(db, [dict(description='Neighborhood Grocery Marke', kind='purchase')])[0].get('category_id') is None
    assert apply_payee_rules(db, [dict(description='Neighborhood Grocery Marke', kind='refund')])[0].get('category_id') is None


def test_similarity_preserves_numbers_short_names_and_edits():
    from abacus.payee_matching import similar_category
    groups = {('neighborhood store 123', 'purchase'): {'category'}}
    assert similar_category('neighborhood store 124', 'purchase', groups, .94, .05) is None
    assert similar_category('store', 'purchase', {('stores', 'purchase'): {'category'}}, .8, .05) is None
    assert similar_category('different store 123', 'purchase', groups, .8, .05) is None


def test_matching_config_reload_and_invalid_config(tmp_path, monkeypatch, caplog):
    import json
    import abacus.payee_matching as matching
    config = tmp_path / 'matching.json'
    monkeypatch.setattr(matching, 'CONFIG_PATH', config)
    config.write_text(json.dumps(dict(fuzzy_threshold=1, fuzzy_margin=.05, patterns=[dict(pattern=r'\bshop\*\w+', replacement='shop')])))
    assert normalize_payee('SHOP*ABC123') == 'shop'
    config.write_text(json.dumps(dict(fuzzy_threshold=1, fuzzy_margin=.05, patterns=[])))
    assert normalize_payee('SHOP*ABC123') == 'shop abc123'
    config.write_text('{bad json')
    assert matching.load_matching_config() == ([], 1, 1)
    assert 'config disabled' in caplog.text
    config.write_text(json.dumps(dict(fuzzy_threshold=.5, fuzzy_margin=.05, patterns=[])))
    assert matching.load_matching_config() == ([], 1, 1)
    config.write_text(json.dumps(dict(fuzzy_threshold=.94, fuzzy_margin=.05, patterns=[dict(pattern='[', replacement='') ])))
    assert matching.load_matching_config() == ([], 1, 1)

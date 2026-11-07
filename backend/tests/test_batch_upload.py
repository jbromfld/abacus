"""Batch UI uses independent per-file preparation, preserving partial successes."""


def upload(client,account,period,name,content):
    return client.post('/api/imports',data={'account_id':account,'period':period},files={'file':(name,content)})


def test_batch_files_have_independent_statuses_and_require_review(client,account_id):
    first=b'Date,Description,Amount\n2025-10-01,Grocer,12.50\n'
    second=b'Date,Description,Amount\n2025-11-01,Grocer,20.00\n'
    responses=[
        upload(client,account_id,'2025-10','oct.csv',first),
        upload(client,account_id,'2025-11','bad.csv',b'bad\n'),
        upload(client,account_id,'2025-10','duplicate.csv',first),
        upload(client,account_id,'2025-11','nov.csv',second),
    ]
    assert [r.status_code for r in responses]==[201,422,409,201]
    imports=client.get('/api/imports').json()
    assert len(imports)==2
    assert {i['period'] for i in imports}=={'2025-10','2025-11'}
    assert all(i['status']=='prepared' for i in imports)
    assert client.get('/api/transactions').json()==[]


def test_batch_files_can_target_different_cards(client,account_id):
    other=client.post('/api/accounts',json={'name':'Second card'}).json()['id']
    data=b'Date,Description,Amount\n2025-10-01,Grocer,12.50\n'
    first=upload(client,account_id,'2025-10','one.csv',data)
    second=upload(client,other,'2025-11','two.csv',data)
    assert first.status_code==second.status_code==201
    assert first.json()['account_id']==account_id
    assert second.json()['account_id']==other
    assert first.json()['period']=='2025-10' and second.json()['period']=='2025-11'

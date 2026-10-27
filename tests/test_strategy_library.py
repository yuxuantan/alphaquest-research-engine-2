import hashlib,json
from test_backtest_api import client,body,save_fixture
from test_optimization import optimization_body,wait_job


def test_instrument_groups_combine_dates_strategies_and_batch_trials_without_changing_reports(client):
    dataset=save_fixture(client)
    # Fixture source has no symbol; explicit missing identity is never guessed.
    first=client.post('/api/backtests',json=body(dataset['id'])).json()
    source=client.app.state.store
    with source.connect() as db:
        record=dict(dataset,symbol='MNQ');db.execute('UPDATE datasets SET metadata=? WHERE id=?',(json.dumps(record),dataset['id']))
    second=client.post('/api/backtests',json={**body(dataset['id']),'from_date':'2026-01-05','to_date':'2026-01-05'}).json()
    job=client.post('/api/backtests',json=optimization_body(dataset['id'])).json();assert wait_job(client,job['id'])['status']=='complete'
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in client.app.state.runs.root.glob('*/report.json')}
    groups=client.get('/api/strategies/groups').json()
    assert groups['total']==2
    mnq=next(g for g in groups['items'] if g['instrument']=='MNQ')
    assert mnq['backtests']==4
    page=client.get('/api/strategies/groups/'+mnq['id']+'/backtests',params=dict(limit=2)).json()
    assert page['total']==4 and len(page['items'])==2
    assert all(row['batch_id']==job['id'] for row in page['items'])
    for row in page['items']:
        saved=client.get('/api/backtests/'+row['id']).json()
        assert row['metrics']['total_net_pnl']==saved['summary']['total_net_pnl']
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    client.delete('/api/backtests/'+second['id'])
    assert client.get('/api/strategies/groups/'+mnq['id']+'/backtests').json()['total']==3
    client.delete('/api/datasets/'+dataset['id'])
    assert client.get('/api/strategies/groups/'+mnq['id']+'/backtests').json()['total']==3
    assert client.get('/api/strategies/groups/not-a-group/backtests').status_code==404
    assert client.get('/api/strategies/groups?limit=101').status_code==422


def test_legacy_index_uses_live_symbol_and_keeps_saved_report_unchanged(client):
    dataset=save_fixture(client);record=client.post('/api/backtests',json=body(dataset['id'])).json()
    # Recreate a historical manifest shape without touching its report files.
    metadata=record['run_metadata'];metadata.pop('instrument')
    with client.app.state.runs.connect() as db:db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(record),record['id']))
    dataset['symbol']='NQ'
    with client.app.state.store.connect() as db:db.execute('UPDATE datasets SET metadata=? WHERE id=?',(json.dumps(dataset),dataset['id']))
    assert client.get('/api/strategies/groups').json()['items'][0]['instrument']=='NQ'
    assert client.get('/api/backtests/'+record['id']).json()==record

"""Normal backtest publication, independent account status and reuse integrity."""
from test_backtest_api import client,body,save_fixture


def test_both_accounts_run_for_incompatible_source_and_missing_companion_invalidates_reuse(client):
    source=save_fixture(client);request=body(source['id']);request['reuse_results']=True
    response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
    record=response.json();automatic=record['run_metadata']['automatic_prop_analysis']
    assert automatic['label']=='Apex 50K EOD' and len(automatic['companions'])==1
    lucid=automatic['companions'][0];assert lucid['label']=='LucidFlex 50K'
    assert lucid['settings']['EVAL_PRICE']=='80.5' and lucid['settings']['ACTIVATION_FEE']=='0'
    for item in (automatic,lucid):
        job=client.get('/api/prop-analyses/'+item['id']).json()
        assert job['status']=='incompatible' and job['historical_net'] is None
    repeat=client.post('/api/backtests',json=request);assert repeat.status_code==200
    assert repeat.json()['id']==record['id']
    assert client.delete('/api/prop-analyses/'+lucid['id']).status_code==204
    renewed=client.post('/api/backtests',json=request);assert renewed.status_code==201,renewed.text
    assert renewed.json()['id']!=record['id']
    assert client.get('/api/backtests/'+record['id']).json()==record


def test_companion_publication_failure_rolls_back_primary_without_partial_backtest(client,monkeypatch):
    source=save_fixture(client);store=client.app.state.prop_analyses;original=store.publish_prepared;calls=[]
    def publish(prepared,directory):
        calls.append(prepared['id'])
        if len(calls)==2:raise ValueError('Injected companion publication failure')
        return original(prepared,directory)
    monkeypatch.setattr(store,'publish_prepared',publish)
    response=client.post('/api/backtests',json=body(source['id']))
    assert response.status_code==500 and len(calls)==2
    assert client.get('/api/backtests').json()['total']==0
    with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM analyses').fetchone()[0]==0


def test_late_source_exit_is_rejected_without_fabricated_lucid_liquidation(client,tmp_path):
    import json
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    for day in ('01/05/2026','01/06/2026'):
        for time,prices in [('21:44','99,100,99,100'),('21:46','100,103,100,103'),('21:47','103,103,103,103')]:
            lines.append(day+','+time+','+prices+',100,60,40')
    saved=client.post('/api/datasets',params=dict(filename='SYNTHETIC-late-Lucid-exit.csv',name='SYNTHETIC cutoff boundary',
        source_timezone='UTC',tick_size='.25',point_value='10'),content=('\n'.join(lines)+'\n').encode())
    assert saved.status_code==201,saved.text
    request=body(saved.json()['id']);request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
    request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
    response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
    record=response.json();lucid=record['run_metadata']['automatic_prop_analysis']['companions'][0]
    job=client.get('/api/prop-analyses/'+lucid['id']).json()
    assert job['status']=='incompatible' and job['historical_net'] is None
    assert 'earlier exit price is unavailable' in job['reason']
    check=client.post('/api/prop-analyses/check',json=dict(source_backtest_id=record['id'],trade_file='',settings=dict(PROP_FIRM='Lucid')))
    assert check.status_code==422 and 'not a simulated account breach' in check.text
    assert record['summary']['total_net_pnl']=='60.00'
    (tmp_path/'cutoff-rejection.json').write_text(json.dumps(dict(source=record,lucid=job,source_check=check.json(),expected_source_net='60.00'),indent=2))


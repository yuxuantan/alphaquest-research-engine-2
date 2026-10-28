"""Saved strategy/dataset hierarchy, explicit IS/OOS pairs and full source dates."""
from hashlib import sha256
import json
from alphaquest.strategy_browser import full_source
from test_research_workflow import client,save,body,oos,status

STRATEGY='consecutive_green_hold'


def run(client,dataset,contracts=1,strategy=STRATEGY):
    request=body(dataset);request['strategy_id']=strategy
    request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=contracts) if strategy==STRATEGY else {p['name']:p['default'] for s in client.get('/api/strategies').json() if s['id']==strategy for p in s['parameters']}
    result=client.post('/api/backtests',json=request);assert result.status_code==201,result.text
    return result.json()


def groups(client,strategy=STRATEGY):
    response=client.get('/api/strategies/'+strategy+'/datasets');assert response.status_code==200,response.text
    return response.json()['items']


def table(client,group,strategy=STRATEGY,**params):
    response=client.get('/api/strategies/'+strategy+'/datasets/'+group+'/backtests',params=params)
    assert response.status_code==200,response.text
    return response.json()


def test_strategy_then_full_dataset_period_then_matching_is_oos_metrics(client):
    dataset=save(client,days=4);insample=run(client,dataset)
    heldout=oos(client,insample);assert heldout.status_code==201,heldout.text
    before={p:sha256(p.read_bytes()).hexdigest() for p in client.app.state.runs.root.glob('*/*') if p.is_file()}
    strategies=client.get('/api/strategies/library').json()['items']
    assert {s['id'] for s in strategies}>={STRATEGY,'vwap_pullback_risk_sizing'}
    source=groups(client)[0]
    assert source['dataset']['start_date']=='2026-01-05' and source['dataset']['end_date']=='2026-01-08'
    assert insample['run_metadata']['selection']['to_date']=='2026-01-06' # full range must not be this
    page=table(client,source['id']);assert page['total']==1
    row=page['items'][0];assert row['parameters']==insample['run_metadata']['strategy']['parameters']
    assert row['insample']['id']==insample['id'] and len(row['oos'])==1
    assert row['oos'][0]['id']==heldout.json()['id']
    for actual,saved in ((row['insample'],insample),(row['oos'][0],heldout.json())):
        for key,value in actual['metrics'].items():assert value==saved['summary'][key]
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}
    assert status(client,dataset)['used']==1


def test_same_instrument_multiple_strategies_and_sources_do_not_merge(client):
    first=save(client,days=4);second=save(client,days=6)
    run(client,first);run(client,second);run(client,first,strategy='vwap_pullback_risk_sizing')
    assert len(groups(client))==2
    alternate=groups(client,'vwap_pullback_risk_sizing');assert len(alternate)==1
    assert alternate[0]['id'] not in {g['id'] for g in groups(client)}
    assert table(client,alternate[0]['id'],'vwap_pullback_risk_sizing')['total']==1
    assert client.get('/api/strategies/'+STRATEGY+'/datasets/'+alternate[0]['id']+'/backtests').status_code==404


def test_source_local_dates_are_saved_after_dataset_deletion_and_index_restart(client):
    assert full_source(dict(id='x',name='x',sha256='x',source_timezone='America/New_York',start='2017-05-21T22:01:00Z',end='2026-07-08T00:00:00Z'))['end_date']=='2026-07-07'
    dataset=save(client,days=4);record=run(client,dataset);group=groups(client)[0]
    assert record['run_metadata']['full_dataset']['end']==dataset['end']
    assert client.delete('/api/datasets/'+dataset['id']).status_code==204
    from alphaquest.strategy_browser import StrategyBrowser
    browser=StrategyBrowser(client.app.state.runs,client.app.state.store,client.app.state.prop_analyses)
    result=browser.dataset_groups(STRATEGY,0,50)['items'][0]
    assert result['dataset']['end_date']==group['dataset']['end_date']
    assert result['available_dataset_id'] is None
    assert browser.reports(STRATEGY,result['id'],0,25,'created_at_utc','desc')['total']==1


def test_missing_legacy_full_dates_are_not_invented_from_is_selection(client):
    dataset=save(client,days=4);record=run(client,dataset)
    record['run_metadata'].pop('full_dataset')
    with client.app.state.runs.connect() as db:db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(record),record['id']))
    client.delete('/api/datasets/'+dataset['id'])
    source=groups(client)[0]['dataset']
    assert not source['full_range_available'] and source['start_date'] is None and source['end_date'] is None


def test_multiple_oos_attempts_and_deleted_parent_do_not_reset_budget(client):
    dataset=save(client,days=4);record=run(client,dataset)
    first=oos(client,record).json();second=oos(client,record).json();group=groups(client)[0]['id']
    row=table(client,group)['items'][0];assert [r['id'] for r in row['oos']]==[second['id'],first['id']]
    assert client.delete('/api/backtests/'+record['id']).status_code==204
    page=table(client,group);assert page['total']==2
    assert all(row['insample'] is None and row['phase']=='oos' for row in page['items'])
    assert status(client,dataset)['used']==2


def test_different_parameters_cannot_be_paired_even_with_same_parent_id(client):
    dataset=save(client,days=4);record=run(client,dataset);out=oos(client,record).json()
    out['run_metadata']['strategy']['parameters']['contracts']=99
    with client.app.state.runs.connect() as db:db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(out),out['id']))
    page=table(client,groups(client)[0]['id']);assert page['total']==2
    assert next(r for r in page['items'] if r['insample'])['oos']==[]
    assert next(r for r in page['items'] if r['phase']=='oos')['oos'][0]['id']==out['id']


def test_parameters_paging_sort_nulls_last_and_legacy_is_not_labeled_is(client):
    dataset=save(client,days=4);records=[run(client,dataset,q) for q in (1,2,3)]
    out=oos(client,records[0]).json();group=groups(client)[0]['id']
    for direction in ('asc','desc'):
        result=table(client,group,sort='oos.total_net_pnl',direction=direction)
        assert result['items'][0]['id']==records[0]['id']
        assert len(result['items'])==3
    result=table(client,group,sort='param.contracts',direction='desc',limit=2)
    assert [r['parameters']['contracts'] for r in result['items']]==[3,2]
    assert result['varying_parameters']==['contracts']
    assert table(client,group,sort='param.contracts',direction='desc',offset=2,limit=2)['items'][0]['parameters']['contracts']==1
    base='/api/strategies/'+STRATEGY+'/datasets/'+group+'/backtests'
    assert client.get(base,params=dict(sort='param.missing')).status_code==422
    assert client.get(base,params=dict(direction='drop table')).status_code==422
    assert client.get(base,params=dict(limit=101)).status_code==422
    # A saved undeclared result remains accessible, with no fabricated IS label.
    legacy=run(client,dataset,4);legacy['run_metadata'].pop('research')
    with client.app.state.runs.connect() as db:db.execute('UPDATE runs SET manifest=? WHERE id=?',(json.dumps(legacy),legacy['id']))
    row=next(r for r in table(client,group)['items'] if r['id']==legacy['id'])
    assert row['insample'] is None and row['legacy']['id']==legacy['id'] and not row['oos']


def test_deleting_oos_prop_report_preserves_budget_and_blocks_unbudgeted_recalculation(client):
    dataset=save(client,days=4);record=run(client,dataset);heldout=oos(client,record).json()
    prop_id=heldout['run_metadata']['automatic_prop_analysis']['id'];group=groups(client)[0]['id']
    assert table(client,group)['items'][0]['oos'][0]['prop_status']=='complete'
    assert client.delete('/api/prop-analyses/'+prop_id).status_code==204
    result=table(client,group)['items'][0]['oos'][0]
    assert result['prop_status']=='deleted' and result['historical_net'] is None
    assert status(client,dataset)['used']==1
    assert client.get('/api/backtests/'+heldout['id']).json()==heldout
    assert client.post('/api/prop-analyses',json=dict(source_backtest_id=heldout['id'],trade_file='',settings={})).status_code==409
    assert status(client,dataset)['used']==1


def test_decimal_spelling_is_not_highlighted_as_a_different_parameter_value(client):
    dataset=save(client,days=4)
    definition=next(s for s in client.get('/api/strategies').json() if s['id']=='vwap_pullback_risk_sizing')
    for value in ('2','2.0'):
        request=body(dataset);request['strategy_id']=definition['id']
        request['strategy_parameters']={p['name']:p['default'] for p in definition['parameters']}
        request['strategy_parameters']['mm_risk_pct']=value
        response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
    group=groups(client,definition['id'])[0]['id']
    assert 'mm_risk_pct' not in table(client,group,definition['id'])['varying_parameters']
    request['strategy_parameters']['mm_risk_pct']='2.0000000000000000000000000001'
    assert client.post('/api/backtests',json=request).status_code==201
    result=table(client,group,definition['id'],sort='param.mm_risk_pct',direction='desc')
    assert result['varying_parameters']==['mm_risk_pct']
    assert result['items'][0]['parameters']['mm_risk_pct']=='2.0000000000000000000000000001'

"""Lucid-only batch refreshes, verified reuse, pinned exports and snapshots."""
import csv
import io
import json
from copy import deepcopy
from hashlib import sha256
from threading import Event
import time

import pytest
from test_optimization import client, optimization_body, start, wait_job
from test_automatic_prop import save_history
from test_backtest_api import save_fixture
from alphaquest.prop import native_analysis, lucid_rules
from alphaquest import optimization_prop


LEGACY = 'alphaquest-lucidflex50k-eod-v1'
REASON = 'Training funding time is unavailable: LucidFlex funding chain is censored at 2,000 sessions; acquisition time is unavailable.'


def historical_batch(client, monkeypatch, count=1):
    dataset = save_history(client)
    request = optimization_body(dataset['id'])
    request['execution_settings'].update(slippage_ticks=0, commission_per_contract_per_side='0')
    request['parameter_ranges'] = dict(green_bar_count=dict(start=1,end=1,step=0),
        hold_minutes=dict(start=1,end=1,step=0), contracts=dict(start=1,end=count,step=1 if count>1 else 0))
    original = native_analysis.training_economics
    def legacy_calibration(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[2]['ACCOUNT_TYPE'] == 'LucidFlex':
            result.update(status='unavailable', replacement_days=None, funding_chain_simulations=0, reason=REASON)
        return result
    with monkeypatch.context() as legacy:
        # Controlled historical-engine oracle; ordinary dataset/backtest/routes.
        legacy.setattr(lucid_rules,'MODEL_VERSION',LEGACY)
        legacy.setattr(native_analysis,'training_economics',legacy_calibration)
        job = wait_job(client,start(client,request))
        assert job['status']=='complete',job
    base='/api/backtests/batches/'+job['id']
    rows=client.get(base+'/results').json()['items']
    assert all(row['metrics']['lucid_historical_net'] is None for row in rows)
    return base,rows


def wait_refresh(client, base):
    end=time.monotonic()+180
    while time.monotonic()<end:
        state=client.get(base+'/lucid-refresh').json()
        if not state['pending']:return state
        time.sleep(.03)
    pytest.fail('Lucid refresh did not finish')


def test_refresh_links_current_results_and_csv_without_mutating_originals(client,monkeypatch):
    base,rows=historical_batch(client,monkeypatch,2)
    runs=client.app.state.runs
    with runs.connect() as db:before=list(db.execute('SELECT * FROM optimization_trials'))
    originals={str(p):sha256(p.read_bytes()).hexdigest() for row in rows for folder in
        [runs.root/row['run_id'],*[client.app.state.prop_analyses.root/item['id'] for item in [row['prop_analysis'],*row['prop_companions']]]]
        for p in folder.rglob('*') if p.is_file()}
    response=client.post(base+'/lucid-refresh');assert response.status_code==202,response.text
    assert response.json()['queued']==2
    state=wait_refresh(client,base)
    assert (state['available'],state['refreshed'],state['unavailable'])==(2,2,0)
    page=client.get(base+'/results?sort=lucid_historical_net&direction=desc').json()
    assert [row['trial'] for row in page['items']]==[1,2]
    for original,row in zip(rows,page['items']):
        assert row['metrics']['lucid_historical_net']==88792
        assert row['metrics']['historical_net']==original['metrics']['historical_net']
        item=row['prop_companions'][0]
        assert item['original_analysis_id']==original['prop_companions'][0]['id']
        assert item['id']!=item['original_analysis_id']
        assert item['model_version']==lucid_rules.MODEL_VERSION
        report=client.get('/api/prop-analyses/'+item['id']+'/downloads/report.json').json()
        assert report['calculations']['model_version']==lucid_rules.MODEL_VERSION
        assert report['source']['backtest']['id']==row['run_id']
        assert report['calculations']['history']['totals']['net']==row['metrics']['lucid_historical_net']
    csv_rows=list(csv.DictReader(io.StringIO(client.get(base+'/exports/results').text)))
    assert [r['lucid_historical_net'] for r in csv_rows]==['88792','88792']
    assert csv_rows[0]['lucid_analysis_id']==page['items'][0]['prop_companions'][0]['id']
    assert csv_rows[0]['lucid_model_version']==lucid_rules.MODEL_VERSION
    assert client.get(base+'/results?limit=1').json()['total']==2
    assert all(r['lucid_historical_net']=='' for r in csv.DictReader(io.StringIO(client.get(base+'/exports/results?prop_revision=0').text)))
    assert client.get(base+'/results?prop_revision=0').json()['items']==rows
    with runs.connect() as db:
        assert list(db.execute('SELECT * FROM optimization_trials'))==before
        count=db.execute('SELECT COUNT(*) FROM optimization_prop_links').fetchone()[0]
    for p,digest in originals.items():assert sha256(__import__('pathlib').Path(p).read_bytes()).hexdigest()==digest
    assert client.post(base+'/lucid-refresh').json()['queued']==0
    client.get(base+'/results');client.get(base+'/lucid-refresh');client.get(base+'/exports/results')
    with runs.connect() as db:assert db.execute('SELECT COUNT(*) FROM optimization_prop_links').fetchone()[0]==count
    assert client.delete(base).status_code==200
    with runs.connect() as db:assert db.execute('SELECT COUNT(*) FROM optimization_prop_links').fetchone()[0]==0


def test_reuse_existing_manual_analysis_and_recover_publication_without_recalculating(client,monkeypatch):
    base,rows=historical_batch(client,monkeypatch)
    source_id=rows[0]['run_id']
    request=dict(source_backtest_id=source_id,trade_file='',settings=dict(PROP_FIRM='Lucid'))
    response=client.post('/api/prop-analyses',json=request);id=response.json()['id']
    end=time.monotonic()+180
    while time.monotonic()<end:
        report=client.get('/api/prop-analyses/'+id).json()
        if report['status']=='complete':break
        assert report['status']!='error',report
        time.sleep(.03)
    assert report['historical_net']==88792
    with client.app.state.prop_analyses.connect() as db:count=db.execute('SELECT COUNT(*) FROM analyses').fetchone()[0]
    refreshed=client.post(base+'/lucid-refresh').json()
    assert refreshed['reused']==1 and refreshed['queued']==0
    store=client.app.state.optimizations
    job_id=base.rsplit('/',1)[-1]
    link=optimization_prop.latest(store.runs,job_id)[1]
    optimization_prop.append(store.runs,job_id,1,dict(link,status='queued',historical_net=None))
    # Reading cannot repair/write or launch a calculation.
    assert client.get(base+'/lucid-refresh').json()['pending']==1
    optimization_prop.initialize(store.runs,store.prop_analyses)
    assert client.get(base+'/results').json()['items'][0]['prop_companions'][0]['id']==id
    assert client.get(base+'/lucid-refresh').json()['pending']==0
    with store.prop_analyses.connect() as db:assert db.execute('SELECT COUNT(*) FROM analyses').fetchone()[0]==count
    verified=optimization_prop.read_verified(store.prop_analyses,id)
    snapshot=verified['source'];settings=verified['settings']
    assert optimization_prop.compatible(verified,snapshot,settings)
    for key in ('model_version','calculations','source','settings','runtime','implementation_sha256'):
        wrong=deepcopy(verified);wrong[key]={} if key!='model_version' else LEGACY
        assert not optimization_prop.compatible(wrong,snapshot,settings)


def test_duplicate_refresh_and_source_deletion_are_safe_while_worker_runs(client,monkeypatch):
    base,rows=historical_batch(client,monkeypatch)
    from alphaquest.prop import store as analysis_module
    run=analysis_module.run_analysis;entered=Event();release=Event()
    def paused(*args,**kwargs):
        entered.set();assert release.wait(15)
        return run(*args,**kwargs)
    monkeypatch.setattr(analysis_module,'run_analysis',paused)
    try:
        first=client.post(base+'/lucid-refresh').json();assert first['queued']==1
        assert entered.wait(10)
        revision=first['revision']
        second=client.post(base+'/lucid-refresh').json()
        assert second['already_pending']==1 and second['queued']==0
        assert client.delete(base).status_code==409
        assert client.delete('/api/backtests/'+rows[0]['run_id']).status_code==409
    finally:release.set()
    assert wait_refresh(client,base)['available']==1
    assert client.get(base+'/results',params={'prop_revision':revision}).json()['items'][0]['metrics']['lucid_historical_net'] is None
    assert client.get(base+'/results').json()['items'][0]['metrics']['lucid_historical_net']==88792


def test_unknown_active_and_source_boundary_rejections_are_explicit(client):
    dataset=save_fixture(client)
    request=optimization_body(dataset['id'])
    request['parameter_ranges']['contracts']=dict(start=1,end=1,step=0)
    job=wait_job(client,start(client,request));base='/api/backtests/batches/'+job['id']
    response=client.post(base+'/lucid-refresh')
    assert response.status_code==202,response.text
    assert response.json()['blocked']==1 and response.json()['queued']==0
    item=client.get(base+'/results').json()['items'][0]['prop_companions'][0]
    assert item['status']=='incompatible' and item['reason']
    client.app.state.optimizations.update(job['id'],status='running')
    try:assert client.post(base+'/lucid-refresh').status_code==409
    finally:client.app.state.optimizations.update(job['id'],status='complete')
    assert client.post('/api/backtests/batches/'+'f'*32+'/lucid-refresh').status_code==404

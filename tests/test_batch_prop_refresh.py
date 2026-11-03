"""Account-isolated refresh links, pinned exports and immutable saved trials."""
import csv
from contextlib import contextmanager
import io
import json
import sqlite3
from types import SimpleNamespace
from threading import Event
import time

import pytest

from alphaquest import optimization_prop
from alphaquest.prop import native_analysis, lucid_rules, automatic
from test_optimization import client, optimization_body, start, wait_job
from test_automatic_prop import save_history


def historical_accounts(client,monkeypatch):
    dataset=save_history(client)
    request=optimization_body(dataset['id'])
    request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
    request['parameter_ranges']=dict(green_bar_count=dict(start=1,end=1,step=0),
        hold_minutes=dict(start=1,end=1,step=0),contracts=dict(start=1,end=1,step=0))
    original=native_analysis.training_economics
    def legacy(*args,**kwargs):
        result=original(*args,**kwargs)
        result.update(status='unavailable',replacement_days=None,funding_chain_simulations=0,reason='SYNTHETIC earlier acquisition guard')
        return result
    with monkeypatch.context() as old:
        old.setattr(native_analysis,'MODEL_VERSION','SYNTHETIC-earlier-apex')
        old.setattr(automatic,'MODEL_VERSION','SYNTHETIC-earlier-apex')
        old.setattr(lucid_rules,'MODEL_VERSION','SYNTHETIC-earlier-lucid')
        old.setattr(native_analysis,'training_economics',legacy)
        job=wait_job(client,start(client,request));assert job['status']=='complete',job
    base='/api/backtests/batches/'+job['id']
    rows=client.get(base+'/results').json()['items']
    assert rows[0]['metrics']['historical_net'] is None and rows[0]['metrics']['lucid_historical_net'] is None
    return base,rows


def wait_all(client,base):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        state=client.get(base+'/prop-refresh').json()
        if not state['pending']:return state
        time.sleep(.03)
    pytest.fail('Prop refresh did not complete')


def test_all_accounts_update_independently_and_original_export_stays_pinned(client,monkeypatch):
    base,old=historical_accounts(client,monkeypatch)
    before=client.get(base+'/exports/results?prop_revision=0').content
    with client.app.state.runs.connect() as db:trials=list(db.execute('select * from optimization_trials'))
    response=client.post(base+'/prop-refresh');assert response.status_code==202,response.text
    assert response.json()['queued']==2
    state=wait_all(client,base)
    assert state['accounts']['apex']['available']==state['accounts']['lucid']['available']==1
    row=client.get(base+'/results?sort=historical_net&direction=desc').json()['items'][0]
    assert row['metrics']['historical_net']==452880 and row['metrics']['lucid_historical_net']==88792
    assert row['prop_analysis']['original_analysis_id']==old[0]['prop_analysis']['id']
    assert row['prop_companions'][0]['original_analysis_id']==old[0]['prop_companions'][0]['id']
    assert row['prop_analysis']['id']!=row['prop_companions'][0]['id']
    assert row['apex_refresh'] and row['lucid_refresh']
    export=list(csv.DictReader(io.StringIO(client.get(base+'/exports/results').text)))[0]
    assert export['historical_net']=='452880' and export['lucid_historical_net']=='88792'
    assert export['prop_analysis_id']==row['prop_analysis']['id']
    assert export['prop_original_analysis_id']==old[0]['prop_analysis']['id']
    assert export['prop_model_version']==native_analysis.MODEL_VERSION
    assert client.get(base+'/exports/results?prop_revision=0').content==before
    assert client.get(base+'/results?prop_revision=0').json()['items']==old
    with client.app.state.runs.connect() as db:
        assert list(db.execute('select * from optimization_trials'))==trials
        links=db.execute('select account,count(*) from optimization_prop_links group by account').fetchall()
        assert {x[0] for x in links}=={'apex','lucid'}
        count=db.execute('select count(*) from optimization_prop_links').fetchone()[0]
    client.get(base+'/prop-refresh');client.get(base+'/results');client.get(base+'/exports/results')
    with client.app.state.runs.connect() as db:assert db.execute('select count(*) from optimization_prop_links').fetchone()[0]==count
    assert client.post(base+'/prop-refresh').json()['queued']==0


def test_pending_duplicate_and_source_deletion_protect_both_accounts(client,monkeypatch):
    base,old=historical_accounts(client,monkeypatch)
    from alphaquest.prop import store as module
    run=module.run_analysis;entered=Event();release=Event()
    def paused(*args,**kwargs):
        entered.set();assert release.wait(30)
        return run(*args,**kwargs)
    monkeypatch.setattr(module,'run_analysis',paused)
    try:
        first=client.post(base+'/prop-refresh').json();assert first['queued']==2
        assert entered.wait(10)
        second=client.post(base+'/prop-refresh').json()
        assert second['queued']==0 and second['already_pending']==2
        assert client.delete(base).status_code==409
        assert client.delete('/api/backtests/'+old[0]['run_id']).status_code==409
        revision=first['revision']
    finally:release.set()
    assert wait_all(client,base)['pending']==0
    pinned=client.get(base+'/results',params={'prop_revision':revision}).json()['items'][0]
    assert pinned['metrics']['historical_net'] is None and pinned['metrics']['lucid_historical_net'] is None
    assert client.get(base+'/results').json()['items'][0]['metrics']['historical_net']==452880


def test_legacy_lucid_index_migration_preserves_existing_link_and_account_isolation(tmp_path):
    path=tmp_path/'legacy.sqlite3'
    @contextmanager
    def connect():
        db=sqlite3.connect(path)
        try:yield db;db.commit()
        finally:db.close()
    runs=SimpleNamespace(connect=connect)
    with connect() as db:
        db.executescript('''CREATE TABLE optimization_trials(optimization_id TEXT,trial INTEGER,PRIMARY KEY(optimization_id,trial));
            CREATE TABLE optimization_prop_links(id INTEGER PRIMARY KEY AUTOINCREMENT,optimization_id TEXT,trial INTEGER,analysis_id TEXT,payload TEXT);
            INSERT INTO optimization_trials VALUES('job',1);''')
        db.execute('insert into optimization_prop_links(optimization_id,trial,analysis_id,payload) values(?,?,?,?)',
            ('job',1,'lucid-old',json.dumps(dict(id='lucid-old',status='complete',historical_net=123))))
    optimization_prop.initialize(runs,SimpleNamespace())
    assert optimization_prop.latest(runs,'job')[1]['id']=='lucid-old'
    optimization_prop.append(runs,'job',1,dict(id='apex-new',status='complete',historical_net=456),account='apex')
    assert optimization_prop.latest(runs,'job')[1]['historical_net']==123
    assert optimization_prop.latest(runs,'job',account='apex')[1]['historical_net']==456
    assert optimization_prop.latest(runs,'job',snapshot=1,account='apex')=={}

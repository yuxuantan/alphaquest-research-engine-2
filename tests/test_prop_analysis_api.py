import json
from pathlib import Path
from threading import Event
import time
from fastapi.testclient import TestClient
import pytest
from alphaquest.app import create_app
from alphaquest.prop.analysis import prepare
from alphaquest.prop.settings import DEFAULTS
from alphaquest.prop.adapter import adapt
from alphaquest.backtest_runs import RunStore

FIXTURES=Path(__file__).parent/'fixtures/backtest_contract'

def backtest(client,name='arithmetic_5m',quantity=2):
    d=client.post('/api/datasets',params=dict(filename=name+'.csv',name='SYNTHETIC '+name,source_timezone='UTC',tick_size='.25',point_value='10'),content=(FIXTURES/(name+'.csv')).read_bytes()).json()
    r=client.post('/api/backtests',json=dict(dataset_id=d.get('id',d.get('dataset_id')),strategy_id='consecutive_green_hold',strategy_parameters=dict(green_bar_count=3,hold_minutes=20,contracts=quantity),execution_settings=dict(initial_capital='10000',tick_size='.25',point_value='10',slippage_ticks=1,commission_per_contract_per_side='1')))
    assert r.status_code==201,r.text
    return r.json()

def wait(client,id):
    until=time.monotonic()+20
    while time.monotonic()<until:
        r=client.get('/api/prop-analyses/'+id).json()
        if r['status'] in ('complete','error'):return r
        time.sleep(.02)
    raise AssertionError('Analysis did not complete')

@pytest.fixture
def portal(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:yield client

def test_arithmetic_download_and_reopen(portal):
    r=backtest(portal);body=dict(source_backtest_id=r['id'],overrides=dict(OOS_START_DATE=None,VALIDATION_SPLIT=0,PROP_MC_SIMS=32))
    checked=portal.post('/api/prop-analyses/check',json=body);assert checked.status_code==200,checked.text
    j=checked.json();assert j['effective_engine']=='trade'
    # Independently: reference 40 / 2 = 20; commission 4 / 2 = 2;
    # slippage 10 / 2 = 5. Net 26 / 2 = 13 per mini. Never 13 - 7.
    assert j['settings']['COMMISSION_PER_CONTRACT']==2
    assert j['settings']['SLIPPAGE_PER_CONTRACT']==5
    assert j['source']['reconciliation']['filtered_normalized_totals']['net']=='13.00'
    job=portal.post('/api/prop-analyses',json=body).json();assert wait(portal,job['id'])['status']=='complete'
    download=portal.get(f"/api/prop-analyses/{job['id']}/downloads/report.json");report=download.json()
    assert report['statistics']['average_net']==13
    assert report['evaluation']['fail_time']==32
    assert report['statistics']['bootstrap_usd_ci']==[13,13]
    assert report['source']['backtest']==r
    assert portal.get(f"/api/prop-analyses/{job['id']}/downloads/report.json").content==download.content
    assert 'profit_net_usd' in portal.get(f"/api/prop-analyses/{job['id']}/downloads/trades.csv").text
    literal=portal.post('/api/prop-analyses/check',json={**body,'preset':'notebook'}).json();assert literal['settings']['COMMISSION_PER_CONTRACT']==2.25
    assert literal['settings']['SLIPPAGE_PER_CONTRACT']==5
    priced=portal.post('/api/prop-analyses/check',json={**body,'pricing':'49+129'}).json()['settings']
    assert [priced[k] for k in ('ATTEMPT_FEE','EVAL_FEE','PA_ACTIVATION')]==[49,49,129]


def test_empty_and_oos_rejected_no_fake_trades(portal):
    r=backtest(portal)
    for overrides in [dict(OOS_START_DATE='2030-01-01'),dict(OOS_START_DATE=None),dict(ENGINE='other'),dict(PROP_MC_SIMS=0),dict(SEED=True),dict(unknown=1)]:
        assert portal.post('/api/prop-analyses/check',json=dict(source_backtest_id=r['id'],overrides=overrides)).status_code==422
    r=backtest(portal,'no_trades');resp=portal.post('/api/prop-analyses/check',json=dict(source_backtest_id=r['id'],overrides=dict(OOS_START_DATE=None,VALIDATION_SPLIT=0)))
    assert resp.status_code==422 and 'No weekday trades' in resp.text


def test_duplicate_submission_and_failed_operation_are_distinct(portal,monkeypatch):
    import alphaquest.prop.store as store
    r=backtest(portal);entered=Event();release=Event()
    def failing(*a,**kw):entered.set();assert release.wait(10);raise RuntimeError('controlled failure')
    monkeypatch.setattr(store,'run_analysis',failing)
    body=dict(source_backtest_id=r['id'],overrides=dict(OOS_START_DATE=None,VALIDATION_SPLIT=0,PROP_MC_SIMS=16))
    a=portal.post('/api/prop-analyses',json=body).json();assert entered.wait(5)
    try:
        b=portal.post('/api/prop-analyses',json=body).json();assert a['id']==b['id']
        assert portal.get(f"/api/prop-analyses/{a['id']}/downloads/report.json").status_code==409
    finally:release.set()
    result=wait(portal,a['id']);assert result['status']=='error' and 'controlled failure' in result['error']
    assert portal.get(f"/api/prop-analyses/{a['id']}/downloads/report.json").status_code==409

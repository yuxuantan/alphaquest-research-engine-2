"""Qualified campaign gate and real independent phase calculations."""
import csv
from decimal import Decimal
from datetime import datetime
import json
import time
from uuid import uuid4

from test_research_workflow import client
from test_campaign_oos import frozen_workflow, oos_csv, run_oos


def qualified_source(client):
    original=oos_csv().decode().splitlines();lines=[original[0]]
    for line in original[1:]:
        row=line.split(',')
        if datetime.strptime(row[0],'%m/%d/%Y').weekday()>=5:continue
        row[2:6]=[str(10000+(Decimal(v)-100)*100) for v in row[2:6]]
        lines.append(','.join(row))
    _,workflow=frozen_workflow(client,symbol='NQ',point_value='20',csv_content=('\n'.join(lines)+'\n').encode())
    job,_=run_oos(client,workflow)
    prefix='/api/campaign-workflows/'+workflow['id']+'/oos/monte-carlo'
    assert client.get('/api/prop-sim/candidates').json()['items']==[]
    response=client.post(prefix+'/run',json={'job_id':job['id']});assert response.status_code==202,response.text
    deadline=time.monotonic()+30
    while True:
        status=client.get('/api/prop-analyses/'+response.json()['id']).json()
        if status['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline,status
        time.sleep(.05)
    assert status['status']=='complete',status
    sources=client.get('/api/prop-sim/candidates')
    assert sources.status_code==200,sources.text
    assert sources.json()['items'],sources.text
    return workflow,sources.json()['items'][0]


def body(source):
    return dict(request_id=uuid4().hex,selections=[source['selection']],
        evaluation_minimum_micros=1,evaluation_maximum_micros=3,funded_minimum_micros=1,funded_maximum_micros=3,
        simulations=32,seed=42,block_weekdays=5,evaluation_price='49',activation_fee='129',
        start_date='2026-11-16',funded_horizon_calendar_days=90,receipt_delay_calendar_days=2,
        maximum_funded_breach_probability=.25,commission_per_mnq_side='0.51')


def wait_prop(client,id):
    deadline=time.monotonic()+90
    while True:
        response=client.get('/api/prop-sim/'+id);assert response.status_code==200,response.text
        data=response.json()
        if all(p['status'] not in ('queued','running') for p in data['phases'].values()):break
        assert time.monotonic()<deadline,data
        time.sleep(.05)
    assert all(p['status']=='complete' for p in data['phases'].values()),data
    return data


def test_qualified_source_gate_real_phase_math_and_durable_results(client):
    workflow,source=qualified_source(client);request=body(source)
    assert client.post('/api/prop-sim/check',json=dict(request,selections=[source['selection']]*2)).status_code==422
    forged=dict(source['selection'],candidate=4 if source['selection']['candidate']!=4 else 1)
    forged['monte_carlo_id']=uuid4().hex
    assert client.post('/api/prop-sim/check',json=dict(request,selections=[forged])).status_code==409
    response=client.post('/api/prop-sim/check',json=request);assert response.status_code==200,response.text
    checked=response.json()
    assert checked['status']=='compatible' and all(p['candidate_search_count']==3 for p in checked['phases'].values())
    eval_request=checked['phases']['evaluation']['request'];funded_request=checked['phases']['funded']['request']
    assert 'horizon_calendar_days' not in eval_request
    assert 'evaluation_price' not in json.dumps(funded_request) and 'activation_fee' not in json.dumps(funded_request)
    assert all(c['source']['source_backtest_id']==source['source_backtest_id'] for c in eval_request['candidates'])
    assert eval_request['candidates'][0]['simulation']['max_micros']==60
    assert funded_request['candidates'][0]['simulation']['max_micros']==40
    assert client.get('/api/prop-sim/defaults').json()['defaults']['maximum_funded_breach_probability'] is None
    uncapped=client.post('/api/prop-sim/check',json=dict(request,maximum_funded_breach_probability=None)).json()
    assert uncapped['phases']['evaluation']['calculation_key']==checked['phases']['evaluation']['calculation_key']
    assert uncapped['phases']['funded']['request']['constraints']['maximum_account_breach_probability'] is None
    for field,value in [('evaluation_maximum_micros',61),('funded_maximum_micros',41),('funded_minimum_micros',4)]:
        assert client.post('/api/prop-sim/check',json=dict(request,**{field:value})).status_code==422
    for phase,other in [('evaluation','funded'),('funded','evaluation')]:
        changed=client.post('/api/prop-sim/check',json=dict(request,**{phase+'_maximum_micros':4})).json()
        assert changed['phases'][phase]['candidate_search_count']==4
        assert changed['phases'][other]['calculation_key']==checked['phases'][other]['calculation_key']
    high=client.post('/api/prop-sim/check',json=dict(request,evaluation_minimum_micros=58,
        evaluation_maximum_micros=60,funded_minimum_micros=38,funded_maximum_micros=40))
    assert high.status_code==200,high.text
    for phase,expected in [('evaluation',[58,59,60]),('funded',[38,39,40])]:
        assert sorted(c['micros'] for c in high.json()['phases'][phase]['request']['candidates'])==expected
    # At 50 USD net per NQ daily, 60 MNQ earns 300/day and reaches 3000 in 10 days.
    # The old implicit 40-MNQ simulation cap would have taken 15 days instead.
    from alphaquest.prop.native_engine import evaluation as evaluate
    cap=high.json()['phases']['evaluation']['request']['candidates'][0]['simulation']['max_micros']
    native=evaluate([[(50.,0.)]]*30,60,8,42,max_micros=cap)
    assert list(native['outcomes'])==['passed']*8 and list(native['days'])==[10]*8
    legacy={k:v for k,v in request.items() if not k.endswith('_micros')}
    legacy.update(minimum_micros=1,maximum_micros=3)
    old_check=client.post('/api/prop-sim/check',json=legacy)
    assert old_check.status_code==200,old_check.text
    assert all(old_check.json()['phases'][p]['calculation_key']==checked['phases'][p]['calculation_key'] for p in ('evaluation','funded'))
    changed=client.post('/api/prop-sim/check',json=dict(request,evaluation_price='99')).json()
    assert changed['phases']['funded']['calculation_key']==checked['phases']['funded']['calculation_key']
    changed=client.post('/api/prop-sim/check',json=dict(request,funded_horizon_calendar_days=30)).json()
    assert changed['phases']['evaluation']['calculation_key']==checked['phases']['evaluation']['calculation_key']
    response=client.post('/api/prop-sim',json=request);assert response.status_code==202,response.text
    saved=wait_prop(client,response.json()['id'])
    assert client.post('/api/prop-sim',json=request).json()['id']==saved['id']
    assert client.post('/api/prop-sim',json=legacy).json()['id']==saved['id']
    evaluation=client.get('/api/prop-sim/'+saved['id']+'/results/evaluation').json()['calculations']
    funded=client.get('/api/prop-sim/'+saved['id']+'/results/funded').json()['calculations']
    assert len(evaluation['candidates'])==len(funded['candidates'])==3
    assert evaluation['winner'] is None
    resolved=[r for r in evaluation['candidates'] if r['metrics']['cost_per_funded'] is not None]
    assert resolved
    for row in resolved:
        m=row['metrics'];assert abs(m['cost_per_funded']-(49/m['pass_probability']+129))<1e-8
    for row in funded['candidates']:
        assert row['paths']
        expected=sum(p['cash_received'] for p in row['paths'])/len(row['paths'])
        assert row['metrics']['expected_funded_cash_payouts_within_horizon']==expected
        assert all(p['cash_received']>=0 and p['pending_cash']>=0 for p in row['paths'])
        assert 'paid_evaluation_fees' not in row['metrics']
    assert any(r['metrics']['expected_funded_cash_payouts_within_horizon']>0 for r in funded['candidates'])
    for phase in ('evaluation','funded'):
        campaign=saved['campaign_ids'][phase]
        blocked=client.get('/api/research-campaigns/'+campaign+'/deletion')
        assert blocked.status_code==409 and 'saved Prop Sim' in blocked.text
        for kind in ('results.csv','report.json','analysis.zip','source_checks.json'):
            assert client.get('/api/research-campaigns/'+campaign+'/exports/'+kind).status_code==200
        job=saved['phases'][phase]['analysis_id']
        assert client.get('/api/jobs/prop_analysis/'+job).json()['links'][0]['href']=='#prop-sim?analysis='+saved['id']
    assert client.app.state.campaign_workflows.get(workflow['id'])['narrow']==workflow['narrow']
    from fastapi.testclient import TestClient
    from alphaquest.app import create_app
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get('/api/prop-sim/'+saved['id']+'/results/funded').json()['calculations']==funded
    # Qualification is rechecked on launch, including an idempotent/cached request.
    mc_id=source['selection']['monte_carlo_id'].replace('-','')
    path=client.app.state.prop_analyses.root/mc_id/'report.json';original=path.read_bytes();path.write_text('{}')
    try:
        assert client.post('/api/prop-sim',json=request).status_code==409
        assert client.get('/api/prop-sim/'+saved['id']+'/results/funded').status_code==200
    finally:path.write_bytes(original)

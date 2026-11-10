"""IS-only grid arithmetic, profitable selection, immutable carry-forward and boundaries."""
import json
import time
from uuid import uuid4
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from alphaquest.app import create_app
from test_research_workflow import client
from test_campaign_mechanics import create_workflow,run_validation,checks


def sustainable_csv(fragile=False):
    """24 labeled synthetic months, 144 trades; independently derived 78/month."""
    from test_campaign_mechanics import mechanics_csv
    lines = ['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol',
             '01/01/2024,09:00,100,100,100,100,100,60,40']
    template = mechanics_csv().decode().splitlines()[1:-1]
    for year in (2024,2025):
        for month in range(1,13):
            for row in template:
                row = f'{month:02}/05/{year}' + row[row.index(','):]
                if fragile and ',14:24,' in row:
                    row = row.replace(',104,104,104,104,', ',99,99,99,99,')
                lines.append(row)
    lines.extend(['12/31/2025,09:00,100,100,100,100,100,60,40',
                  '01/01/2026,09:00,900,900,900,900,100,60,40'])
    return ('\n'.join(lines)+'\n').encode()


def create_broad_workflow(client,fragile=False):
    dataset=client.post('/api/datasets',params=dict(filename='SYNTHETIC-24-months.csv',name='SYNTHETIC 24-month screening',symbol='SYNTHETIC',source_timezone='UTC',tick_size='.25',point_value='10'),content=sustainable_csv(fragile)).json()
    body=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',sample_split=dict(mode='dates',is_start='2024-01-01',is_end='2025-12-31',oos_start='2026-01-01',oos_end='2026-01-01'),execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
    response=client.post('/api/campaign-workflows',json=body);assert response.status_code==201,response.text
    return dataset,body,response.json()


def passed_mechanics(client):
    dataset,body,workflow=create_broad_workflow(client)
    result=run_validation(client,workflow);prefix='/api/campaign-workflows/'+workflow['id']
    reviewed=client.patch(prefix+'/review',json=checks(result)).json()
    response=client.post(prefix+'/confirm',json={'revision':reviewed['review']['revision']})
    assert response.status_code==200,response.text
    return dataset,body,response.json()


def broad_grid(green_end=4,hold_end=60,contracts_end=3):
    return dict(workers=1,parameter_ranges={
        'green_bar_count':dict(start=3,end=green_end,step=1 if green_end!=3 else 0),
        'hold_minutes':dict(start=20,end=hold_end,step=20 if hold_end!=20 else 0),
        'contracts':dict(start=1,end=contracts_end,step=1 if contracts_end!=1 else 0)})


def preview_body(client,prefix,grid):
    response=client.post(prefix+'/broad/preview',json=grid);assert response.status_code==200,response.text
    return dict(grid,revision=response.json()['revision'],preview_token=response.json()['preview_token'])


def start_grid(client,prefix,grid):
    body=preview_body(client,prefix,grid)
    response=client.post(prefix+'/broad/run',json=body);assert response.status_code==202,response.text
    return wait_job(client,response.json()['id']),body


def wait_job(client,id):
    deadline=time.monotonic()+20
    while True:
        job=client.get('/api/backtests/batches/'+id).json()
        if job['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert job['status']=='complete',job
    return job


def selection(client,prefix,trials,revision=None,job_id=None):
    state=client.get(prefix+'/broad').json()['state']
    return client.patch(prefix+'/broad/selection',json=dict(job_id=job_id or state['job_id'],revision=state['revision'] if revision is None else revision,trials=trials))


def test_grid_uses_fixed_is_costs_rejects_nonprofit_and_freezes_at_most_two(client):
    dataset,body,workflow=create_broad_workflow(client)
    prefix='/api/campaign-workflows/'+workflow['id']
    assert client.post(prefix+'/broad/preview',json=broad_grid()).status_code==409
    assert client.get('/api/backtests/batches').json()['total']==0
    result=run_validation(client,workflow)
    reviewed=client.patch(prefix+'/review',json=checks(result)).json()
    assert client.post(prefix+'/confirm',json={'revision':reviewed['review']['revision']}).status_code==200
    job,request=start_grid(client,prefix,broad_grid())
    assert job['total_trials']==18 and job['request']['automatic_prop'] is False
    response=client.get(prefix+'/broad/results');assert response.status_code==200,response.text
    rows=response.json()['items'];assert len(rows)==18
    assert [float(row['metrics']['total_net_pnl']) for row in rows]==[1872,3744,5616,-1944,-3888,-5832,-504,-1008,-1512]+[0]*9
    assert [r['trial'] for r in rows if r['qualifies']]==[1,2,3]
    for row in rows:
        record=client.get('/api/backtests/'+row['run_id']).json()
        assert record['run_metadata']['selection']['from_date']=='2024-01-01'
        assert record['run_metadata']['selection']['to_date']=='2025-12-31'
        assert record['execution_settings']==result['declaration']['execution_settings']
        assert record['run_metadata']['research']['workflow_phase']=='is_broad'
        assert 'automatic_prop_analysis' not in record['run_metadata']
    measured=rows[0]['screening']
    assert measured['closed_trades']==144
    assert measured['metrics']['is_history_months']==24
    assert measured['metrics']['is_full_months']==24
    assert float(measured['metrics']['is_profitable_months_pct'])==100
    assert float(measured['metrics']['is_mtm_max_drawdown'])==40.5 # includes open-position entry costs after the 37 loss
    assert float(measured['metrics']['is_stress_net_profit'])==1152
    stress=client.get('/api/backtests/'+measured['cost_stress']['run_id']).json()
    assert stress['execution_settings']['slippage_ticks']==2
    assert stress['summary']['trades_taken']==144
    assert float(stress['summary']['total_net_pnl'])==1152
    assert client.get('/api/backtests/'+rows[0]['run_id']+'/exports/is_screening').status_code==200
    assert client.delete('/api/backtests/'+stress['id']).status_code==409
    # A tampered stress trade file cannot be adopted as if it were original evidence.
    path=client.app.state.runs.root/stress['id']/'trades.csv';original=path.read_bytes()
    path.write_bytes(original+b'\n')
    assert selection(client,prefix,[1]).status_code==409
    assert client.get('/api/backtests/'+rows[0]['run_id']+'/exports/is_screening').status_code==409
    path.write_bytes(original)
    detailed=client.post('/api/backtests/'+rows[0]['run_id']+'/detailed')
    assert detailed.status_code==201,detailed.text
    assert client.get('/api/backtests/'+detailed.json()['id']+'/exports/is_screening').status_code==200
    for bad in [[4],[10],[999],[1,1]]:
        assert selection(client,prefix,bad).status_code==409
    assert selection(client,prefix,[1,2,3]).status_code==422
    assert selection(client,prefix,[1],job_id=uuid4().hex).status_code==409
    state=selection(client,prefix,[1]).json()
    assert selection(client,prefix,[2],revision=state['revision']-1).status_code==409
    state=selection(client,prefix,[1,2]).json()
    frozen=client.post(prefix+'/broad/confirm',json={'job_id':job['id'],'revision':state['revision']})
    assert frozen.status_code==200,frozen.text
    frozen=frozen.json();assert [x['total_net_pnl'] for x in frozen['selection']]==['1872.00','3744.00']
    assert frozen['confirmed_at_utc']
    assert client.get(prefix+'/phases/is_narrow').status_code==200
    assert client.get(prefix+'/phases/oos').status_code==409
    assert selection(client,prefix,[]).status_code==409
    assert client.post(prefix+'/broad/preview',json=broad_grid()).status_code==409
    assert client.post(prefix+'/broad/run',json=request).status_code==409
    assert client.delete('/api/backtests/batches/'+job['id']).status_code==409
    assert client.delete('/api/backtests/'+rows[-1]['run_id']).status_code==409
    assert client.post('/api/backtests/'+rows[0]['run_id']+'/oos',json={'request_id':str(uuid4())}).status_code==409
    downloaded=client.get(prefix+'/broad/download').json()
    before={p:sha256(p.read_bytes()).hexdigest() for p in client.app.state.runs.root.glob('*/*') if p.is_file()}
    with TestClient(create_app(client.app.state.store.path)) as reopened:
        assert reopened.get(prefix+'/broad/download').json()==downloaded
        assert reopened.get('/api/jobs?kind=mechanic_validation').json()['total']==1
        assert reopened.get('/api/jobs?kind=backtest_batch').json()['total']==1
        assert reopened.get(prefix+'/phases/is_narrow').status_code==200
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}


def test_no_profitable_rows_do_not_advance_retries_are_idempotent_and_one_choice_is_enough(client):
    _,_,workflow=passed_mechanics(client);prefix='/api/campaign-workflows/'+workflow['id']
    grid=broad_grid();grid['parameter_ranges']['green_bar_count']=dict(start=4,end=4,step=0)
    body=preview_body(client,prefix,grid)
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(lambda _:client.post(prefix+'/broad/run',json=body),range(2)))
    assert all(r.status_code==202 for r in responses)
    assert len({r.json()['id'] for r in responses})==1
    job=wait_job(client,responses[0].json()['id'])
    assert not any(r['qualifies'] for r in client.get(prefix+'/broad/results').json()['items'])
    state=client.get(prefix+'/broad').json()['state']
    assert client.post(prefix+'/broad/confirm',json=dict(job_id=job['id'],revision=state['revision'])).status_code==409
    assert selection(client,prefix,[1]).status_code==409
    assert client.get(prefix+'/phases/is_narrow').status_code==409
    assert client.post(prefix+'/broad/run',json=body).json()['id']==job['id']
    replacement,_=start_grid(client,prefix,broad_grid(3,20))
    assert replacement['id']!=job['id']
    assert client.get('/api/jobs?kind=backtest_batch').json()['total']==2
    assert client.delete('/api/backtests/batches/'+job['id']).status_code==409
    expanded,_=start_grid(client,prefix,broad_grid(3,20,4))
    assert expanded['reused_trials']==3 # native base and cost-stress evidence safely reused together
    earlier=client.get(prefix+'/broad',params={'job_id':replacement['id']})
    assert earlier.status_code==200,earlier.text
    assert earlier.json()['state']['archived'] and earlier.json()['job']['id']==replacement['id']
    earlier_rows=client.get(prefix+'/broad/results',params={'job_id':replacement['id']}).json()
    assert earlier_rows['total']==3 and not any(r['selectable'] for r in earlier_rows['items'])
    package=client.get(prefix+'/broad/download',params={'job_id':replacement['id']}).json()
    assert package['state']['archived'] and package['job']['id']==replacement['id']
    assert client.get(prefix+'/broad',params={'job_id':uuid4().hex}).status_code==404
    assert selection(client,prefix,[1],job_id=replacement['id']).status_code==409
    detail=client.get('/api/jobs/backtest_batch/'+expanded['id']).json()
    assert detail['links']==[dict(label='Open IS Broad',href=f"#campaigns/workflows/{workflow['id']}/is_broad?job={expanded['id']}")]
    replacement=expanded
    state=selection(client,prefix,[2]).json()
    confirmed=client.post(prefix+'/broad/confirm',json=dict(job_id=replacement['id'],revision=state['revision'])).json()
    assert len(confirmed['selection'])==1 and confirmed['selection'][0]['parameters']['contracts']==2
    path=client.app.state.runs.root/confirmed['selection'][0]['run_id']/'trades.csv'
    path.write_bytes(path.read_bytes()+b'\n')
    assert client.get(prefix+'/phases/is_narrow').status_code==409
    assert client.get(prefix+'/broad/download').status_code==409


def test_preview_boundaries_and_code_drift_do_not_change_saved_jobs(client,monkeypatch):
    _,_,workflow=passed_mechanics(client);prefix='/api/campaign-workflows/'+workflow['id']
    bad=broad_grid();bad['parameter_ranges']['contracts']['end']=10001
    assert client.post(prefix+'/broad/preview',json=bad).status_code==409
    bad=broad_grid();bad['parameter_ranges']['contracts']['step']='0.5'
    assert client.post(prefix+'/broad/preview',json=bad).status_code==409
    assert client.post(prefix+'/broad/preview',json=dict(broad_grid(),sample_split={})).status_code==422
    body=preview_body(client,prefix,broad_grid(3,20))
    from alphaquest import campaign_broad
    original=campaign_broad.engine_identity
    monkeypatch.setattr(campaign_broad,'engine_identity',lambda:'changed')
    assert client.post(prefix+'/broad/run',json=body).status_code==409
    assert client.get('/api/backtests/batches').json()['total']==0
    monkeypatch.setattr(campaign_broad,'engine_identity',original)
    job=client.post(prefix+'/broad/run',json=body).json();wait_job(client,job['id'])
    state=selection(client,prefix,[1]).json()
    monkeypatch.setattr(campaign_broad,'engine_identity',lambda:'changed')
    assert client.post(prefix+'/broad/confirm',json=dict(job_id=job['id'],revision=state['revision'])).status_code==409


def test_positive_profit_cannot_override_short_history_or_failed_actual_cost_stress(client):
    # The old six-trade example is profitable, but cannot meet the evidence gate.
    _,_,workflow=create_workflow(client);result=run_validation(client,workflow)
    prefix='/api/campaign-workflows/'+workflow['id']
    reviewed=client.patch(prefix+'/review',json=checks(result)).json()
    client.post(prefix+'/confirm',json={'revision':reviewed['review']['revision']})
    start_grid(client,prefix,broad_grid(3,20,1))
    row=client.get(prefix+'/broad/results').json()['items'][0]
    assert float(row['metrics']['total_net_pnl'])==78 and not row['qualifies']
    assert row['screening']['status']=='insufficient_evidence'
    assert selection(client,prefix,[1]).status_code==409
    _,_,workflow=create_broad_workflow(client,fragile=True)
    prefix='/api/campaign-workflows/'+workflow['id'];result=run_validation(client,workflow)
    reviewed=client.patch(prefix+'/review',json=checks(result)).json()
    client.post(prefix+'/confirm',json={'revision':reviewed['review']['revision']})
    start_grid(client,prefix,broad_grid(3,20,1))
    row=client.get(prefix+'/broad/results').json()['items'][0]
    assert float(row['metrics']['total_net_pnl'])==672
    assert float(row['metrics']['is_stress_net_profit'])==-48
    assert [c['id'] for c in row['screening']['checks'] if not c['passed']]==['cost_stress']
    assert not row['qualifies'] and selection(client,prefix,[1]).status_code==409


def test_legacy_pending_grid_requires_rerun_and_confirmed_history_is_preserved(client):
    from alphaquest.campaign_broad import BroadGrid, prepare, candidate
    from alphaquest.research import metadata,dates_for
    from types import SimpleNamespace
    _,_,workflow=passed_mechanics(client);store=client.app.state.campaign_workflows
    prefix='/api/campaign-workflows/'+workflow['id']
    saved,dataset,definition,config,axes,total,request,_=prepare(SimpleNamespace(app=client.app),workflow['id'],BroadGrid.model_validate(broad_grid(3,20,1)))
    job=client.app.state.optimizations.create(request,dataset,definition,config,axes,total,
        metadata(saved['declaration']['plan'],workflow_id=workflow['id'],workflow_phase='is_broad'))
    client.app.state.optimizations.run(job,client.app.state.store,definition,config,dates_for(saved['declaration']['plan']))
    legacy=dict(job_id=job['id'],revision=1,selected_trials=[],selection=[],confirmed_at_utc=None,criterion='IS total_net_pnl > 0 after slippage and commissions')
    with store.runs.connect() as db:
        db.execute('INSERT INTO campaign_broad_jobs VALUES (?,?)',(job['id'],workflow['id']))
        db.execute('INSERT INTO campaign_broad_state VALUES (?,?)',(workflow['id'],json.dumps(legacy)))
    assert selection(client,prefix,[1]).status_code==409
    assert client.get(prefix+'/broad').json()['legacy']
    assert not client.get(prefix+'/broad/results').json()['items'][0]['qualifies']
    # A real earlier confirmation is read with its original identity and rule.
    with store.runs.connect() as db:
        chosen=candidate(store,workflow['id'],job['id'],1,db,legacy=True)
        legacy.update(selected_trials=[1],selection=[chosen],confirmed_at_utc='2026-11-10T00:00:00+00:00')
        db.execute('UPDATE campaign_broad_state SET payload=? WHERE workflow_id=?',(json.dumps(legacy),workflow['id']))
    before={p:sha256(p.read_bytes()).hexdigest() for p in store.runs.root.glob('*/*') if p.is_file()}
    assert client.get(prefix+'/phases/is_narrow').status_code==200
    downloaded=client.get(prefix+'/broad/download');assert downloaded.status_code==200,downloaded.text
    assert downloaded.json()['state']['selection']==[chosen]
    assert client.get(prefix+'/broad/results').json()['items'][0]['legacy_screening']
    assert selection(client,prefix,[]).status_code==409
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}


def test_pending_six_rule_grid_uses_saved_evidence_for_five_rule_selection(client):
    from alphaquest.campaign_broad import BroadGrid, candidate, prepare
    from alphaquest.research import metadata,dates_for
    from alphaquest.workflow_criteria import PREVIOUS_VERSION,policy
    from types import SimpleNamespace
    _,_,workflow=passed_mechanics(client);store=client.app.state.campaign_workflows
    prefix='/api/campaign-workflows/'+workflow['id']
    saved,dataset,definition,config,axes,total,request,_=prepare(
        SimpleNamespace(app=client.app),workflow['id'],BroadGrid.model_validate(broad_grid(3,20,1)))
    original_policy=policy(PREVIOUS_VERSION)
    job=client.app.state.optimizations.create(request,dataset,definition,config,axes,total,
        metadata(saved['declaration']['plan'],workflow_id=workflow['id'],workflow_phase='is_broad',screening_policy=original_policy))
    client.app.state.optimizations.run(job,client.app.state.store,definition,config,dates_for(saved['declaration']['plan']))
    state=dict(job_id=job['id'],revision=1,selected_trials=[],selection=[],confirmed_at_utc=None,
               criterion='All six IS Broad criteria must pass.',screening_policy=original_policy)
    with store.runs.connect() as db:
        db.execute('INSERT INTO campaign_broad_jobs VALUES (?,?)',(job['id'],workflow['id']))
        db.execute('INSERT INTO campaign_broad_state VALUES (?,?)',(workflow['id'],json.dumps(state)))
        previous=json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?',(job['id'],)).fetchone()[0])
        previous['engine_identity']='prior-policy-engine-snapshot'
        db.execute('UPDATE optimizations SET payload=? WHERE id=?',(json.dumps(previous),job['id']))
        original_choice=candidate(store,workflow['id'],job['id'],1,db,target_policy=original_policy)
        historical=dict(state,selected_trials=[1],selection=[original_choice],confirmed_at_utc='2026-11-10T00:00:00+00:00')
        db.execute('UPDATE campaign_broad_state SET payload=? WHERE workflow_id=?',(json.dumps(historical),workflow['id']))
    assert client.get(prefix+'/phases/is_narrow').status_code==200
    assert not client.get(prefix+'/broad').json()['reassessed']
    assert 'admission' not in client.get(prefix+'/broad/results').json()['items'][0]
    with store.runs.connect() as db:
        db.execute('UPDATE campaign_broad_state SET payload=? WHERE workflow_id=?',(json.dumps(state),workflow['id']))
    before={p:sha256(p.read_bytes()).hexdigest() for p in store.runs.root.glob('*/*') if p.is_file()}
    assert client.get(prefix+'/broad').json()['reassessed']
    row=client.get(prefix+'/broad/results').json()['items'][0]
    assert row['screening']['policy']==original_policy and len(row['screening']['checks'])==6
    assert row['admission']['qualifies'] and len(row['admission']['checks'])==5 and row['qualifies']
    assert 'annual_profit_dd' not in [check['id'] for check in row['admission']['checks']]
    artifact=store.runs.root/row['run_id']/'is_screening.json';original=artifact.read_bytes()
    artifact.write_bytes(original+b'\n')
    assert selection(client,prefix,[1]).status_code==409
    artifact.write_bytes(original)
    chosen=selection(client,prefix,[1]);assert chosen.status_code==200,chosen.text
    assert chosen.json()['selection_policy']==policy()
    confirmed=client.post(prefix+'/broad/confirm',json=dict(job_id=job['id'],revision=chosen.json()['revision']))
    assert confirmed.status_code==200,confirmed.text
    assert client.get(prefix+'/phases/is_narrow').status_code==200
    assert client.get('/api/backtests/batches').json()['total']==1
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}
    archived=client.get(prefix+'/broad/results').json()['items'][0]
    assert archived['admission']['qualifies'] and archived['screening']['policy']==original_policy
    assert client.get(prefix+'/broad').json()['reassessed']

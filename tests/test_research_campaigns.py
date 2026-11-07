"""Saved-source campaigns: normal APIs, independent arithmetic and persistence."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from uuid import uuid4

import pytest
from alphaquest.app import create_app
from alphaquest.prop.phase_profiles import rule_version
from research_fixtures import ResearchClient
from test_prop_phases import save_source
from test_prop_analysis_api import wait


def declaration(a, b=None, phase='evaluation'):
    plan = a['run_metadata']['research']['plan']
    profile = dict(profile_id='apex-50k-eod', rule_version=rule_version('apex-50k-eod'))
    settings = dict(calendar=dict(start_dates=['2026-01-05'], coverage_end='2037-01-01'))
    sampling = dict(block_weekdays=1)
    if phase == 'evaluation':
        profile.update(evaluation_price='30', activation_fee='40')
        sampling.update(chain_simulations=8, chain_seed=45)
    else:
        settings.update(horizon_calendar_days=14, receipt_delay_calendar_days=4,
                        constraints=dict(maximum_account_breach_probability=0), bootstrap_replicates=100)
    return dict(campaign_id=uuid4().hex, phase=phase, profile=profile,
        sources=[dict(backtest_id=s['id'], sizes=[1, 3]) for s in [a, *([b] if b else [])]],
        maximum_candidates=4, is_window=dict(first_session=plan['is_start'], last_session=plan['is_end']),
        simulation=dict(simulations=8, seed=42), sampling=sampling, costs=dict(mode='source'), search_settings=settings)


@pytest.fixture(scope='module')
def library(tmp_path_factory):
    root = tmp_path_factory.mktemp('campaign-library')
    with ResearchClient(create_app(root/'datasets.sqlite3')) as client:
        a = save_source(client, days=8); b = save_source(client, green=2, days=8)
        yield client, a, b, root


def create(client, body):
    r = client.post('/api/research-campaigns', json=body)
    assert r.status_code == 201, r.text
    return r.json()


def run(client, id):
    r = client.post(f'/api/research-campaigns/{id}/run')
    assert r.status_code == 202, r.text
    analysis_id = r.json()['analysis_id']
    assert wait(client, analysis_id)['status'] == 'complete', wait(client, analysis_id)
    return client.get(f'/api/research-campaigns/{id}').json()


def files(root):
    return {str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest()
            for folder in ('backtest_runs', 'prop_analyses') for p in (root/folder).rglob('*')
            if p.is_file() and '.sqlite3' not in p.name}


def test_normal_campaigns_independent_math_reuse_freeze_and_reopen(library, monkeypatch):
    client, a, b, root = library
    before = files(root)
    evidence = []
    for phase in ('evaluation', 'funded'):
        request = declaration(a, b, phase)
        # Evaluation and funded candidate sets need not match.
        if phase == 'evaluation':
            request['sources'][0]['sizes'] = [3, 10]
            request['sources'][1]['sizes'] = [3, 10]
        created = create(client, request); id = created['campaign_id']
        assert created['manifest']['candidate_search_count'] == 4
        assert client.post(f'/api/research-campaigns/{id}/check').status_code == 200
        saved = run(client, id); analysis_id = saved['analysis_id']
        result = client.get(f'/api/research-campaigns/{id}/exports/results.json').json()
        candidates = result['candidates']
        if phase == 'funded':
            assert sorted(c['metrics']['expected_payouts'] for c in candidates) == [0, 0, 0, 1500]
            best = next(c for c in candidates if c['candidate_id'] == result['winner'])
            assert best['metrics']['expected_pending_cash'] == 1500
            selected = [result['winner']]
        else:
            # Constant $300/MNQ A and $100/MNQ B; target $3000,
            # Monday start + one activation session => readiness 2,4,7,15 days (activation/readiness skip weekends).
            assert sorted(c['metrics']['cost_per_funded'] for c in candidates) == [70]*4
            assert sorted(c['metrics']['expected_calendar_days_to_funded'] for c in candidates) == [2,4,7,15]
            assert len(result['frontier']) == 1
            selected = result['frontier']
        export = client.get(f'/api/research-campaigns/{id}/exports/results.csv')
        assert export.status_code == 200 and 'candidate_id' in export.text
        assert client.get(f'/api/research-campaigns/{id}/exports/analysis.zip').status_code == 200
        frozen = client.post(f'/api/research-campaigns/{id}/freeze', json=dict(candidate_ids=selected, rationale='Independent synthetic arithmetic verified.'))
        assert frozen.status_code == 200, frozen.text
        assert client.post(f'/api/research-campaigns/{id}/freeze', json=dict(candidate_ids=selected, rationale='Independent synthetic arithmetic verified.')).json() == frozen.json()
        assert client.post(f'/api/research-campaigns/{id}/freeze', json=dict(candidate_ids=selected, rationale='changed')).status_code == 409
        assert client.delete('/api/prop-analyses/'+analysis_id).status_code == 409
        assert client.delete('/api/backtests/'+b['id']).status_code == 409
        request2 = deepcopy(request); request2['campaign_id'] = uuid4().hex
        reused = run(client, create(client, request2)['campaign_id'])
        assert reused['analysis_id'] == analysis_id
        assert create(client, request)['analysis_id'] == analysis_id
        # Byte-for-byte preserved outputs, with numerical functions poisoned.
        module = 'alphaquest.prop.'+phase+'_optimization.optimize_'+phase
        with monkeypatch.context() as m:
            m.setattr(module, lambda *a, **k: pytest.fail('Reopen recalculated'))
            assert client.get(f'/api/research-campaigns/{id}/exports/results.json').json() == result
            assert client.post(f'/api/research-campaigns/{id}/run').json()['analysis_id'] == analysis_id
        evidence.append(dict(campaign_id=id, analysis_id=analysis_id, request=request,
                             selection=selected, frozen=frozen.json(), results=result))
    assert all(sha256((root/name).read_bytes()).hexdigest() == value for name,value in before.items())
    (root/'campaign-verification.json').write_text(json.dumps(dict(synthetic=True, campaigns=evidence,
        unchanged_files=len(before), reopened_without_recalculation=True), indent=2))
    from alphaquest.prop.store import AnalysisStore
    from alphaquest.research_campaigns import CampaignStore
    store = AnalysisStore(root, recover_interrupted=False)
    try:
        reopened = CampaignStore(client.app.state.runs, store, client.app.state.optimizations)
        assert reopened.get(evidence[0]['campaign_id'])['frozen'] == evidence[0]['frozen']
        assert reopened.report(evidence[1]['campaign_id'])['calculations'] == evidence[1]['results']
    finally:
        store.close()


@pytest.mark.parametrize('mutate', [
    lambda r:r['sources'].append(r['sources'][0]),
    lambda r:r['sources'][0].update(sizes=[1,1]),
    lambda r:r['sources'][0].update(sizes=[1.5]),
    lambda r:r['profile'].update(profile_id='unknown'),
    lambda r:r['profile'].update(funded_payout=100),
    lambda r:r['is_window'].update(last_session='2030-01-01'),
    lambda r:r['search_settings'].update(evaluation_pass_probability=0),
])
def test_reject_invalid_campaigns(library, mutate):
    client,a,b,_ = library
    request = declaration(a,b); mutate(request)
    r = client.post('/api/research-campaigns', json=request)
    assert r.status_code == 422, r.text


def test_reject_mixed_source_risk_costs_and_oos(library):
    client,a,b,_ = library
    runs = client.app.state.runs
    with runs.connect() as db:
        original = db.execute('SELECT manifest FROM runs WHERE id=?', (b['id'],)).fetchone()[0]
    mutations = [lambda r:r['run_metadata']['research'].update(phase='oos'),
        lambda r:r['run_metadata']['research']['plan'].update(is_start='2026-01-06'),
        lambda r:r['execution_settings'].update(commission_per_contract_per_side='1'),
        lambda r:r['run_metadata']['strategy']['parameters'].update(use_vol_sizing=True),
        lambda r:r.pop('intratrade_risk'),
        lambda r:r['run_metadata']['dataset'].update(symbol='ES')]
    try:
        for mutate in mutations:
            record = json.loads(original); mutate(record)
            with runs.connect() as db: db.execute('UPDATE runs SET manifest=? WHERE id=?', (json.dumps(record),b['id']))
            r = client.post('/api/research-campaigns',json=declaration(a,b))
            assert r.status_code == 422, r.text
    finally:
        with runs.connect() as db: db.execute('UPDATE runs SET manifest=? WHERE id=?', (original,b['id']))


def test_duplicate_alias_and_legacy_budget_does_not_limit_sizes(library):
    client,a,b,_ = library
    request = declaration(a,b); request['maximum_candidates'] = 10
    request['sources'].append(dict(backtest_id=a['id'],sizes=[1]))
    r = client.post('/api/research-campaigns',json=request)
    assert r.status_code == 422 and 'Duplicate candidate' in r.text
    request = declaration(a,b); request['maximum_candidates'] = 3
    r = client.post('/api/research-campaigns',json=request)
    assert r.status_code == 201, r.text
    assert r.json()['manifest']['candidate_search_count'] == 4


def test_interrupted_job_recovery_and_no_oos_reads(library, monkeypatch):
    client,a,b,root = library
    request = declaration(a,phase='funded'); request['simulation']['seed'] = 199
    id = create(client,request)['campaign_id']
    store = client.app.state.prop_analyses
    # Simulate interruption after enqueue, before the worker can publish.
    with monkeypatch.context() as m:
        m.setattr(store.worker,'submit',lambda *a,**k:None)
        first = client.post(f'/api/research-campaigns/{id}/run').json()['analysis_id']
    from alphaquest.prop.store import AnalysisStore
    recovered = AnalysisStore(root)
    recovered.close()
    assert client.get(f'/api/research-campaigns/{id}').json()['status'] == 'error'
    # Campaign run needs only saved IS files; poison any dataset loader and OOS action.
    monkeypatch.setattr(client.app.state.store,'get',lambda *a,**k:pytest.fail('Dataset/OOS inspected'))
    second = run(client,id)['analysis_id']
    assert second != first
    assert store.get(first)['status'] == 'error'
    history=client.get(f'/api/research-campaigns/{id}/attempts').json()['items']
    assert [a['id'] for a in history]==[first,second]
    assert [a['status'] for a in history]==['error','complete']
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM campaign_analyses WHERE campaign_id=?',(id,)).fetchone()[0] == 2


def test_numerical_identity_and_declared_immutability(library, monkeypatch):
    client,a,b,_ = library
    request = declaration(a,b); saved = create(client,request); id = saved['campaign_id']
    other = deepcopy(request); other['simulation']['seed'] += 1
    assert client.post('/api/research-campaigns',json=other).status_code == 409
    identity = saved['manifest']['numerical_implementation']
    assert not any('web' in k or k.endswith('.md') for k in identity['files'])
    monkeypatch.setattr('alphaquest.prop.evaluation_optimization.implementation_identity',lambda:dict(changed=True))
    assert client.post(f'/api/research-campaigns/{id}/run').status_code == 409


def make_jobs(client):
    from test_vwap_pullback import scenario, parameters
    from alphaquest.reporting import json_value
    from test_optimization import wait_job
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    for day in (5,6,7):
        for bar in scenario():
            stamp=bar.timestamp_utc.replace(day=day)
            # Explicitly huge synthetic swings yield fast, independently
            # identifiable account breaches in both source strategies.
            prices=[str(int(value)*100) for value in bar.source_fields[2:6]]
            lines.append(','.join([stamp.strftime('%m/%d/%Y'),stamp.strftime('%H:%M'),*prices,*bar.source_fields[6:]]))
        # Closing bars ensure the other strategy cannot carry a late entry
        # overnight; these are actual synthetic bars, not rewritten trades.
        for minute in (4,5,6):
            lines.append(f'01/{day:02}/2026,15:{minute:02},12000,12000,12000,12000,1,0,0')
    result=client.post('/api/datasets',params=dict(filename='SYNTHETIC-evaluation-two-strategies.csv',
        name='SYNTHETIC Evaluation two strategies',source_timezone='UTC',tick_size='.25',point_value='20',symbol='NQ'),content=('\n'.join(lines)+'\n').encode())
    assert result.status_code==201,result.text
    dataset=result.json()['id']
    vwap_params=json.loads(json.dumps(asdict(parameters(day_reset_time=700)),default=json_value))
    execution=dict(initial_capital='10000',tick_size='.25',point_value='20',slippage_ticks=0,commission_per_contract_per_side='0')
    cases=[('vwap_pullback_risk_sizing',vwap_params),
           ('consecutive_green_hold',dict(green_bar_count=1,hold_minutes=1,contracts=1))]
    trials=[];jobs=[]
    for strategy,params in cases:
        body=dict(dataset_id=dataset,strategy_id=strategy,execution_settings=execution,
            method='exhaustive',workers=1,reuse_results=False,
            parameter_ranges={k:dict(start=v,end=v,step='0' if isinstance(v,str) else 0) for k,v in params.items()})
        response=client.post('/api/optimizations',json=body)
        assert response.status_code==202,response.text
        job=wait_job(client,response.json()['id']);assert job['status']=='complete',job
        jobs.append(job['id'])
        items=client.get(f"/api/optimizations/{job['id']}/results").json()['items']
        assert len(items)==1
        response=client.get('/api/backtests/'+items[0]['run_id'])
        assert response.status_code==200,response.text
        trials.append(response.json())
    return trials, jobs


@pytest.mark.parametrize('phase', ['evaluation', 'funded'])
def test_campaign_multiple_strategies_jobs_complete_grid_and_determinism(tmp_path, phase):
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        trials,jobs = make_jobs(client)
        request = declaration(*trials, phase)
        request['sources'] = [dict(optimization_id=id, sizes=[1,3]) for id in jobs]
        saved = create(client,request); id = saved['campaign_id']
        assert saved['manifest']['candidate_search_count'] == 4
        assert len(saved['manifest']['optimization_grids']) == 2
        run(client,id)
        results = client.get(f'/api/research-campaigns/{id}/exports/results.json').json()
        assert {r['manifest']['strategy']['id'] for r in results['candidates']} == {'consecutive_green_hold','vwap_pullback_risk_sizing'}
        assert {o['optimization_id'] for r in results['candidates'] for o in r['origin_trials']} == set(jobs)
        assert {r['manifest']['configuration']['micros'] for r in results['candidates']} == {1,3}
        # Stable expansion and calculation reuse when the submitted job order changes.
        reverse = deepcopy(request); reverse['campaign_id'] = uuid4().hex; reverse['sources'].reverse()
        second = run(client,create(client,reverse)['campaign_id'])
        assert second['analysis_id'] == client.get(f'/api/research-campaigns/{id}').json()['analysis_id']
        # Direct backtest plus the same trial is an explicit duplicate, not extra evidence.
        duplicate = deepcopy(request); duplicate['campaign_id'] = uuid4().hex; duplicate['maximum_candidates'] = 8
        duplicate['sources'].append(dict(backtest_id=trials[0]['id'], sizes=[1]))
        bad = client.post('/api/research-campaigns',json=duplicate)
        assert bad.status_code == 422 and 'Duplicate candidate' in bad.text
        missing = deepcopy(request);missing['campaign_id'] = uuid4().hex;missing['sources'][0]['trials'] = [999999]
        assert client.post('/api/research-campaigns',json=missing).status_code == 422
        assert client.delete('/api/optimizations/'+jobs[0]).status_code == 409
        # Saved report reads do not need a live strategy, job or data lookup.
        (tmp_path/'cross-job-campaign.json').write_text(json.dumps(dict(request=request,campaign_id=id,
            analysis_id=second['analysis_id'],candidate_count=4,strategies=sorted({r['manifest']['strategy']['id'] for r in results['candidates']})),indent=2))


def test_phase_sets_are_independent_and_no_joint_selection(library,monkeypatch):
    client,a,b,_ = library
    def forbidden(*a,**kw):pytest.fail('An unrelated phase or joint selector was called')
    monkeypatch.setattr('alphaquest.prop.joint_sizing.select',forbidden)
    for phase,source,opposite in [('evaluation',a,'funded'),('funded',b,'evaluation')]:
        request=declaration(source,phase=phase);request['simulation']['seed']=235
        id=create(client,request)['campaign_id']
        with monkeypatch.context() as m:
            m.setattr('alphaquest.prop.'+opposite+'_optimization.optimize_'+opposite,forbidden)
            saved=run(client,id)
        assert saved['manifest']['phase']==phase
        assert {r['source']['source_backtest_id'] for r in saved['manifest']['request']['candidates']}=={source['id']}


def test_queue_limits_and_not_completed_freeze(library,monkeypatch):
    client,a,_,_=library;store=client.app.state.prop_analyses
    request=declaration(a);request['simulation']['seed']=555
    id=create(client,request)['campaign_id']
    assert client.get(f'/api/research-campaigns/{id}/candidates').status_code==409
    assert client.post(f'/api/research-campaigns/{id}/freeze',json=dict(candidate_ids=['bogus'],rationale='premature')).status_code==409
    jobs=[uuid4().hex for _ in range(8)]
    try:
        with store.connect() as db:
            db.executemany('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',[(j,j,a['id'],'2026-01-01','queued','fixture',None) for j in jobs])
        assert client.post(f'/api/research-campaigns/{id}/run').status_code==409
    finally:
        with store.connect() as db:db.executemany('DELETE FROM analyses WHERE id=?',[(j,) for j in jobs])


def test_changed_source_blocks_run_but_saved_reports_reopen(library):
    client,a,_,_=library
    request=declaration(a,phase='funded');request['simulation']['seed']=501
    id=create(client,request)['campaign_id']
    path=client.app.state.runs.root/a['id']/'trades.csv';before=path.read_bytes()
    try:
        path.write_bytes(before.replace(b'3000',b'3001'))
        assert client.post(f'/api/research-campaigns/{id}/run').status_code in (409,422)
    finally:path.write_bytes(before)


def test_duplicate_report_and_timezone_aliases(library):
    client,a,_,_=library
    # Ordinary rerun, identical strategy/parameters on the same saved data.
    response=client.post('/api/backtests',json=dict(dataset_id=a['run_metadata']['dataset']['id'],
        strategy_id=a['run_metadata']['strategy']['id'],strategy_parameters=a['run_metadata']['strategy']['parameters'],
        execution_settings=a['execution_settings'],reuse_results=False))
    assert response.status_code==201,response.text
    again=response.json()
    assert again['id']!=a['id']
    request=declaration(a,again)
    response=client.post('/api/research-campaigns',json=request)
    assert response.status_code==422 and 'Duplicate candidate' in response.text
    request=declaration(a,a)
    request['sources'][1]['export_timezone']='UTC'  # no export: irrelevant timezone cannot create new evidence
    response=client.post('/api/research-campaigns',json=request)
    assert response.status_code==422 and 'Duplicate candidate' in response.text


def test_incompatible_measured_and_ohlc_risk_rejected(library,tmp_path):
    from test_prop_analysis_api import export_for
    client,a,b,_=library
    # Synthetic companion reconciles real IDs, times, quantities and net costs;
    # its supplied measured excursions must not mix with OHLC upper bounds.
    export=export_for(client,b,tmp_path)
    request=declaration(a,b)
    request['sources'][1].update(trade_file=str(export),export_timezone='UTC')
    response=client.post('/api/research-campaigns',json=request)
    assert response.status_code==422 and 'risk conventions' in response.text

"""Independent mathematical oracles plus normal saved-source/report integration."""
from dataclasses import asdict, replace
from datetime import date, timedelta
from hashlib import sha256
import io
import itertools
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import zipfile

import pytest

from alphaquest.app import create_app
from alphaquest.prop.evaluation_optimization import (
    AcquisitionCalendar, EvaluationCandidate, EvaluationSearch, SequentialRetry,
    acquisition_metrics, check_search, optimize_evaluation, parse_request, pareto_sort,
)
from alphaquest.prop.phase_profiles import (
    EvaluationProfile, EvaluationSamplingConfig, SavedTradeSource, SimulationConfig,
    SourceCosts, rule_version,
)
from research_fixtures import ResearchClient
from test_prop_analysis_api import wait
from test_prop_phases import save_source


def profile(fee='30', activation='40'):
    return EvaluationProfile('apex-50k-eod', rule_version('apex-50k-eod'), fee, activation)


def calendar(start='2026-01-05', closures=()):
    return AcquisitionCalendar((start,), '2037-01-01', closures)


def attempts(outcomes, durations, censored=0):
    return SimpleNamespace(outcomes=outcomes, duration_weekdays=durations,
                           censoring=SimpleNamespace(censored_paths=censored))


def metrics(outcomes, durations, *, retry=None, cal=None, count=20000, censored=0):
    return acquisition_metrics(attempts(outcomes, durations, censored), profile(),
        retry or SequentialRetry(activation_delay_sessions=0), cal or calendar(),
        EvaluationSamplingConfig(chain_simulations=count))


def row(id, cost, days, status='estimated'):
    return dict(candidate_id=id, status=status,
        metrics=dict(cost_per_funded=cost, expected_calendar_days_to_funded=days))


def test_complete_nonconvex_frontier_ties_and_dominated_independent_of_order():
    # B lies above the A–C chord: no linear weight selects it uniquely,
    # nevertheless B is nondominated and must be retained.
    points = [row('A',100,10), row('B',160,8), row('C',180,4), row('D',190,12), row('A2',100,10)]
    expected = None
    for permutation in itertools.permutations(points):
        result = pareto_sort([dict(r) for r in permutation])
        assert result['frontier'] == ['A','A2','B','C']
        assert [m['usd_per_calendar_day_saved'] for m in result['marginal_acceleration_cost']] == [None,30,5]
        assert next(r for r in result['candidates'] if r['candidate_id']=='D')['dominated'] is True
        assert result['winner'] is None and result['certified_frontier'] is False
        encoded = json.dumps(result, sort_keys=True, allow_nan=False)
        if expected is None: expected = encoded
        assert encoded == expected


def test_equal_time_equal_cost_and_unresolved_are_not_false_ties_or_exclusions():
    result = pareto_sort([row('A',100,10), row('same_time',120,10), row('same_cost',100,12),
        row('unresolved',None,None,'censored')])
    assert result['frontier'] == ['A']
    assert result['unresolved_candidates'] == ['unresolved']
    assert result['candidates'][-1]['dominated'] is None
    assert all(r['robust_dominated'] is None for r in result['candidates'])


def test_full_pass_calendar_weekends_holiday_and_activation_cost():
    # Fri Jan 9 pass, Mon Jan 12 declared closed, Tue activation, Wed usable.
    r = metrics(['passed'], [1], retry=SequentialRetry(activation_delay_sessions=1),
                cal=calendar('2026-01-09', ('2026-01-12',)), count=8)
    m = r['metrics']
    assert (m['cost_per_funded'], m['expected_attempts_per_funded']) == (70,1)
    assert m['expected_calendar_days_to_funded'] == m['median_calendar_days_to_funded'] == m['p90_calendar_days_to_funded'] == 5
    assert m['funded_accounts_per_30_calendar_days'] == 6
    assert m['probability_funded_by_day_30'] == m['probability_funded_by_day_60'] == 1
    assert all(p['cost_accrued']=='70' and p['funded_date']=='2026-01-14' for p in r['paths'])
    assert r['uncertainty']['calendar_mean_se'] == 0


def test_start_on_weekend_and_dst_is_civil_days():
    # Saturday before US DST: Monday trading, Tuesday usable = three civil days.
    r = metrics(['passed'], [1], cal=calendar('2026-03-07'), count=8)
    assert r['metrics']['expected_calendar_days_to_funded'] == 3
    assert r['paths'][0]['funded_date'] == '2026-03-10'


def independent_ready(failures, fail_duration, pass_duration, delay=0):
    """Scalar standard-library dated oracle, no production calendar helpers."""
    cursor = date(2026,1,5)
    for duration in [fail_duration]*failures + [pass_duration]:
        used=0
        while used < duration:
            if cursor.weekday()<5: used += 1
            cursor += timedelta(days=1)
        if used and failures:
            # Delay applies after every failed attempt, never after success.
            failures -= 1
            cursor += timedelta(days=delay)
    while cursor.weekday()>=5: cursor+=timedelta(days=1)
    return (cursor-date(2026,1,5)).days


def test_geometric_oracle_uses_failed_duration_and_retry_overhead():
    # p=1/2, failed attempts 3 sessions, successful attempts 1 session.
    # Fee E[C]=30/(1/2)+40=100, attempts E[K]=2. Calendar oracle sums
    # the geometric law independently; truncation after 60 failures < 1e-14 days.
    r = metrics(['blown','passed'], [3,1], retry=SequentialRetry(retry_delay_calendar_days=2, activation_delay_sessions=0))
    distribution = [(independent_ready(k,3,1,2), 2.**(-k-1)) for k in range(60)]
    expected = sum(t*p for t,p in distribution)
    assert r['metrics']['cost_per_funded'] == 100
    assert r['metrics']['expected_attempts_per_funded'] == 2
    assert abs(r['metrics']['expected_calendar_days_to_funded']-expected) < .25
    for day in (30,60):
        actual=r['metrics'][f'probability_funded_by_day_{day}']
        assert abs(actual-sum(p for t,p in distribution if t<=day)) < .01
    for path in r['paths']:
        assert path['observed_calendar_days']==independent_ready(path['attempts']-1,3,1,2)
        assert path['cost_accrued']==str(30*path['attempts']+40)
    # Different failed duration changes time, not p/cost.
    faster=metrics(['blown','passed'], [1,1])
    assert faster['metrics']['cost_per_funded']==100
    assert faster['metrics']['expected_calendar_days_to_funded'] < expected


def test_zero_pass_or_censored_attempts_have_no_finite_acquisition_mean():
    for result in [metrics(['timeout'],[21],count=8),
                   metrics(['passed','timeout'],[1,21],count=8,censored=1)]:
        assert result['status']=='unresolved'
        assert result['metrics']['cost_per_funded'] is None
        assert result['metrics']['expected_calendar_days_to_funded'] is None
        assert result['metrics']['expected_attempts_per_funded'] is None
        assert result['metrics']['probability_funded_by_day_30_bounds']==[0,1]
    assert metrics(['timeout'],[21],count=8)['metrics']['pass_probability_ci'][1] > 0


def test_censored_chains_do_not_average_only_successes_or_pay_activation_early():
    r=metrics(['blown','passed'],[3,1],retry=SequentialRetry(max_attempts=1, activation_delay_sessions=0),count=256)
    assert 0<r['censoring']['chain_paths']<256
    assert r['metrics']['cost_per_funded'] is r['metrics']['expected_calendar_days_to_funded'] is None
    assert r['metrics']['p90_calendar_days_to_funded'] is None
    assert r['metrics']['probability_funded_by_day_30'] is None
    for p in r['paths']:
        assert p['cost_accrued']==('70' if p['event']=='funded' else '30')
    waiting=metrics(['passed'],[1],retry=SequentialRetry(activation_delay_sessions=4,max_calendar_days=2),count=8)
    assert waiting['paths'][0]['pending_activation'] is True
    assert waiting['paths'][0]['cost_accrued']=='30'
    # Fee is payable Friday but readiness Monday lies beyond Saturday cutoff.
    pending=metrics(['passed'],[1],retry=SequentialRetry(activation_delay_sessions=0,max_calendar_days=1),cal=calendar('2026-01-09'),count=8)
    assert pending['paths'][0]['activation_paid'] is True
    assert pending['paths'][0]['pending_readiness'] is True
    assert pending['paths'][0]['cost_accrued']=='70'
    assert pending['metrics']['cost_per_funded'] is None


def test_funding_exactly_day_30_and_60_is_inclusive():
    # Monday start, 22 sessions finishes Tuesday Feb 3; Wed Feb 4 = day 30.
    r=metrics(['passed'],[22],count=8)
    assert r['metrics']['expected_calendar_days_to_funded']==30
    assert r['metrics']['probability_funded_by_day_30']==1
    r=metrics(['passed'],[44],count=8)
    assert r['metrics']['expected_calendar_days_to_funded']==60
    assert r['metrics']['probability_funded_by_day_30']==0
    assert r['metrics']['probability_funded_by_day_60']==1


def request_for(a,b):
    def c(source,size,fee):
        return EvaluationCandidate(SavedTradeSource(source['id']), profile(fee,'40'),size,
            SimulationConfig(simulations=8),EvaluationSamplingConfig(chain_simulations=8),SourceCosts(mode='source'))
    return json.loads(json.dumps(asdict(EvaluationSearch(a['id'], (c(a,10,'100'),c(a,5,'60'),c(b,10,'30'),c(b,5,'50')), calendar()))))


@pytest.fixture(scope='module')
def library(tmp_path_factory):
    root=tmp_path_factory.mktemp('evaluation-search-library')
    with ResearchClient(create_app(root/'datasets.sqlite3')) as client:
        a=save_source(client,days=8);b=save_source(client,green=2,days=8)
        yield client,a,b,root


def test_normal_check_run_download_reopen_and_independence(library, monkeypatch):
    client,a,b,root=library
    from alphaquest.prop import native_analysis, joint_sizing, funded_profiles, source
    def forbidden(*args,**kwargs):pytest.fail('Funded or joint selection was called')
    monkeypatch.setattr(native_analysis,'funded',forbidden)
    monkeypatch.setattr(native_analysis,'account_backend',forbidden)
    monkeypatch.setattr(native_analysis,'calculate',forbidden)
    monkeypatch.setattr(joint_sizing,'select',forbidden)
    monkeypatch.setattr(funded_profiles,'simulate_funded_profile',forbidden)
    monkeypatch.setattr(source,'matching_exports',forbidden)
    before={str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for folder in (root/'backtest_runs',root/'prop_analyses') for p in folder.rglob('*') if p.is_file() and p.suffix not in ('.sqlite3','-wal','-shm')}
    body=request_for(a,b)
    check=client.post('/api/prop-analyses/check',json=body)
    assert check.status_code==200,check.text
    job=client.post('/api/prop-analyses',json=body)
    assert job.status_code==202,job.text
    id=job.json()['id'];assert wait(client,id)['status']=='complete',wait(client,id)
    response=client.get(f'/api/prop-analyses/{id}/downloads/report.json')
    report=response.json();calc=report['calculations']
    # Independent actual source arithmetic: A=$300/MNQ/session; B=$100.
    # Sizes 10,5 and B10,B5 reach $3000 in 1,2,3,6 sessions. One
    # activation session then next open session gives 2,3,4,9 calendar days.
    observed=sorted((r['metrics']['cost_per_funded'],r['metrics']['expected_calendar_days_to_funded']) for r in calc['candidates'])
    assert observed==[(70,4),(90,9),(100,3),(140,2)]
    assert len(calc['frontier'])==3
    assert [m['usd_per_calendar_day_saved'] for m in calc['marginal_acceleration_cost']]==[30,40]
    download=client.get(f'/api/prop-analyses/{id}/downloads/analysis.zip').content
    with zipfile.ZipFile(io.BytesIO(download)) as archive:
        assert 'phase_metrics.csv' in archive.namelist()
        assert json.loads(archive.read('calculations.json'))==calc
    for s in (a,b):
        listing=client.get('/api/prop-analyses/sources/'+s['id'],params=dict(discover_exports=False)).json()
        assert id in [r['id'] for r in listing['analyses']]
    assert client.get(f'/api/prop-analyses/{id}/files/phase_metrics.csv').status_code==200
    # Candidate order has no effect on identity; source navigation isn't a score.
    body['candidates'].reverse()
    assert client.post('/api/prop-analyses',json=body).json()['id']==id
    monkeypatch.setattr('alphaquest.prop.evaluation_optimization.optimize_evaluation',forbidden)
    assert client.get(f'/api/prop-analyses/{id}/downloads/report.json').content==response.content
    from alphaquest.prop.store import AnalysisStore
    reopened=AnalysisStore(root,recover_interrupted=False)
    try:assert reopened.fingerprint(id) is not None
    finally:reopened.close()
    assert all(sha256((root/name).read_bytes()).hexdigest()==value for name,value in before.items())
    (root/'evaluation-search-request.json').write_text(json.dumps(body,indent=2))
    (root/'evaluation-search-verification.json').write_text(json.dumps(dict(synthetic=True,
        analysis_id=id,source_ids=[a['id'],b['id']],expected_points=[[70,4],[90,9],[100,3],[140,2]],
        observed_points=observed,frontier=calc['frontier'],unchanged_files=len(before),
        source_check=check.json(),reopened_without_recalculation=True),indent=2))


def test_request_rejections_and_cache_dimensions(library):
    client,a,b,_=library
    body=request_for(a,b)
    for mutation in [lambda x:x.update(funded_strategy='anything'),
                     lambda x:x['candidates'][0].update(funded_profile={}),
                     lambda x:x['candidates'][0]['retry'].update(model='finite_budget'),
                     lambda x:x['candidates'][0]['profile'].update(profile_id='lucidflex-50k'),
                     lambda x:x['candidates'][0].update(micros=0),
                     lambda x:x['candidates'][0]['source'].update(source_backtest_id=12),
                     lambda x:x['calendar'].update(closures=['20260112']),
                     lambda x:x['calendar'].update(start_dates=['20260105']),
                     lambda x:x['candidates'].append(x['candidates'][0]),
                     lambda x:x['calendar'].update(coverage_end='2026-01-06')]:
        copy=json.loads(json.dumps(body));mutation(copy)
        assert client.post('/api/prop-analyses/check',json=copy).status_code==422
    from alphaquest.prop.evaluation_optimization import search_key
    search=parse_request(body);checks=check_search(client.app.state.runs,search)
    base=search_key(search,checks)
    changed=replace(search,calendar=replace(search.calendar,closures=('2026-01-12',)))
    assert search_key(changed,checks)!=base
    for field,value in [('micros',6),('profile',profile('61')),
                        ('sampling',EvaluationSamplingConfig(chain_simulations=10)),
                        ('retry',SequentialRetry(retry_delay_calendar_days=1))]:
        c=replace(search.candidates[0],**{field:value})
        new=replace(search,candidates=(c,*search.candidates[1:]))
        assert search_key(new,check_search(client.app.state.runs,new))!=base


def test_all_sources_protected_while_search_runs(library,monkeypatch):
    client,a,b,_=library
    import alphaquest.prop.evaluation_optimization as module
    original=module.optimize_evaluation;entered=Event();release=Event()
    def paused(*args,**kwargs):
        entered.set();assert release.wait(10)
        return original(*args,**kwargs)
    monkeypatch.setattr(module,'optimize_evaluation',paused)
    body=request_for(a,b);body['candidates'][0]['profile']['evaluation_price']='101'
    try:
        response=client.post('/api/prop-analyses',json=body);assert response.status_code==202
        assert entered.wait(10)
        assert {a['id'],b['id']} <= client.app.state.prop_analyses.active_sources()
        for s in (a,b):assert client.delete('/api/backtests/'+s['id']).status_code==409
    finally:release.set()
    assert wait(client,response.json()['id'])['status']=='complete'


@pytest.mark.parametrize('phase', ['evaluation', 'funded'])
def test_two_strategies_two_saved_jobs_have_complete_membership(tmp_path, phase):
    from test_vwap_pullback import scenario, parameters
    from alphaquest.reporting import json_value
    from test_optimization import wait_job
    from alphaquest.prop.adapter import source_record
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
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
            trials.append(source_record(client.app.state.runs,items[0]['run_id']))
        body=request_for(*trials)
        if phase == 'funded':
            from test_funded_optimization import search_for, body as funded_body
            body=funded_body(search_for(*trials))
        checked=client.post('/api/prop-analyses/check',json=body)
        assert checked.status_code==200,checked.text
        result=client.post('/api/prop-analyses',json=body)
        id=result.json()['id'];assert wait(client,id)['status']=='complete',wait(client,id)
        report=client.get(f'/api/prop-analyses/{id}/downloads/report.json').json()
        candidates=report['calculations']['candidates']
        assert len(candidates)==4
        assert {origin['optimization_id'] for c in candidates for origin in c['origin_trials']} == set(jobs)
        assert {c['manifest']['strategy']['id'] for c in candidates}=={c[0] for c in cases}
        assert {c['manifest']['configuration']['source']['source_backtest_id'] for c in candidates}=={t['id'] for t in trials}
        (tmp_path/'cross-job-verification.json').write_text(json.dumps(dict(jobs=jobs,
            source_ids=[t['id'] for t in trials],analysis_id=id,full_candidate_count=4),indent=2))


def test_oos_and_unequal_research_windows_reject_before_simulation(library):
    client,a,b,_=library
    search=parse_request(request_for(a,b))
    from test_prop_phase_profiles import SingleSource
    oos=json.loads(json.dumps(a));oos['run_metadata']['research']['phase']='oos'
    with pytest.raises(ValueError,match='declared IS'):
        check_search(SingleSource(client.app.state.runs,oos),search)
    from alphaquest.prop.phase_profiles import ResearchPeriod
    changed=replace(search.candidates[0],period=ResearchPeriod('2026-01-05','2026-01-06'))
    with pytest.raises(ValueError,match='identical dataset'):
        check_search(client.app.state.runs,replace(search,candidates=(changed,*search.candidates[1:])))


def test_equal_weight_start_cohort_has_conditional_standard_error():
    cal=AcquisitionCalendar(('2026-01-09','2026-01-05'),'2037-01-01')
    result=metrics(['passed'],[1],cal=cal,count=8)
    # Fri -> Mon = 3 days; Mon -> Tue = 1 day. Fixed equal allocation,
    # deterministic within each stratum: exact mixture mean 2, MC error 0.
    assert result['metrics']['expected_calendar_days_to_funded']==2
    assert result['uncertainty']['calendar_mean_se']==0
    assert result['uncertainty']['probability_funded_by_day_30_ci'] is None


def test_missing_saved_artifact_cannot_satisfy_reuse(library):
    client,a,b,_=library
    body=request_for(a,b)
    body['candidates'][0]['profile']['evaluation_price']='103'
    response=client.post('/api/prop-analyses',json=body)
    assert response.status_code==202,response.text
    first=response.json()['id'];assert wait(client,first)['status']=='complete'
    # Damage only the new report made by this test, never the saved demonstration.
    (client.app.state.prop_analyses.root/first/'source_checks.json').unlink()
    response=client.post('/api/prop-analyses',json=body)
    assert response.status_code==202,response.text
    second=response.json()['id']
    assert second!=first
    assert wait(client,second)['status']=='complete'
    assert client.app.state.prop_analyses.fingerprint(second) is not None


def test_funded_administrative_metadata_cannot_change_candidate_or_cache_identity(library):
    client,a,b,_=library
    from test_prop_phase_profiles import SingleSource
    from alphaquest.prop.evaluation_optimization import search_key
    search=parse_request(request_for(a,b))
    search=replace(search,candidates=(search.candidates[0],))
    before=check_search(SingleSource(client.app.state.runs,a),search)
    modified=json.loads(json.dumps(a))
    modified['run_metadata']['automatic_prop_analysis']={'historical_net':9999999,'funded_micros':40}
    after=check_search(SingleSource(client.app.state.runs,modified),search)
    assert before[0]['manifest']['source']['manifest_sha256'] != after[0]['manifest']['source']['manifest_sha256']
    assert before[0]['candidate_id'] == after[0]['candidate_id']
    assert search_key(search,before)==search_key(search,after)

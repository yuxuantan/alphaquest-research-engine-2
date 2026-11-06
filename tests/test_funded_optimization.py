"""Funded-only mathematical, native-kernel and normal-product qualification."""
from dataclasses import asdict, replace
from datetime import date, timedelta
from hashlib import sha256
import io
import json
from threading import Event
from types import SimpleNamespace
import zipfile

import numpy as np
import pytest

from alphaquest.app import create_app
from alphaquest.prop.funded_optimization import (FundedCandidate, FundedConstraints, FundedSearch,
    check_search, funded_metrics, optimize_funded, parse_request, rank_candidates, search_key)
from alphaquest.prop.funded_profiles import simulate_dated_funded_profile, simulate_funded_profile
from alphaquest.prop.phase_profiles import (FundedProfile, SamplingConfig, SavedTradeSource,
    SimulationConfig, SourceCosts, rule_version)
from alphaquest.prop.phase_search import PhaseCalendar
from research_fixtures import ResearchClient
from test_prop_analysis_api import wait
from test_prop_phases import save_source


def profile(firm='apex-50k-eod', **kw):
    return FundedProfile(firm, rule_version(firm), **kw)


def candidate(id, size=3, firm='apex-50k-eod'):
    return FundedCandidate(SavedTradeSource(id),profile(firm),size,SimulationConfig(simulations=8),
        SamplingConfig(1),SourceCosts(mode='source'))


def search_for(a,b=None, horizon=14, lag=4, **kw):
    candidates = (candidate(a['id']),) if b is None else (candidate(a['id']),candidate(a['id'],1),candidate(b['id']),candidate(b['id'],1))
    return FundedSearch(a['id'],candidates,PhaseCalendar(('2026-01-05',),'2037-01-01'),horizon,lag,
                        bootstrap_replicates=100,**kw)


def body(search):return json.loads(json.dumps(asdict(search)))


@pytest.fixture(scope='module')
def library(tmp_path_factory):
    root=tmp_path_factory.mktemp('funded-search-library')
    with ResearchClient(create_app(root/'datasets.sqlite3')) as client:
        a=save_source(client,days=8);b=save_source(client,green=2,days=8)
        yield client,a,b,root


def test_normal_check_run_download_reopen_and_independence(library,monkeypatch):
    client,a,b,root=library
    from alphaquest.prop import native_analysis, evaluation_profiles, evaluation_optimization, joint_sizing
    def forbidden(*a,**k):pytest.fail('Evaluation or legacy joint selector was called')
    monkeypatch.setattr(evaluation_profiles,'simulate_evaluation_profile',forbidden)
    monkeypatch.setattr(evaluation_optimization,'optimize_evaluation',forbidden)
    monkeypatch.setattr(native_analysis,'evaluation_model',forbidden)
    monkeypatch.setattr(native_analysis,'training_economics',forbidden)
    monkeypatch.setattr(native_analysis,'calculate',forbidden)
    monkeypatch.setattr(joint_sizing,'select',forbidden)
    before={str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for folder in (root/'backtest_runs',root/'prop_analyses') for p in folder.rglob('*') if p.is_file() and '.sqlite3' not in p.name}
    request=body(search_for(a,b))
    check=client.post('/api/prop-analyses/check',json=request)
    assert check.status_code==200,check.text
    result=client.post('/api/prop-analyses',json=request)
    assert result.status_code==202,result.text
    id=result.json()['id'];assert wait(client,id)['status']=='complete',wait(client,id)
    response=client.get(f'/api/prop-analyses/{id}/downloads/report.json');report=response.json()
    calc=report['calculations'];rows=calc['candidates']
    assert len(rows)==4
    # A3 earns $900/day: native five qualifying days pay $1500 on Jan9;
    # receipt Jan13; next request Jan16 settles Jan20 beyond Jan19 cutoff.
    # A1 and B3 earn $300/day: $3600 threshold only reached session12,
    # outside this 14-calendar-day horizon. B1 never qualifies at $100/day.
    assert sorted(r['metrics']['expected_payouts'] for r in rows)==[0,0,0,1500]
    best=next(r for r in rows if r['candidate_id']==calc['winner'])
    assert best['manifest']['configuration']['source']['source_backtest_id']==a['id']
    assert best['manifest']['configuration']['micros']==3
    m=best['metrics']
    assert m['expected_pending_cash']==1500 and m['expected_gross_account_deductions']==3000
    assert m['expected_days_to_first_payout_conditional_on_payout']==8
    assert m['expected_account_lifetime'] is None
    assert m['restricted_mean_account_lifetime_calendar_days']==14
    assert m['probability_surviving_to_horizon']==1
    assert all(p['observed_sessions']==10 for p in best['paths'])
    archive=client.get(f'/api/prop-analyses/{id}/downloads/analysis.zip').content
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert json.loads(z.read('calculations.json'))==calc
        for name,info in report['files'].items():assert sha256(z.read(name)).hexdigest()==info['sha256']
    for source in (a,b):
        listing=client.get('/api/prop-analyses/sources/'+source['id'],params=dict(discover_exports=False)).json()
        assert id in [r['id'] for r in listing['analyses']]
    request['candidates'].reverse()
    assert client.post('/api/prop-analyses',json=request).json()['id']==id
    monkeypatch.setattr('alphaquest.prop.funded_optimization.optimize_funded',forbidden)
    assert client.get(f'/api/prop-analyses/{id}/downloads/report.json').content==response.content
    from alphaquest.prop.store import AnalysisStore
    reopened=AnalysisStore(root,recover_interrupted=False)
    try:assert reopened.fingerprint(id) is not None
    finally:reopened.close()
    assert all(sha256((root/name).read_bytes()).hexdigest()==value for name,value in before.items())
    (root/'funded-search-request.json').write_text(json.dumps(request,indent=2))
    (root/'funded-search-verification.json').write_text(json.dumps(dict(synthetic=True,analysis_id=id,
        source_ids=[a['id'],b['id']],expected_cash=[0,0,0,1500],winner=calc['winner'],
        unchanged_files=len(before),source_check=check.json(),reopened_without_recalculation=True),indent=2))


def test_zero_evaluation_passes_does_not_block_funded(library,monkeypatch):
    client,_,b,_=library
    from alphaquest.prop.evaluation_profiles import simulate_evaluation_profile
    from alphaquest.prop.phase_profiles import EvaluationProfile,EvaluationSamplingConfig
    e=simulate_evaluation_profile(client.app.state.runs,SavedTradeSource(b['id']),
        EvaluationProfile('apex-50k-eod',rule_version('apex-50k-eod'),'30','40'),1,
        SimulationConfig(simulations=8),sampling=EvaluationSamplingConfig(chain_simulations=8),costs=SourceCosts(mode='source'))
    assert e.evaluation['passed']==0
    result=optimize_funded(client.app.state.runs,search_for(b,horizon=90,lag=0))
    assert result['winner'] is not None
    assert result['candidates'][0]['metrics']['expected_payouts']==13000


@pytest.mark.parametrize('horizon,lag,cash,pending',[(4,0,0,0),(5,0,1500,0),(8,4,0,1500),(9,4,1500,0)])
def test_request_and_receipt_exclusive_cutoff(library,horizon,lag,cash,pending):
    client,a,_,_=library
    result=optimize_funded(client.app.state.runs,search_for(a,horizon=horizon,lag=lag))['candidates'][0]
    assert result['metrics']['expected_payouts']==cash
    assert result['metrics']['expected_pending_cash']==pending
    assert all(e['request_date']<p['cutoff_exclusive'] for p in result['paths'] for e in p['payout_events'])


@pytest.mark.parametrize('horizon',[90,180,365])
def test_calendar_horizons_and_paid_all_not_breach(library,horizon):
    client,a,_,_=library
    row=optimize_funded(client.app.state.runs,search_for(a,horizon=horizon,lag=0))['candidates'][0]
    assert row['metrics']['expected_payouts']==13000
    assert row['metrics']['account_breach_probability']==0
    assert row['metrics']['probability_payout_limit_completion']==1
    assert row['metrics']['expected_account_lifetime']==39  # sixth Friday from Monday start
    assert all(p['observed_sessions']==30 for p in row['paths'])


def test_ranking_constraints_ties_uncertainty_and_win_rate(library):
    _,a,_,_=library
    search=search_for(a)
    def row(id,cash,win,breach,size=3,p10=0):
        return dict(candidate_id=id,status='estimated',source_win_rate=win,
            metrics=dict(expected_funded_cash_payouts_within_horizon=cash,account_breach_probability=breach,
                probability_first_payout=.8,p10_payouts=p10),
            manifest=dict(configuration=dict(micros=size)),uncertainty=dict(mean_family_interval=[cash-10,cash+10]))
    high=row('high',1000,.4,.3);low=row('low',800,.9,.05)
    assert rank_candidates([low,high],search)['winner']=='high'
    limited=replace(search,constraints=FundedConstraints(maximum_account_breach_probability=.1))
    r=rank_candidates([high,low],limited)
    assert r['winner']=='low' and not high['feasible']
    assert high['constraint_violations']==['maximum_account_breach_probability']
    tied=row('a',800,.1,.05)
    r=rank_candidates([low,tied],search)
    assert r['winner']=='a' and r['near_ties']==['low']
    for constraints in (FundedConstraints(minimum_probability_first_payout=.9),
                        FundedConstraints(minimum_p10_payouts=1),FundedConstraints(maximum_position_size=2)):
        assert rank_candidates([low],replace(search,constraints=constraints))['winner'] is None
    high['status']='unresolved'
    assert rank_candidates([high,low],search)['winner'] is None


@pytest.mark.parametrize('firm',['apex-50k-eod','lucidflex-50k'])
def test_dated_matches_legacy_funded_cash_and_no_double_costs(library,firm):
    client,a,_,_=library
    runs=client.app.state.runs
    # Constant source means path addressing does not alter sampled observations.
    # Monday start: 14 calendar days contains ten legacy weekdays.
    for costs in (SourceCosts(mode='source'),SourceCosts(mode='override',per_side='1')):
        c=replace(candidate(a['id'],firm=firm),costs=costs)
        old=simulate_funded_profile(runs,c.source,c.profile,c.micros,10,c.simulation,sampling=c.sampling,costs=costs)
        new=simulate_dated_funded_profile(runs,c.source,c.profile,c.micros,14,
            search_for(a).calendar,0,c.simulation,sampling=c.sampling,costs=costs)
        for previous,dated in zip(old.paths,new['paths']):
            assert dated['cash_received']==sum(v for _,v in previous['trader_payouts'])
            assert dated['gross_account_deductions']==sum(v for _,v in previous['gross_account_deductions'])
            assert dated['equity']==previous['equity']
            assert dated['trading_profit']==pytest.approx((900 if costs.mode=='source' else 894)*10)
        assert np.mean([p['cash_received'] for p in new['paths']])==old.payouts['mean_trader_payout']


def test_requests_survive_closure_and_calendar_closures(library):
    client,a,_,_=library
    s=search_for(a,horizon=90,lag=50)
    r=optimize_funded(client.app.state.runs,s)['candidates'][0]
    assert r['metrics']['expected_payouts']==13000  # last request day39, receipt day89
    assert all(e['receipt_date']>p['terminal_date'] for p in r['paths'] for e in p['payout_events'])
    r=optimize_funded(client.app.state.runs,replace(s,horizon_calendar_days=89))['candidates'][0]
    assert r['metrics']['expected_payouts']==10000 and r['metrics']['expected_pending_cash']==3000
    s=search_for(a,horizon=14,lag=0)
    s=replace(s,calendar=replace(s.calendar,start_dates=('2026-03-07',),closures=('2026-03-09',)))
    p=optimize_funded(client.app.state.runs,s)['candidates'][0]['paths'][0]
    assert p['observed_sessions']==9 and p['days_to_first_payout']==9  # Tuesday through Monday


def test_native_inactivity_on_non_session_date():
    from alphaquest.prop.lucid_engine import FundedAccount
    a=FundedAccount()
    assert not a.expire_inactive(29)
    assert a.expire_inactive(30) and a.outcome=='inactive'
    a=FundedAccount()
    a.advance([(200.,0.)],10,calendar_day=30)  # trading on the boundary prevents expiry
    assert a.outcome=='open' and a.last_activity==30


def test_strict_rejections_cache_identity_and_risk(library):
    client,a,b,_=library
    request=body(search_for(a,b))
    mutations=[lambda x:x.update(evaluation_pass_probability=0),
        lambda x:x['candidates'][0]['profile'].update(evaluation_price='30'),
        lambda x:x['candidates'][0].update(evaluation_micros=1),
        lambda x:x['candidates'][0]['sampling'].update(chain_simulations=8),
        lambda x:x['candidates'][0].update(micros=1.5),
        lambda x:x['candidates'][0]['profile'].update(profile_id='unknown'),
        lambda x:x['candidates'].append(x['candidates'][0]),
        lambda x:x.update(horizon_calendar_days=0),lambda x:x.update(receipt_delay_calendar_days=-1),
        lambda x:x['calendar'].update(coverage_end='2026-01-06'),
        lambda x:x.update(constraints=dict(maximum_account_breach_probability=2))]
    for mutate in mutations:
        r=json.loads(json.dumps(request));mutate(r)
        response=client.post('/api/prop-analyses/check',json=r)
        assert response.status_code==422,response.text
    s=parse_request(request);checks=check_search(client.app.state.runs,s);key=search_key(s,checks)
    for field,value in [('horizon_calendar_days',90),('receipt_delay_calendar_days',0),('bootstrap_seed',99),
                        ('constraints',FundedConstraints(maximum_position_size=1)),('near_tie_cash',50)]:
        assert search_key(replace(s,**{field:value}),checks)!=key
    from test_prop_phase_profiles import SingleSource
    single=search_for(a)
    modified=json.loads(json.dumps(a));modified['run_metadata']['automatic_prop_analysis']={'evaluation_pass_probability':0,'evaluation_micros':60,'cost_per_funded':1e9}
    before=check_search(SingleSource(client.app.state.runs,a),single)
    after=check_search(SingleSource(client.app.state.runs,modified),single)
    assert before[0]['candidate_id']==after[0]['candidate_id']
    assert search_key(single,before)==search_key(single,after)
    modified['run_metadata']['research']['phase']='oos'
    with pytest.raises(ValueError,match='declared IS'):check_search(SingleSource(client.app.state.runs,modified),single)


def test_all_sources_protected_during_worker(library,monkeypatch):
    client,a,b,_=library
    import alphaquest.prop.funded_optimization as module
    original=module.optimize_funded;entered=Event();release=Event()
    def paused(*a,**kw):
        entered.set();assert release.wait(10)
        return original(*a,**kw)
    monkeypatch.setattr(module,'optimize_funded',paused)
    try:
        response=client.post('/api/prop-analyses',json=body(search_for(a,b,horizon=15)))
        assert response.status_code==202,response.text
        assert entered.wait(10)
        for source in (a,b):assert client.delete('/api/backtests/'+source['id']).status_code==409
    finally:release.set()
    assert wait(client,response.json()['id'])['status']=='complete'


def test_incomplete_horizon_and_open_lifetime_are_distinct(library):
    client,a,_,_=library;s=search_for(a)
    c=candidate(a['id'])
    component=simulate_dated_funded_profile(client.app.state.runs,c.source,c.profile,3,14,s.calendar,4,c.simulation,costs=c.costs)
    paths=component['paths']
    complete=funded_metrics(paths,s)
    assert complete['metrics']['expected_payouts']==1500 and complete['status']=='estimated'
    paths[0]['horizon_observations_complete']=False;paths[0]['unresolved']=True
    incomplete=funded_metrics(paths,s)
    assert incomplete['metrics']['expected_payouts'] is None and incomplete['status']=='unresolved'
    assert incomplete['metrics']['expected_account_lifetime'] is None
    assert incomplete['censoring']['mean_accrued_cash_lower_bound']==1500


def test_native_sampled_strategies_cash_beats_winrate_and_breach_filter(library,monkeypatch):
    """Analytical test day books only; never injected into a product report."""
    import alphaquest.prop.funded_profiles as component
    _,a,_,_=library
    s=search_for(a,horizon=90,lag=0)
    sim=SimulationConfig(simulations=256,seed=42)
    monkeypatch.setattr(component,'verify_phase_source',lambda *a:None)
    monkeypatch.setattr(component,'provenance',lambda *a,**k:{})
    rows=[]
    # The 100%-win source makes only $100/session and can never qualify for
    # Apex's $250 day. The 2/3-win source can make actual native cash payouts.
    for id,days,winrate in [('lower_winrate',[[(900.,0.)],[(900.,0.)],[(-3000.,3000.,[(3000.,True)])]],2/3),
                            ('higher_winrate',[[(100.,0.)]],1.)]:
        monkeypatch.setattr(component,'prepare_phase_source',lambda *a,days=days:({},days,{}))
        result=component.simulate_dated_funded_profile(None,SavedTradeSource(a['id']),profile(),10,
            90,s.calendar,0,sim,sampling=SamplingConfig(1))
        rows.append(dict(candidate_id=id,**funded_metrics(result['paths'],s),
            source_win_rate=winrate,manifest=dict(configuration=dict(micros=10))))
    assert rows[0]['metrics']['expected_payouts']>0 and rows[1]['metrics']['expected_payouts']==0
    assert rows[0]['metrics']['account_breach_probability']>0
    assert rank_candidates(rows,s)['winner']=='lower_winrate'
    assert rank_candidates(rows,replace(s,constraints=FundedConstraints(maximum_account_breach_probability=0)))['winner']=='higher_winrate'


def test_multi_start_uncertainty_and_path_order(library):
    client,a,b,_=library
    s=search_for(a,b,horizon=14,lag=0)
    s=replace(s,calendar=replace(s.calendar,start_dates=('2026-01-05','2026-01-09')))
    left=optimize_funded(client.app.state.runs,s)
    right=optimize_funded(client.app.state.runs,replace(s,candidates=tuple(reversed(s.candidates))))
    assert left==right
    for row in left['candidates']:
        assert row['uncertainty']['mean_monte_carlo_se']==0
        assert row['uncertainty']['probability_nominal_95_intervals']=={}
        assert len(row['distribution']['values'])==8


def test_missing_saved_artifact_invalidates_funded_reuse(library):
    client,a,_,_=library
    request=body(search_for(a,horizon=16))
    first=client.post('/api/prop-analyses',json=request).json()['id']
    assert wait(client,first)['status']=='complete'
    (client.app.state.prop_analyses.root/first/'source_checks.json').unlink()
    second=client.post('/api/prop-analyses',json=request).json()['id']
    assert second!=first and wait(client,second)['status']=='complete'
    assert client.app.state.prop_analyses.fingerprint(second) is not None


def test_saved_api_boundary_and_constraints(library):
    client,a,b,root=library
    cases=[('receipt_at_cutoff',search_for(a,horizon=8),0,1500),
           ('receipt_before_cutoff',search_for(a,horizon=9),1500,0),
           ('size_constraint',search_for(a,b,constraints=FundedConstraints(maximum_position_size=1)),0,0)]
    evidence=[]
    for name,search,cash,pending in cases:
        request=body(search)
        checked=client.post('/api/prop-analyses/check',json=request)
        assert checked.status_code==200,checked.text
        result=client.post('/api/prop-analyses',json=request)
        assert result.status_code==202,result.text
        id=result.json()['id'];assert wait(client,id)['status']=='complete'
        report=client.get(f'/api/prop-analyses/{id}/downloads/report.json').json()
        calc=report['calculations'];winner=next(r for r in calc['candidates'] if r['candidate_id']==calc['winner'])
        assert winner['metrics']['expected_payouts']==cash
        assert winner['metrics']['expected_pending_cash']==pending
        if name=='size_constraint':
            highest=max(calc['candidates'],key=lambda r:r['metrics']['expected_payouts'])
            assert highest['metrics']['expected_payouts']==1500 and not highest['feasible']
        evidence.append(dict(case=name,analysis_id=id,expected_received=cash,expected_pending=pending,request=request))
    invalid=body(search_for(a));invalid['evaluation_pass_probability']=0
    rejected=client.post('/api/prop-analyses/check',json=invalid)
    assert rejected.status_code==422
    (root/'funded-boundary-verification.json').write_text(json.dumps(dict(cases=evidence,
        opposite_phase_rejection=dict(request=invalid,status=rejected.status_code,detail=rejected.json())),indent=2))

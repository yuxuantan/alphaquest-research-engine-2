"""Independent arithmetic and boundary checks for the replacement evidence gate."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from alphaquest.prop import complementary_assessment as owner
from test_prop_oos_qualification import fixed_search


def eval_paths(n=10,funded=5,horizon=365):
    return [dict(start_date='2026-01-01',event='funded' if i<funded else 'calendar_guard',
        observed_calendar_days=10 if i<funded else horizon,cost_accrued='99.5') for i in range(n)]


def test_deadline_censoring_keeps_unfunded_accounts_and_fees():
    summary=owner.summarize(eval_paths(),'evaluation',365)
    assert summary['funded_probability']['mean']==.5
    assert summary['fees_spent']['mean']==99.5
    assert summary['capped_wait']['mean']==187.5
    assert summary['median_days']==10 and summary['p90_days'] is None
    assert summary['observation_complete'] and summary['early_guard_paths']==0
    short=eval_paths();short[-1]['observed_calendar_days']=30
    assert not owner.summarize(short,'evaluation',365)['observation_complete']
    assert owner.summarize(short,'evaluation',365)['early_guard_paths']==1


def test_funded_receipts_include_zero_pending_and_breach_separately():
    paths=[dict(cash_received=0,pending_cash=500,outcome='blown'),dict(cash_received=100,pending_cash=0,outcome='open')]
    s=owner.summarize(paths,'funded',90)
    assert s['received_cash']['mean']==50 and s['median_cash']==50
    assert s['pending_cash']['mean']==250 and s['zero_receipts']['mean']==.5 and s['breach']['mean']==.5
    assert s['p10_cash']==0
    paths[-1]['unresolved']=True
    assert not owner.summarize(paths,'funded',90)['observation_complete']


def test_wilson_and_simulation_precision_are_not_historical_intervals():
    p=owner.estimate([0]*2500+[1]*2500,probability=True)
    assert p['interval']==pytest.approx([.4861462842,.5138537158],abs=1e-6)
    assert p['precision_ok']
    constant=owner.estimate([100]*5000)
    assert constant['interval']==[100,100] and constant['relative_mcse']==0
    assert not owner.estimate([0]*5000)['precision_ok']
    assert owner.RULES['historical_replicates']==0


def package(phase='evaluation'):
    if phase=='evaluation':s=owner.summarize(eval_paths(5000,5000),'evaluation',365)
    else:s=owner.summarize([dict(cash_received=100,pending_cash=0,outcome='open')]*5000,'funded',90)
    primary={role:[dict(summary=deepcopy(s))] for role in ('is','oos')}
    stress=[dict(name='Constant oracle',role='oos',summary=deepcopy(s))]
    starts=dict(paths=[{},{}],summary=dict(funded=2,zero_receipt_starts=0))
    return primary,stress,starts


def test_review_watches_evidence_failures_and_economics_are_distinct():
    primary,stress,starts=package()
    def run():return owner.insights(primary,stress,starts,'evaluation',[dict(passed=True)],dict(passed=True))
    assert run()['status']=='GO'
    primary['oos'][-1]['summary']['funded_probability']['mean']=.6
    result=run();assert result['status']=='REVIEW_REQUIRED'
    assert next(f for f in result['findings'] if f['key']=='deterioration')['state']=='WATCH'
    starts['paths']=[]
    assert run()['status']=='INSUFFICIENT_EVIDENCE'
    primary['oos'][-1]['summary']['funded_probability']['mean']=0
    assert run()['status']=='NO_GO'
    assert run()['historical_replicates']==0


def test_coverage_only_start_plan_up_to_24_full_windows():
    period=dict(first_session='2025-01-01',last_session='2026-06-30')
    plan=owner.covered_starts(period,180)
    assert len(plan['starts'])==24 and len(set(plan['starts']))==24
    assert all(date.fromisoformat(v).toordinal()+179<=date(2026,6,30).toordinal() for v in plan['starts'])
    short=owner.covered_starts(dict(first_session='2025-01-01',last_session='2025-01-31'),180)
    assert short['starts']==[]
    p=owner.policy('evaluation',period,90)
    assert p['rules']['account_paths']==5000 and p['start_plan']['horizon_calendar_days']==180
    assert p['version']==owner.VERSION


@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('profile',['lucidflex-50k','apex-50k-eod'])
def test_existing_local_account_owners_constant_cash_oracle(phase,profile,monkeypatch):
    from alphaquest.prop.phase_profiles import rule_version
    search=fixed_search(phase);c=search.candidates[0]
    c=replace(c,profile=replace(c.profile,profile_id=profile,rule_version=rule_version(profile),**({'consistency_percent':40} if phase=='evaluation' and profile=='apex-50k-eod' else {})))
    # Controlled source-adaptation boundary; real existing account owners run.
    monkeypatch.setattr('alphaquest.prop.phase_profiles.prepare_phase_source',lambda *a,**k:(dict(commission_simulation=dict(per_side='0.50')),[[(1500.,0.)]]*40,dict(ACCOUNT_TYPE='LucidFlex' if profile=='lucidflex-50k' else 'Apex EOD')))
    monkeypatch.setattr('alphaquest.prop.phase_profiles.verify_phase_source',lambda *a:None)
    if phase=='evaluation' and profile=='apex-50k-eod':
        from alphaquest.prop.phase_profiles import profile_settings
        monkeypatch.setattr('alphaquest.prop.phase_profiles.prepare_phase_source',lambda *a,**k:(dict(commission_simulation=dict(per_side='0.50')),[[(1500.,0.)]]*40,profile_settings(c.profile,c.costs)))
    runner=owner.Runner(None,None,search,lambda:None,lambda x:None)
    result=runner.run(c,8,90)
    assert len(result['paths'])==8
    if phase=='evaluation':
        assert result['summary']['funded_probability']['mean']==1
        assert result['summary']['fees_spent']['mean']==99.5
        assert result['summary']['capped_wait']['mean']==2
    else:assert result['summary']['received_cash']['mean']>0


def test_cancellation_propagates_before_simulation():
    def stop():raise RuntimeError('Stopped')
    runner=owner.Runner(None,None,fixed_search('evaluation'),stop,lambda x:None)
    with pytest.raises(RuntimeError,match='Stopped'):runner.notify('Test',0,1)


def test_short_history_skips_account_work_and_explains_what_evidence_is_missing(tmp_path,monkeypatch):
    from dataclasses import asdict
    import json
    from hashlib import sha256
    from alphaquest.prop.phase_profiles import ResearchPeriod
    from alphaquest.prop.adapter import canonical
    search=fixed_search('evaluation');candidate=replace(search.candidates[0],period=ResearchPeriod('2025-01-02','2025-01-20'))
    search=replace(search,candidates=(candidate,));snapshot=dict(backtest=dict(summary=dict(trades_taken=10)))
    manifest=dict(configuration=asdict(candidate),source=snapshot)
    parent=tmp_path/'parent';parent.mkdir();(parent/'report.json').write_text(json.dumps(dict(calculations=dict(candidates=[dict(candidate_id='frozen')]))))
    store=SimpleNamespace(root=tmp_path,fingerprint=lambda id:dict(files={'report.json':'sealed'}))
    assessment=dict(frozen_package=dict(analysis_id='parent',report_sha256='sealed'),sources=[dict(frozen_candidate_id='frozen',frozen_manifest=manifest)],prop_sim_review=dict(policy=owner.policy('evaluation',asdict(candidate.period),90),implementation=owner.implementation(),kind='qualification',prerequisites=dict(passed=True)))
    checks=[dict(candidate_id='oos',frozen_candidate_id='frozen',manifest=manifest)]
    calc=dict(candidates=[dict(candidate_id='oos',frozen_candidate_id='frozen',paths=[])])
    monkeypatch.setattr('alphaquest.prop.phase_profiles.verify_phase_source',lambda *a:None)
    monkeypatch.setattr('alphaquest.prop.phase_search.capture_inputs',lambda *a:None)
    monkeypatch.setattr(owner.Runner,'run',lambda *a,**k:pytest.fail('Short source launched account work'))
    result=owner.qualify(calc,search,assessment,None,checks,lambda:None,lambda x:None,tmp_path,store)
    q=result['candidates'][0]['prop_qualification']
    assert q['status']=='INSUFFICIENT_EVIDENCE' and q['historical_replicates']==0
    assert not result['qualification_complementary']
    assert 'Additional simulated paths cannot repair' in q['findings'][0]['next_step']

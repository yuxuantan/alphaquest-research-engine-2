"""Independent declared selector and complete causal handoff contracts."""
from copy import deepcopy
from dataclasses import asdict
import json
from uuid import uuid4

import pytest
from alphaquest.prop.phase_profiles import EvaluationProfile, FundedProfile, rule_version
from alphaquest.prop.phase_dispatch import module_for
from alphaquest.research_phase_selection import (
    EvaluationSelector, FundedSelector, PhaseStudy, Policy, build_search,
    build_training_context, complete_qualified_membership, policy_training_metadata,
    select_evaluation, select_funded, validate_native_policies,
    FUNDED_OBJECTIVE, digest, SESSION_CONVENTION,
)


def setup():
    candidates=[dict(id=k,strategy_id='consecutive',parameters={'green_candles':i},
        strategy={'id':'consecutive','parameters':{'green_candles':i},'source_sha256':'s'*64}) for i,k in enumerate(('a','b','c'),1)]
    plan=dict(campaign_id=uuid4().hex,candidates=candidates,input_identity='input',engine_identity='engine',
        dataset={'sha256':'d'*64},session_inventory={'counts':{'2026-01-05':10,'2026-01-06':10}},
        observed_calendar=dict(version='declared-test-v1',sha256='c'*64,convention=SESSION_CONVENTION,open_sessions=['2026-01-05','2026-01-06']))
    outer=dict(index=0,train=dict(first_session='2026-01-05',last_session='2026-01-06',sessions=['2026-01-05','2026-01-06']),
        test=dict(first_session='2026-01-07',last_session='2026-01-08',sessions=['2026-01-07','2026-01-08']))
    q=dict(candidates=[dict(candidate_id=c['id'],strategy_id=c['strategy_id'],parameters=c['parameters'],status='PASS' if c['id']!='c' else 'FAIL') for c in candidates],approved_ids=['a','b'])
    return plan,outer,q


def study(phase='evaluation'):
    profiles=([asdict(EvaluationProfile('apex-50k-eod',rule_version('apex-50k-eod'),'30','40'))]
        if phase=='evaluation' else [asdict(FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')))])
    settings=dict(calendar=dict(start_dates=['2026-01-07'],coverage_end='2037-01-01'))
    if phase=='funded':settings.update(horizon_calendar_days=2,receipt_delay_calendar_days=0,bootstrap_replicates=100)
    return PhaseStudy(phase=phase,profiles=profiles,policies=[Policy(micros=1),Policy(micros=3)],
        simulation=dict(simulations=8,seed=42),sampling=dict(block_weekdays=1,**({'chain_simulations':8} if phase=='evaluation' else {})),
        costs=dict(mode='source'),search_settings=settings,selector={})


def record(candidate,research,id=None):
    return dict(id=id or uuid4().hex,status='complete',execution_settings={},run_metadata=dict(
        strategy=candidate['strategy'],dataset=dict(sha256='d'*64),research=research))


def context():
    plan,outer,q=setup();m=complete_qualified_membership(plan['candidates'],q)
    r={c['id']:record(c,policy_training_metadata(plan['campaign_id'],outer,m,plan['input_identity'])) for c in m['configurations']}
    h={id:{'trades.csv':'t'*64} for id in r}
    return plan,outer,q,m,r,h,build_training_context(plan,outer,m,r,h)


def ev(id,cost,time,pass_probability=1,status='estimated'):
    return dict(candidate_id=id,status=status,manifest=dict(strategy=dict(id=id,parameters={},source_sha256='s'*64),configuration=dict(micros=1,source={})),metrics=dict(cost_per_funded=cost,expected_calendar_days_to_funded=time,pass_probability=pass_probability))


def funded(id,cash,feasible=True,status='estimated'):
    return dict(candidate_id=id,status=status,feasible=feasible,manifest=dict(strategy=dict(id=id,parameters={},source_sha256='s'*64),configuration=dict(micros=1,source={})),metrics={FUNDED_OBJECTIVE:cash})


@pytest.mark.parametrize('raw',[
    dict(mode='min_cost_under_time_cap'),dict(mode='min_time_under_cost_cap'),
    dict(minimum_pass_probability=2),dict(maximum_cost_per_funded=True),
    dict(maximum_expected_calendar_days='NaN'),dict(maximum_cost_per_funded=-1),
    dict(mode='pareto_family',tie_policy='configuration_id'),dict(arbitrary_lambda=.5),
])
def test_evaluation_bad_selector_rejects(raw):
    with pytest.raises(ValueError):EvaluationSelector(**raw)


@pytest.mark.parametrize('raw',[dict(minimum_expected_cash=True),dict(minimum_expected_cash='Infinity'),dict(evaluation_cost=20)])
def test_funded_bad_selector_rejects(raw):
    with pytest.raises(ValueError):FundedSelector(**raw)


def test_membership_keeps_every_pass_and_does_not_select_top_edge():
    plan,_,q=setup();m=complete_qualified_membership(plan['candidates'],q)
    assert m['configuration_ids']==['a','b'];assert m['excluded'][0]['configuration_id']=='c'
    q['candidates'].reverse();assert complete_qualified_membership(plan['candidates'],q)['configuration_ids']==['a','b']
    q['approved_ids']=['a']
    with pytest.raises(ValueError,match='PASS'):complete_qualified_membership(plan['candidates'],q)


def test_missing_and_changed_candidate_fail_closed():
    plan,_,q=setup();q['candidates'].pop()
    with pytest.raises(ValueError,match='every declared'):complete_qualified_membership(plan['candidates'],q)
    plan,_,q=setup();q['candidates'][0]['parameters']={'green_candles':999}
    with pytest.raises(ValueError,match='parameters'):complete_qualified_membership(plan['candidates'],q)


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_cartesian_search_is_actual_phase_contract_with_default_normalization(phase):
    *_,ctx=context();request=build_search(study(phase),ctx)
    assert len(request['candidates'])==4
    assert {c['source']['source_backtest_id'] for c in request['candidates']}==set(ctx['training_sources'])
    assert {c['micros'] for c in request['candidates']}=={1,3}
    assert json.loads(json.dumps(asdict(module_for(phase).parse_request(request))))==request
    assert all(c['period']==dict(first_session='2026-01-05',last_session='2026-01-06') for c in request['candidates'])
    assert ('receipt_delay_calendar_days' not in request and 'horizon_calendar_days' not in request) if phase=='evaluation' else 'retry' not in request['candidates'][0]


@pytest.mark.parametrize('change', ['role','phase','window','parameters','implementation','dataset','protocol','absent_bars'])
def test_training_context_boundaries(change):
    plan,outer,q,m,r,h,_=context()
    meta=r['a']['run_metadata']
    if change=='role':meta['research']['role']='outer_test'
    elif change=='phase':meta['research']['phase']='is'
    elif change=='window':meta['research']['window']['last_session']='2026-01-07'
    elif change=='parameters':meta['strategy']=deepcopy(meta['strategy']);meta['strategy']['parameters']={'green_candles':9}
    elif change=='implementation':meta['strategy']=deepcopy(meta['strategy']);meta['strategy']['source_sha256']='x'*64
    elif change=='dataset':meta['dataset']['sha256']='x'*64
    elif change=='protocol':meta['research']['input_identity']='different'
    else:plan['session_inventory']['counts']['2026-01-05']=0
    with pytest.raises(ValueError):build_training_context(plan,outer,m,r,h)


def choose(rows,selector):
    from alphaquest.prop.evaluation_optimization import pareto_sort, EvaluationConstraints
    limits={key:float(value) for key,value in selector.items() if key in ('maximum_cost_per_funded','maximum_expected_calendar_days','minimum_pass_probability')}
    return select_evaluation(pareto_sort(deepcopy(rows['candidates']),EvaluationConstraints(**limits)),selector)


def test_pareto_nonconvex_all_ties_and_explicit_cap_preference():
    calc={'candidates':[ev('a',100,10),ev('a2',100,10),ev('b',160,8),ev('c',180,4),ev('d',190,12)]}
    assert choose(calc,{})['selected_ids']==['a','a2','b','c']
    assert choose(calc,dict(mode='min_cost_under_time_cap',maximum_expected_calendar_days=8))['selected_ids']==['b']
    assert choose(calc,dict(mode='min_time_under_cost_cap',maximum_cost_per_funded=160))['selected_ids']==['b']
    assert choose(calc,dict(mode='min_cost_under_time_cap',maximum_expected_calendar_days=10))['selected_ids']==['a','a2']
    assert len(choose(calc,dict(mode='min_cost_under_time_cap',maximum_expected_calendar_days=10,tie_policy='configuration_id'))['selected_ids'])==1
    assert 'lambda' not in json.dumps(choose(calc,{}))


def test_pass_constraint_recomputes_feasible_frontier_and_unknown_prevents_winner():
    calc={'candidates':[ev('fast',100,5,.1),ev('safer',200,10,.8)]}
    assert choose(calc,{'minimum_pass_probability':'.5'})['selected_ids']==['safer']
    calc['candidates'].append(ev('unknown',None,None,status='censored'))
    assert choose(calc,{})['status']=='INSUFFICIENT_EVIDENCE'
    assert choose(calc,{})['selected_ids']==[]


def test_funded_maximum_cash_keeps_ties_and_obeys_phase_risk_constraints():
    calc=dict(objective=FUNDED_OBJECTIVE,candidates=[funded('a',100),funded('b',100),funded('risky',10000,False)])
    request=dict(horizon_calendar_days=20,receipt_delay_calendar_days=4,constraints={'maximum_account_breach_probability':.1})
    result=select_funded(calc,{},request);assert result['selected_ids']==['a','b']
    assert result['constraints']==request['constraints']
    assert len(select_funded(calc,{'tie_policy':'configuration_id'},request)['selected_ids'])==1
    assert select_funded(calc,{'minimum_expected_cash':'101'},request)['status']=='NO_FEASIBLE_POLICY'
    calc['candidates'].append(funded('unknown',None,False,'censored'))
    assert select_funded(calc,{},request)['selected_ids']==[]


def test_native_dynamic_and_required_baseline_cannot_be_silently_removed():
    s=study();value=s.model_dump()
    value['policies'][0]['sizing']=dict(policy=dict(kind='fixed_dollar_risk',risk_dollars='100'),initial_configured_capital='50000',
        planning_execution=dict(tick_size='.25',commission_per_contract_per_side='1'))
    with pytest.raises(ValueError,match='native_rerun_required'):validate_native_policies([PhaseStudy(**value)])
    with pytest.raises(ValueError,match='required_baseline_unavailable'):validate_native_policies([s],[dict(required=True,source_kind='native_backtest',sizing_kind='fixed_dollar_risk')])


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_tie_preference_is_phase_independent_of_context_and_generated_ids(phase):
    rows=([ev('a',100,10),ev('b',100,10)] if phase=='evaluation' else [funded('a',100),funded('b',100)])
    for row in rows:
        row['manifest']['configuration'].update(source={'source_backtest_id':row['candidate_id']},profile={'profile_id':'apex-50k-eod'},simulation={'seed':42})
        row['manifest']['training_context_sha256']='evaluation and funded original context'
    selector=dict(tie_policy='configuration_id',**({'mode':'min_cost_under_time_cap','maximum_expected_calendar_days':10} if phase=='evaluation' else {}))
    request=dict(horizon_calendar_days=20,receipt_delay_calendar_days=0)
    def selected(rows):
        calc={'candidates':rows,'objective':FUNDED_OBJECTIVE}
        chosen=choose(calc,selector) if phase=='evaluation' else select_funded(calc,selector,request)
        return next(row['manifest']['strategy']['id'] for row in rows if row['candidate_id']==chosen['selected_ids'][0])
    original=selected(rows)
    changed=deepcopy(rows)
    for row in changed:
        row['candidate_id']='z' if row['candidate_id']=='a' else '0'
        row['manifest']['configuration']['source']['source_backtest_id']='unrelated-new-run-'+row['candidate_id']
        row['manifest']['training_context_sha256']='opposite phase settings changed'
    assert selected(list(reversed(changed)))==original

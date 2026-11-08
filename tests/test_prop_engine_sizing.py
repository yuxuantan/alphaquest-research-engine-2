"""Kernel qualification; trade templates are synthetic and exogenous.

Pinned hashes came from immutable pre-M2b kernels at bdbfa7e; they cover each
phase independently, full funded states, and unchanged seeded sample draws.
"""
from dataclasses import asdict, replace
from importlib import import_module
from hashlib import sha256
import json
import numpy as np
import pytest

ENGINES=[import_module('alphaquest.prop.'+x) for x in ('native_engine','lucid_engine','_native_compiled','_lucid_compiled')]
DEFAULT_HASHES={'native-42-1-1': 'ac3aab37261055d72f9d97dc9b5e0b03fd7542cc0de68eba8dc508ae5b9cd9b3', 'native-43-5-9': '45cd1b997ab849368cf9d96e269367bae2592404ec561706c27b654a9086c76b', 'native-44-3-40': 'fa216aa0086b3de7a009de2e376a5fe0ae7b4e44d8dea5b0f18f504a0f8b2843', 'lucid-42-1-1': '75e057ed48ba1628bc7491fb519bffc45ab5327be6d4c5a5b9744717f3013ba1', 'lucid-43-5-9': '180948e2020e8fba357968f50155debb09b1a7acabfe8fcd8f69f3a85acae104', 'lucid-44-3-40': 'c7cce40b5a5662181c27c78f97cdc3af180b04f8e9dd9e1c55624496987667fd'}
CONTEXT={'initial_configured_capital':'1000','planning_execution':{'tick_size':'0.25','point_value':'2','entry_slippage_ticks':0,'stop_exit_slippage_ticks':0,'commission_per_contract_per_side':'0'}}
PERCENT={'kind':'percentage_risk','risk_percent':'10','reference':'current_account_balance'}

def template(net=200.,adverse=0.,index=0):
    minute=index*2
    decision=f'2026-01-05T15:{minute:02d}:00Z'
    entry=f'2026-01-05T15:{minute+1:02d}:00Z'
    return (net,adverse,((adverse,True),),True,{'source_trade_id':f'synthetic-{index}', 'side':'long','entry_time_utc':entry,'sizing_decision':{'timestamp_utc':decision,'reference_price':'100','execution_timing':'next_open'},'initial_stop':{'price':'95','known_at_utc':decision,'basis':'strategy_decision'}})

def same(left,right):
    if isinstance(left,dict):
        assert left.keys()==right.keys()
        for key in left:assert np.array_equal(left[key],right[key]),key
    else:assert [asdict(x) for x in left]==[asdict(x) for x in right]

@pytest.mark.parametrize('engine',ENGINES)
@pytest.mark.parametrize('seed,block,micros',[(42,1,1),(43,5,9),(44,3,40)])
def test_none_and_fixed_policy_match_prior_numerical_results(engine,seed,block,micros):
    family='lucid' if 'lucid' in engine.__name__ else 'native'
    days=[[(800.,0.),(-350.,600.),(0.,0.)],[],[(-2700.,2700.),(450.,0.)],[(1700.,100.),(900.,0.)]]
    policy={'kind':'fixed_contracts','contracts':micros}
    kwargs={'sizing_policy':policy,'sizing_context':CONTEXT}
    results=[]
    for mode in ({},kwargs):
        evaluation=engine.evaluation(days,micros,30,seed,block,deadline=40,**mode)
        numerical={'evaluation':{key:value.tolist() if hasattr(value,'tolist') else value for key,value in evaluation.items()},'funded':[]}
        for variant in (True,False):
            rules=replace(engine.Rules(),daily_loss=1200. if variant else None) if family=='lucid' else replace(engine.Rules(),approval_day_counts=variant)
            numerical['funded'].append([asdict(account) for account in engine.funded(days,micros,30,seed,block,horizon=100,rules=rules,**mode)])
        results.append(numerical)
        digest=sha256(json.dumps(numerical,sort_keys=True,default=list,separators=(',',':')).encode()).hexdigest()
        assert digest==DEFAULT_HASHES[f'{family}-{seed}-{block}-{micros}']
    assert results[0]==results[1]

@pytest.mark.parametrize('engine',ENGINES)
def test_compounding_within_one_session_uses_pretrade_balance_and_opening_floors(engine):
    trace=[];account=engine.FundedAccount()
    account.advance([template(),template(-250,250,1),template(100,0,2)],40,sizing_policy=PERCENT,sizing_context=CONTEXT,trace=trace.append)
    assert [r['quantity'] for r in trace]==[10,12,9]
    assert account.day==1 and account.trades_consumed==3 and account.opportunities_consumed==3
    assert account.equity==-10
    assert [r['state_before']['equity_change_from_initial'] for r in trace]==['0.0','200.0','-100.0']
    assert len({r['state_before']['daily_floor_from_initial'] for r in trace})==1
    assert len({r['state_before']['account_floor_from_initial'] for r in trace})==1
    assert trace[-1]['equity_after']=='-10.0'

@pytest.mark.parametrize('engine',ENGINES)
def test_candidate_and_opening_provider_caps_remain_separate(engine):
    account=engine.FundedAccount();trace=[]
    account.advance([template(1000),template(1000,0,1)],60,sizing_policy={'kind':'fixed_contracts','contracts':60},sizing_context=CONTEXT,trace=trace.append)
    assert [r['quantity'] for r in trace]==[20,20]
    assert [r['state_before']['provider_max_contracts'] for r in trace]==[20,20]
    other=engine.FundedAccount();trace=[]
    other.advance([template()],7,max_micros=4,sizing_policy={'kind':'fixed_contracts','contracts':60},sizing_context=CONTEXT,trace=trace.append)
    assert trace[0]['quantity']==4 and trace[0]['state_before']['user_max_contracts']==4

@pytest.mark.parametrize('engine',ENGINES)
def test_skipped_opportunities_do_not_create_costs_activity_or_qualifying_days(engine):
    account=engine.FundedAccount();trace=[]
    policy={'kind':'fixed_dollar_risk','risk_dollars':'9.99'}
    account.advance([template(100000,20000)],40,sizing_policy=policy,sizing_context=CONTEXT,trace=trace.append)
    assert account.day==1 and account.equity==0 and account.trades_consumed==0
    assert account.opportunities_consumed==account.skipped_trades==1
    assert account.qualifying==0 and account.payouts==[] and account.effective_micros is None
    assert trace[0]['quantity']==0 and trace[0]['outcome']=='skipped'
    while account.outcome=='open':
        account.advance([template()],40,sizing_policy=policy,sizing_context=CONTEXT)
    assert account.outcome=='inactive'

@pytest.mark.parametrize('engine',ENGINES)
def test_gap_hit_stops_visiting_future_opportunities_and_keeps_observed_loss(engine):
    account=engine.FundedAccount();trace=[]
    account.advance([template(-1300,1300),template(100000,0,1)],40,sizing_policy={'kind':'fixed_contracts','contracts':10},sizing_context=CONTEXT,trace=trace.append)
    assert account.equity==-1300 and account.last_hit==1
    assert len(trace)==1 and trace[0]['account_hit']==1
    assert account.opportunities_consumed==account.trades_consumed==1

@pytest.mark.parametrize('engine',ENGINES)
def test_risk_metadata_is_required_and_future_stop_rejected(engine):
    account=engine.FundedAccount()
    with pytest.raises(ValueError,match='causal'):
        account.advance([(200.,0.)],40,sizing_policy=PERCENT,sizing_context=CONTEXT)
    trade=template();trade[4]['initial_stop']['known_at_utc']='2026-01-05T15:02:00Z'
    with pytest.raises(ValueError,match='known'):
        engine.FundedAccount().advance([trade],40,sizing_policy=PERCENT,sizing_context=CONTEXT)

@pytest.mark.parametrize('family',['native','lucid'])
def test_dynamic_reference_compiled_results_and_traces_match_with_repeated_templates(family):
    reference=import_module('alphaquest.prop.'+family+'_engine');compiled=import_module('alphaquest.prop._'+family+'_compiled')
    days=[[template(800),template(-300,300,1)],[],[template(-900,900)],[template(1200)]]
    traces=[];results=[]
    for engine in (reference,compiled):
        trace=[]
        results.append(engine.evaluation(days,40,20,15,block=2,deadline=25,sizing_policy=PERCENT,sizing_context=CONTEXT,trace=trace.append));traces.append(trace)
    same(*results);assert traces[0]==traces[1]
    assert traces[0][0]['decision_time_utc']=='2026-01-05T15:00:00Z'
    assert len({r['session_index'] for r in traces[0]})>1
    traces=[];results=[]
    for engine in (reference,compiled):
        trace=[]
        results.append(engine.funded(days,40,20,15,block=2,horizon=30,sizing_policy=PERCENT,sizing_context=CONTEXT,trace=trace.append));traces.append(trace)
    same(*results);assert traces[0]==traces[1]

@pytest.mark.parametrize('engine',[ENGINES[1],ENGINES[3]])
def test_lucid_payout_stops_opportunities_and_trace_contains_withdrawal(engine):
    account=engine.FundedAccount(qualifying=4);trace=[]
    account.advance([template(1000),template(999999,0,1)],40,sizing_policy={'kind':'fixed_contracts','contracts':10},sizing_context=CONTEXT,trace=trace.append)
    assert account.withdrawals==[(1,500.)] and account.payouts==[(1,450.)]
    assert account.equity==500 and len(trace)==1 and trace[0]['equity_after']=='500.0'


@pytest.mark.parametrize('engine',ENGINES)
def test_declared_planning_cost_sizes_quantity_without_deducting_source_net_again(engine):
    context=dict(CONTEXT,planning_execution=dict(CONTEXT['planning_execution'],
        entry_slippage_ticks=1,stop_exit_slippage_ticks=2,commission_per_contract_per_side='0.5'))
    account=engine.FundedAccount();trace=[]
    account.advance([template()],40,sizing_policy={'kind':'fixed_dollar_risk','risk_dollars':'25'},
        sizing_context=context,trace=trace.append)
    # (5 point stop + 3 ticks * .25) * $2 + $1 round trip = $12.50 per MNQ.
    assert trace[0]['quantity']==2 and trace[0]['decision']['planned_risk_per_mnq']=='12.50'
    assert account.equity==40  # Already-net source $200 per NQ * 2/10.


@pytest.mark.parametrize('engine',ENGINES)
def test_cushion_percentage_recomputes_from_prior_trade_without_moving_floor(engine):
    account=engine.FundedAccount();trace=[]
    policy={'kind':'percentage_risk','risk_percent':'5','reference':'available_drawdown_cushion'}
    account.advance([template(-400,400),template(100,0,1)],40,sizing_policy=policy,
        sizing_context=CONTEXT,trace=trace.append)
    assert [item['quantity'] for item in trace]==[10,8]
    assert [item['decision']['denominator_value'] for item in trace]==['2000.0','1600.0']
    assert account.equity==-320 and account.day==1


@pytest.mark.parametrize('engine',ENGINES)
def test_evaluation_session_compounds_without_resetting_day_floor(engine):
    trace=[];trades=[template(),template(-250,250,1),template(100,0,2)]
    args=(trades,0.,0.,0.,0,0,40) if 'lucid' in engine.__name__ else (trades,0.,0.,40)
    result=engine.evaluation_session(*args,sizing_policy=PERCENT,sizing_context=CONTEXT,trace=trace.append)
    assert result[0]==-10 and [item['quantity'] for item in trace]==[10,12,9]
    assert len({item['state_before']['daily_floor_from_initial'] for item in trace})==1
    assert result[-1]==3


@pytest.mark.parametrize('engine',ENGINES)
def test_fixed_policy_accepts_historical_absent_stop_and_decision(engine):
    trade=template();trade[4].update(sizing_decision=None,initial_stop=None)
    account=engine.FundedAccount()
    account.advance([trade],40,sizing_policy={'kind':'fixed_contracts','contracts':2},sizing_context=CONTEXT)
    assert account.equity==40


@pytest.mark.parametrize('field,value',[('actual_entry_fill','100'),('entry_price','100')])
def test_planning_metadata_rejects_observed_fill_inputs(field,value):
    from alphaquest.prop.sizing_runtime import decision_risk_from_metadata
    metadata=template()[4];metadata[field]=value
    with pytest.raises(ValueError,match='unsupported'):
        decision_risk_from_metadata(metadata)


@pytest.mark.parametrize('engine',ENGINES)
def test_fractional_candidate_ceiling_is_rejected_for_explicit_sizing(engine):
    with pytest.raises(ValueError,match='whole'):
        engine.FundedAccount().advance([template()],1.5,sizing_policy=PERCENT,sizing_context=CONTEXT)


@pytest.mark.parametrize('family',['native','lucid'])
def test_fixed_policy_preserves_rng_stream_after_prefetch_boundary(family):
    engine=import_module('alphaquest.prop._'+family+'_compiled')
    rules=replace(engine.Rules(),inactivity_calendar_days=10000) if family=='lucid' else replace(engine.Rules(),inactivity_window=6000)
    days=[[(.01,0.)],[(.02,0.)],[]]
    original=engine.funded(days,1,2,42,block=1,horizon=5000,rules=rules)
    sized=engine.funded(days,1,2,42,block=1,horizon=5000,rules=rules,
        sizing_policy={'kind':'fixed_contracts','contracts':1},sizing_context=CONTEXT)
    same(original,sized)

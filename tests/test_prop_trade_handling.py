"""Independent arithmetic and account-state oracles for frozen trade handling."""
from dataclasses import asdict
from decimal import Decimal
import pytest
from alphaquest.prop.phase_profiles import SizingConfiguration, SizingTrace
from alphaquest.prop.saved_trade_simulation import ACCOUNT_MODEL, adapt_saved_trades, describe_results
from alphaquest.prop.sizing import choose_quantity
from alphaquest.prop.sizing_runtime import decision_risk_from_metadata
from test_saved_trade_simulation import metadata


def configured(kind='percentage_risk', action='skip', minimum=False, percent='.5', contracts=40, stop='95'):
    policy=dict(kind=kind,maximum_contracts=40)
    policy.update(dict(risk_percent=percent,reference='initial_configured_capital') if kind=='percentage_risk' else dict(contracts=contracts))
    return SizingConfiguration(policy,'50000',dict(tick_size='.25',commission_per_contract_per_side='.5'),ACCOUNT_MODEL,
        dict(account_limit_action=action,minimum_one_contract=minimum))


def decision(c,*,account='2000',daily='1200',cap=40,stop='95'):
    m=metadata();m['initial_stop']['price']=stop
    state=dict(initial_configured_capital='50000',equity_change_from_initial='0',
        account_floor_from_initial='-'+account,daily_floor_from_initial='-'+daily if daily is not None else None,
        provider_max_contracts=cap,user_max_contracts=40)
    return choose_quantity(c.policy,state,decision_risk_from_metadata(m),c.planning_execution,trade_handling=c.trade_handling)


def test_actual_capped_position_not_requested_budget_controls_skip():
    c=configured(percent='4') # Requested $2,000; provider caps at one $11-risk MNQ.
    result=decision(c,cap=1,daily='12')
    assert result['quantity']==1 and Decimal(result['risk_budget'])==2000
    assert Decimal(result['planned_total_risk'])==11
    assert decision(c,cap=1,daily='11')['quantity']==0 # Touching is a limit event.


def test_minimum_one_changes_only_soft_percentage_budget_and_is_optional():
    assert decision(configured(percent='.01'))['quantity']==0 # $5 cannot buy $11 risk.
    result=decision(configured(percent='.01',minimum=True))
    assert result['quantity']==1 and result['minimum_one_override'] and result['risk_budget_override']
    assert Decimal(result['actual_risk_percent'])==Decimal('.022')
    assert decision(configured(percent='.01',minimum=True),daily='10')['quantity']==0
    assert decision(configured(percent='.01',minimum=True,action='exit_at_limit'),daily='10')['quantity']==1
    assert decision(configured(percent='.01',minimum=True),cap=0)['quantity']==0
    with pytest.raises(ValueError,match='percentage'):
        configured(kind='fixed_contracts',minimum=True)


@pytest.mark.parametrize('profile',['apex','lucid'])
@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('action',['skip','exit_at_limit'])
def test_winner_can_hit_limit_and_later_opportunities_are_not_counted(profile,phase,action):
    from alphaquest.prop import native_engine,lucid_engine
    kernel=native_engine if profile=='apex' else lucid_engine
    c=configured(kind='fixed_contracts',action=action)
    trace=SizingTrace(c)
    m=metadata();m['initial_stop']['price']='50' # $101 planned risk per MNQ.
    winner=(500.,800.,(),True,m) # +$50/MNQ, but captured adverse excursion $80/MNQ.
    args=dict(**c.kernel_arguments(),trace=trace)
    if phase=='evaluation':
        result=(kernel.evaluation_session([winner,winner],0.,0.,40,**args) if profile=='apex' else
            kernel.evaluation_session([winner,winner],0.,0.,0.,0,0,40,**args))
        equity,hit=result[0],result[-2]
    else:
        account=kernel.FundedAccount(kernel.Rules())
        account.advance([winner,winner],40,**args)
        equity,hit=account.equity,account.last_hit
    if action=='skip':
        assert equity==0 and hit==0
        assert trace.summary['decision_count']==2 and trace.summary['skipped_count']==2
    else:
        assert equity==(-1000 if profile=='apex' else -1200) and hit==1
        assert trace.summary['decision_count']==1 # No trace/skip for the later halted opportunity.
        assert trace.summary['account_limit_exit_count']==1 and trace.summary['daily_limit_exit_count']==1
        assert trace.summary['account_breach_exit_count']==0
        assert Decimal(trace.summary['behavior_examples']['account_limit_exit'][0]['equity_after'])==Decimal(str(equity))


@pytest.mark.parametrize('profile',['apex','lucid'])
def test_account_floor_is_exact_and_account_terminates(profile):
    from alphaquest.prop import native_engine,lucid_engine
    kernel=native_engine if profile=='apex' else lucid_engine
    c=configured(kind='fixed_contracts',action='exit_at_limit');trace=SizingTrace(c)
    account=kernel.FundedAccount(kernel.Rules())
    account.equity=-1500 # Only $500 account cushion remains; DLL is farther away.
    m=metadata();m['initial_stop']['price']='50'
    account.advance([(500.,800.,(),True,m)]*2,40,**c.kernel_arguments(),trace=trace)
    assert account.equity==-2000 and account.last_hit==2 and account.outcome=='blown'
    assert trace.summary['account_breach_exit_count']==1 and trace.summary['decision_count']==1


def test_override_summary_uses_entries_and_excludes_skips():
    from alphaquest.prop import native_engine
    c=configured(percent='.01',minimum=True);trace=SizingTrace(c)
    trade=(100.,0.,(),True,metadata())
    native_engine.evaluation_session([trade]*2,0.,0.,40,**c.kernel_arguments(),trace=trace)
    row=dict(provenance=dict(source={'saved_trade_simulation':dict(model=ACCOUNT_MODEL,source_trades=1)},sizing=trace.result()))
    describe_results([row]);s=row['quantity_summary']
    assert s['opportunities']==2 and s['source_trade_count']==1
    assert s['risk_budget_override_count']==2 and s['risk_budget_override_rate']==1
    assert Decimal(s['mean_actual_risk_percent'])==Decimal('.022')
    assert Decimal(s['maximum_actual_risk_percent'])==Decimal('.022')
    assert s['skipped_rate']==0 and s['account_limit_exit_rate']==0


def test_mae_changes_outcome_evidence_never_quantity_and_missing_evidence_rejects(monkeypatch):
    from copy import deepcopy
    from native_replay_fixtures import parameter_values
    c=configured(kind='fixed_contracts',action='exit_at_limit')
    snap=dict(backtest=dict(run_metadata=dict(strategy=dict(id='vwap_pullback_risk_sizing',parameters=parameter_values()))),
        commission_simulation=dict(per_side='.5',source_instrument='MNQ'))
    monkeypatch.setattr('alphaquest.prop.saved_trade_simulation.causal_plans',lambda *a:({'1':metadata()},dict(method='SYNTHETIC oracle')))
    base=dict(trade_id=1,entry_utc=metadata()['entry_time_utc'],exit_utc='2026-01-05T15:05:00Z',simulation_net_per_nq='500')
    with pytest.raises(ValueError,match='captured source MAE'):
        adapt_saved_trades(None,deepcopy(snap),[base.copy()],c)
    for mae in ('0','99999'):
        s=deepcopy(snap);rows=[dict(base,measured_mae=mae,simulation_mae_per_nq=mae)]
        adapt_saved_trades(None,s,rows,c)
        assert rows[0]['simulation_net_per_nq']=='500'
        assert Decimal(rows[0]['simulation_mae_per_nq'])==min(Decimal(mae),Decimal(110))
        assert s['saved_trade_simulation']['mae_used']
        assert decision(c)['quantity']==40


def test_unsupported_models_and_non_boolean_options_reject():
    c=configured()
    with pytest.raises(ValueError,match='versioned'):
        SizingConfiguration(c.policy,'50000',c.planning_execution,None,c.trade_handling)
    from alphaquest.prop.sizing import TradeHandling
    with pytest.raises(ValueError):TradeHandling(minimum_one_contract='true')
    with pytest.raises(ValueError):TradeHandling(account_limit_action='ignore_rules')


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
@pytest.mark.parametrize('kind',['fixed_contracts','percentage_risk'])
def test_frozen_handling_reaches_both_phase_engines_and_oos(tmp_path,monkeypatch,profile,kind):
    from alphaquest.app import create_app
    from research_fixtures import ResearchClient
    from test_saved_trade_simulation import saved_source_pair
    from test_percentage_automatic import install_admission_fixture,configuration
    from test_prop_sim_automatic import wait_automatic
    from alphaquest.prop.phase_dispatch import module_for
    from alphaquest.prop.complementary_assessment import Runner
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        source=saved_source_pair(client);install_admission_fixture(monkeypatch,source)
        body=configuration(source,profile)
        body.update(evaluation_trade_handling=dict(account_limit_action='exit_at_limit',minimum_one_contract=kind=='percentage_risk'),
                    funded_trade_handling=dict(account_limit_action='skip',minimum_one_contract=kind=='percentage_risk'))
        if kind=='fixed_contracts':
            for phase in ('evaluation','funded'):
                body.pop(phase+'_percentage_grid')
                body.update({phase+'_minimum_micros':10,phase+'_maximum_micros':11})
            body['search_kind']=kind
        checked=client.post('/api/prop-sim/check',json=body)
        assert checked.status_code==200,checked.text
        response=client.post('/api/prop-sim',json=body);assert response.status_code==202,response.text
        saved=wait_automatic(client,response.json()['id'],timeout=180)
        assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
        for phase in ('evaluation','funded'):
            expected=body[phase+'_trade_handling']
            campaign=client.app.state.campaigns.get(saved['campaign_ids'][phase])
            search=module_for(phase).parse_request(campaign['manifest']['request'])
            report=client.get(f"/api/prop-sim/{saved['id']}/results/{phase}").json()
            assert len(report['calculations']['candidates'])==2
            for row in report['calculations']['candidates']:
                assert row['simulation_model']['model']==ACCOUNT_MODEL
                assert row['manifest']['configuration']['sizing']['trade_handling']==expected
                assert row['quantity_summary']['opportunities']>0
            state=saved['automation']['phases'][phase]
            oos=client.get(f"/api/prop-sim/{saved['id']}/validation/{phase}/{state['oos_request_id']}").json()
            for row in oos['calculations']['candidates']:
                assert row['configuration']['sizing']['trade_handling']==expected
                assert row['simulation_model']['model']==ACCOUNT_MODEL
                assert 'account_limit_exit_rate' in row['quantity_summary']
            # Actual baseline/stress owners, with small oracle counts. Production
            # evidence minima stay intact; the short synthetic source cannot GO.
            runner=Runner(client.app.state.runs,client.app.state.store,search,lambda:None,lambda v:None)
            for options in ({},{'extra_cost':True},{'block':1}):
                result=runner.run(search.candidates[0],8,9,**options)
                assert len(result['paths'])==8
                assert result['summary']['trade_behavior']['opportunities']>0


@pytest.mark.parametrize('profile',['apex','lucid'])
@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_compiled_v2_cash_and_full_decisions_match_python(profile,phase):
    from alphaquest.prop import native_engine,native_backend,lucid_engine,lucid_backend
    reference,backend=(native_engine,native_backend) if profile=='apex' else (lucid_engine,lucid_backend)
    assert backend.compiled is not None, 'Build matching optional kernels for parity verification.'
    for action in ('skip','exit_at_limit'):
        c=configured(kind='fixed_contracts',action=action);m=metadata();m['initial_stop']['price']='50'
        trades=[(500.,800.,(),True,m)]*2
        outcomes=[]
        for kernel in (reference,backend.compiled):
            trace=SizingTrace(c);args=dict(**c.kernel_arguments(),trace=trace)
            if phase=='funded':
                account=kernel.FundedAccount(kernel.Rules());account.advance(trades,40,**args)
                result=asdict(account)
            else:
                result=(kernel.evaluation_session(trades,0.,0.,40,**args) if profile=='apex' else
                    kernel.evaluation_session(trades,0.,0.,0.,0,0,40,**args))
            outcomes.append((result,trace.result()))
        assert outcomes[0]==outcomes[1]


def test_equal_account_and_daily_floors_terminate_at_exact_account_floor():
    from alphaquest.prop.sizing_runtime import resolve_runtime,saved_limit_result
    c=configured(kind='fixed_contracts',action='exit_at_limit')
    args=c.kernel_arguments();runtime=resolve_runtime(args['sizing_policy'],args['sizing_context'],None)
    assert saved_limit_result(runtime,(500.,1000.,(),True,metadata()),0.,-1000.,-1000.,10)==(-1000.,2)
    with pytest.raises(ValueError):
        SizingConfiguration(c.policy,'50000',c.planning_execution,ACCOUNT_MODEL,0)

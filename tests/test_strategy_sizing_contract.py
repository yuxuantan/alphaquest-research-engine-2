"""Shared admission, real Twin orders, causal sizing and provider-floor oracles."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import pytest

from alphaquest.execution import Trade, execute
from alphaquest.strategies.registry import STRATEGIES, StrategyDefinition
from alphaquest.strategies.twin_continuation import TwinContinuation, Parameters
from alphaquest.strategy import EntryIntent, EntryProtection, StopEntriesIntent, CloseIntent
from alphaquest.strategy_sizing import controlled_orders
from test_twin_continuation import config, momentum_parameters, momentum_rows, breakout_rows, prices, CT
from test_native_account_execution import owner


def test_every_registered_strategy_declares_independent_modes_and_no_stop_is_invented():
    for definition in STRATEGIES.values():
        capabilities=definition.sizing.describe(definition.module.Parameters())
        assert capabilities['version']=='strategy-sizing-contract-v1'
        assert set(capabilities)>={'fixed_contracts','percentage_risk','native_fixed_contracts','accelerated_native'}
        assert definition.description()['sizing_support']==capabilities
    green=STRATEGIES['consecutive_green_hold']
    assert green.sizing.describe(green.module.Parameters())['fixed_contracts']['supported']
    assert 'no pre-entry protective stop' in green.sizing.describe(green.module.Parameters())['percentage_risk']['reason']
    from types import SimpleNamespace
    with pytest.raises(ValueError,match='Every registered strategy'):
        StrategyDefinition(SimpleNamespace(),object)


def test_capabilities_depend_on_parameters_not_just_strategy_name():
    vwap=STRATEGIES['vwap_pullback_risk_sizing'];p=vwap.module.Parameters()
    assert vwap.sizing.describe(p)['percentage_risk']['supported']
    assert not vwap.sizing.describe(replace(p,use_vol_sizing=True))['fixed_contracts']['supported']
    assert not vwap.sizing.describe(replace(p,use_eod_flat=False))['percentage_risk']['supported']
    multiple=vwap.sizing.describe(replace(p,max_trades_per_day=2))
    assert multiple['percentage_risk']['supported'] and not multiple['accelerated_native']
    twin=STRATEGIES['twin_continuation']
    assert twin.sizing.describe(Parameters())['percentage_risk']['supported']
    for change in [dict(immediate_protection=False),dict(use_session_calendar=False),dict(clock_shift=1)]:
        support=twin.sizing.describe(replace(Parameters(),**change))
        assert support['fixed_contracts']['supported'] and not support['percentage_risk']['supported']


def test_saved_source_version_blocks_native_modes_but_preserves_fixed_path_support():
    import json
    from alphaquest.strategy_sizing import source_support
    definition=STRATEGIES['twin_continuation'];parameters=Parameters()
    saved=json.loads(json.dumps(definition.provenance(parameters),default=str))
    assert source_support(definition,parameters,saved)['percentage_risk']['supported']
    saved['source_sha256']='0'*64
    support=source_support(definition,parameters,saved)
    assert support['fixed_contracts']['supported'] and not support['native_source_version_matches']
    assert not support['percentage_risk']['supported'] and not support['native_fixed_contracts']['supported']
    assert 'new qualified source' in support['percentage_risk']['reason']


@pytest.mark.parametrize('strategy_id,quantity_field',[('consecutive_green_hold','contracts'),('vwap_pullback_risk_sizing','position_size')])
def test_other_registered_fixed_paths_preserve_decisions_when_quantity_changes(strategy_id,quantity_field):
    from native_replay_fixtures import bars,parameters
    definition=STRATEGIES[strategy_id]
    p=parameters() if strategy_id=='vwap_pullback_risk_sizing' else definition.module.Parameters()
    cfg=replace(config(),point_value=D(2))
    rows=bars()
    outcomes=[]
    for quantity in [1,3]:
        strategy=definition.create(replace(p,**{quantity_field:quantity}),cfg,instrument_symbol='MNQ')
        outcomes.append([t for t in execute(rows,strategy,cfg) if type(t) is Trade])
    assert outcomes[0] and len(outcomes[0])==len(outcomes[1])
    for a,b in zip(*outcomes):
        assert (a.entry_time_utc,a.exit_time_utc,a.side,a.entry_fill_price,a.exit_fill_price)==(b.entry_time_utc,b.exit_time_utc,b.side,b.entry_fill_price,b.exit_fill_price)
        assert b.net_pnl==3*a.net_pnl and b.total_commissions==3*a.total_commissions


@pytest.mark.parametrize('short',[False,True])
@pytest.mark.parametrize('kind',['momentum','breakout'])
def test_twin_fixed_path_scaling_preserves_real_signals_fills_and_costs(kind,short):
    parameters=momentum_parameters(immediate_protection=True) if kind=='momentum' else Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1)
    rows=momentum_rows(short=short) if kind=='momentum' else breakout_rows(short)
    outcomes=[]
    for quantity in [1,3]:
        outcomes.append([t for t in execute(rows,TwinContinuation(replace(parameters,qty=quantity)),config()) if type(t) is Trade])
    assert outcomes[0] and len(outcomes[0])==len(outcomes[1])
    for a,b in zip(*outcomes):
        assert (a.entry_time_utc,a.exit_time_utc,a.entry_fill_price,a.exit_fill_price,a.entry_reason,a.exit_reason)==(b.entry_time_utc,b.exit_time_utc,b.entry_fill_price,b.exit_fill_price,b.entry_reason,b.exit_reason)
        assert b.net_pnl==a.net_pnl*3 and b.total_commissions==a.total_commissions*3


@pytest.mark.parametrize('short',[False,True])
@pytest.mark.parametrize('kind',['momentum','breakout'])
@pytest.mark.parametrize('policy',[dict(kind='fixed_contracts',contracts=2),dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital')])
def test_real_twin_controlled_entries_use_actual_quantity_and_reconcile(kind,short,policy):
    parameters=momentum_parameters(immediate_protection=True) if kind=='momentum' else Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1)
    rows=momentum_rows(short=short) if kind=='momentum' else breakout_rows(short)
    cfg=replace(config(),point_value=D(2),commission_per_contract_per_side=D(0),slippage_ticks=0)
    control=owner(rows,policy,config=cfg)
    events=list(execute(rows,TwinContinuation(parameters,execution_config=cfg),cfg,
        account_control=control,completion='require_flat',capture_decisions=True,capture_risk=True))
    trades=[t for t in events if type(t) is Trade]
    result=control.finish_replay()
    if kind=='momentum' and policy['kind']=='percentage_risk':
        # $100 planned budget / ($75 stop * $2 point) cannot buy one contract.
        assert not trades and result['execution_counts']['skipped_opportunities']>0
    else:
        assert trades and all(t.contracts==2 for t in trades)
        assert D(result['trading_profit'])==sum(t.net_pnl for t in trades)
    assert not control._quoted_entries and result['conservation']


class GroupSignals:
    """Independent OCO fixture; submitted before the execution bar is known."""
    tick_size=D('.25')
    def on_bar(self,bar,position):
        if bar.bar_number==1:
            return StopEntriesIntent(((EntryIntent(1,'buy',timing='next_open',protection=EntryProtection(stop_distance=D(5),target_distance=D(5))),D(110)),
                                     (EntryIntent(1,'sell',side='short',timing='next_open',protection=EntryProtection(stop_distance=D(5),target_distance=D(5))),D(90))))
        return CloseIntent('flatten') if position else None
    def on_bar_controlled(self,bar,position,admit):return controlled_orders(self,bar,position,admit)
    def on_finish(self,bar,position):raise AssertionError('No fabricated EOF exit')


def test_oco_quantities_are_committed_before_gap_and_only_post_fill_path_hits_floors():
    from datetime import datetime
    start=datetime(2024,1,16,9,tzinfo=CT)
    cfg=replace(config(),point_value=D(2),commission_per_contract_per_side=D(0),slippage_ticks=0)
    # Low first: sell fills at 90, then takes profit at 85. The sibling never fills.
    rows=[prices(1,start),prices(2,start+timedelta(minutes=1),100,120,80,110)]
    control=owner(rows,dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital'),config=cfg)
    trades=[t for t in execute(rows,GroupSignals(),cfg,account_control=control,completion='require_flat',capture_decisions=True) if type(t) is Trade]
    trade,=trades
    assert trade.side=='short' and trade.contracts==10 and trade.net_pnl==D(100)
    result=control.finish_replay()
    assert result['execution_counts']['accepted_submissions']==2
    assert result['execution_counts']['filled_entries']==1 and result['execution_counts']['cancelled_entries']==1
    assert {d['decision_reference_price'] for d in result['sizing_decisions']}=={'110','90'}


def test_unfilled_oco_quotes_expire_without_leaking_pending_state():
    from datetime import datetime
    start=datetime(2024,1,16,9,tzinfo=CT)
    rows=[prices(1,start),prices(2,start+timedelta(minutes=1))]
    cfg=replace(config(),point_value=D(2),commission_per_contract_per_side=D(0))
    control=owner(rows,dict(kind='fixed_contracts',contracts=2),config=cfg)
    assert not [t for t in execute(rows,GroupSignals(),cfg,account_control=control,completion='require_flat') if type(t) is Trade]
    result=control.finish_replay()
    assert result['execution_counts']['cancelled_entries']==2 and not control._quoted_entries


class LongStopSignals(GroupSignals):
    def on_bar(self,bar,position):
        if bar.bar_number==1:
            return StopEntriesIntent(((EntryIntent(1,'buy',timing='next_open',protection=EntryProtection(
                stop_distance=D(30),target_distance=D(30))),D(110)),))
        return CloseIntent('flatten') if position else None


@pytest.mark.parametrize('ohlc,reason,net',[
    ((100,150,80,140),'take_profit',1200), # Low before entry belongs to no position.
    ((100,120,70,90),'native_daily_floor',-1000), # High first; provider floor precedes strategy stop.
])
def test_oco_provider_floor_and_strategy_protection_share_only_the_held_path(ohlc,reason,net):
    from datetime import datetime
    start=datetime(2024,1,16,9,tzinfo=CT)
    rows=[prices(1,start),prices(2,start+timedelta(minutes=1),*ohlc)]
    cfg=replace(config(),point_value=D(2),commission_per_contract_per_side=D(0),slippage_ticks=0)
    control=owner(rows,dict(kind='fixed_contracts',contracts=40),config=cfg)
    trade,=[t for t in execute(rows,LongStopSignals(),cfg,account_control=control,completion='require_flat') if type(t) is Trade]
    assert trade.exit_reason==reason and trade.net_pnl==net
    assert D(control.finish_replay()['trading_profit'])==net


def test_stop_gap_changes_fill_but_never_the_precommitted_percentage_quantity():
    from datetime import datetime
    start=datetime(2024,1,16,9,tzinfo=CT)
    cfg=replace(config(),point_value=D(2),commission_per_contract_per_side=D(0),slippage_ticks=0)
    results=[]
    for opening in [110,130]:
        rows=[prices(1,start),prices(2,start+timedelta(minutes=1),opening,opening+1,opening-1,opening)]
        control=owner(rows,dict(kind='percentage_risk',risk_percent='.2',reference='initial_configured_capital'),config=cfg)
        trade,=[t for t in execute(rows,GroupSignals(),cfg,account_control=control,completion='require_flat') if type(t) is Trade]
        result=control.finish_replay();results.append(trade)
        assert result['sizing_decisions'][0]['decision_reference_price']=='110'
    assert [t.contracts for t in results]==[10,10]
    assert [t.entry_fill_price for t in results]==[110,130]

"""Independent actual-fill arithmetic with the real native phase controller."""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal

import pytest

from alphaquest.execution import ExecutionContinuation,ExecutionError,EquityPoint,Trade,execute
from alphaquest.decision_capture import DecisionEvent
from alphaquest.execution_scenarios import FillAssumptions
from alphaquest.prop.funded_profiles import NativeFundedController
from alphaquest.prop.native_control import SessionContext
from alphaquest.prop.phase_profiles import FundedProfile,SizingConfiguration,rule_version
from alphaquest.prop.sizing import AccountSizingState,DecisionRisk,KnownDecisionRisk,choose_quantity
from alphaquest.session_calendar import session_date
from alphaquest.strategy import Bar,EntryIntent,CloseIntent,BracketIntent,ExecutionConfig

D=Decimal
CONFIG=ExecutionConfig(D('10000'),D('.25'),D('2'),0,D('0'))
START=datetime(2026,1,5,15,tzinfo=timezone.utc)


def bar(number,close='100',*,opening=None,low=None,high=None,day=0,minute=None):
    close=D(close);opening=D(opening) if opening is not None else close
    stamp=START+timedelta(days=day,minutes=number-1 if minute is None else minute)
    return Bar(number,stamp,stamp.strftime('%m/%d/%Y'),stamp.strftime('%H:%M'),opening,
        D(high) if high is not None else max(close,opening),D(low) if low is not None else min(close,opening),close,D(1),D(0),D(0),())


def owner(bars,policy,*,config=CONFIG,stop_extra=0):
    groups={}
    for value in bars:groups.setdefault(session_date(value.timestamp_utc),[]).append(value)
    contexts={day:SessionContext(day,datetime.combine(day,datetime.min.time(),timezone.utc)+timedelta(hours=22),
        'independent-unit-observed-bars','a'*64,len(values),True) for day,values in groups.items()}
    sizing=SizingConfiguration(policy,'50000',dict(tick_size='.25',point_value='2',
        entry_slippage_ticks=config.slippage_ticks,stop_exit_slippage_ticks=config.slippage_ticks+stop_extra,
        commission_per_contract_per_side=str(config.commission_per_contract_per_side)))
    return NativeFundedController(FundedProfile('apex-50k-eod',rule_version('apex-50k-eod')),sizing,40,
        session_contexts=contexts,start_date=min(groups),cutoff_date_exclusive=max(groups)+timedelta(days=1),
        receipt_delay_calendar_days=0)


class ControlledSignals:
    """An independently specified strategy commits only accepted submissions."""
    def __init__(self,orders,*,allow=True):self.orders=orders;self.allow=allow;self.accepted=0;self.observed=[]
    def on_bar(self,bar,position):
        return self.orders.get(bar.bar_number)
    def on_bar_controlled(self,bar,position,admit_entry):
        self.observed.append((bar.bar_number,position))
        intent=self.orders.get(bar.bar_number)
        if type(intent) is EntryIntent:
            intent=admit_entry(intent)
            if intent is not None:self.accepted+=1
        if type(intent) in (CloseIntent,BracketIntent) and position is None:return None
        return intent
    def allow_entry_fill(self,bar):return self.allow
    def on_finish(self,bar,position):raise AssertionError('Native require_flat must never repair EOF with on_finish')


def controlled(bars,strategy,control,config=CONFIG,**kwargs):
    return list(execute(bars,strategy,config,account_control=control,completion='require_flat',
        capture_decisions=True,capture_risk=True,**kwargs))


def test_known_native_risk_has_no_future_entry_and_dictionary_contract_stays_strict():
    raw=dict(sizing_decision_time_utc=START.isoformat(),initial_stop_known_at_utc=START.isoformat(),
        execution_timing='next_open',side='long',decision_reference_price='100',initial_stop_price='95')
    known=KnownDecisionRisk(**raw)
    state=AccountSizingState(initial_configured_capital='50000',equity_change_from_initial='0',
        account_floor_from_initial='-2000',provider_max_contracts=40,user_max_contracts=40)
    execution=dict(tick_size='.25',entry_slippage_ticks=1,stop_exit_slippage_ticks=2,commission_per_contract_per_side='1')
    result=choose_quantity({'kind':'fixed_dollar_risk','risk_dollars':'100'},state,known,execution)
    assert result['quantity']==7 and D(result['planned_risk_per_mnq'])==D('13.5')
    assert 'entry_time_utc' not in known.model_dump()
    with pytest.raises(ValueError):choose_quantity({'kind':'fixed_dollar_risk','risk_dollars':'100'},state,raw,execution)
    with pytest.raises(ValueError):KnownDecisionRisk(**dict(raw,entry_time_utc=(START+timedelta(minutes=1)).isoformat()))
    with pytest.raises(ValueError):KnownDecisionRisk(**dict(raw,initial_stop_known_at_utc=(START+timedelta(minutes=1)).isoformat()))
    with pytest.raises(ValueError):KnownDecisionRisk(**dict(raw,previous_source_exit_utc=(START+timedelta(minutes=1)).isoformat()))
    DecisionRisk(**dict(raw,entry_time_utc=(START+timedelta(minutes=1)).isoformat()))


def test_actual_three_session_percentage_decisions_use_provider_balance_not_backtest_capital():
    bars=[bar(1),bar(2,'95'),bar(3,day=1,minute=0),bar(4,'110',day=1,minute=1),
        bar(5,day=2,minute=0),bar(6,day=2,minute=1)]
    strategy=ControlledSignals({1:EntryIntent(1,'a',initial_stop=D(95)),2:CloseIntent('a_exit'),
        3:EntryIntent(1,'b',initial_stop=D(95)),4:CloseIntent('b_exit'),
        5:EntryIntent(1,'c',initial_stop=D(90)),6:CloseIntent('c_exit')})
    control=owner(bars,dict(kind='percentage_risk',risk_percent='.2',reference='current_account_balance'))
    events=controlled(bars,strategy,control);trades=[v for v in events if type(v) is Trade]
    result=control.finish_replay()
    assert [t.contracts for t in trades]==[10,9,5]
    assert [t.net_pnl for t in trades]==[D(-100),D(180),D(0)]
    assert [D(d['denominator_value']) for d in result['sizing_decisions']]==[D(50000),D(49900),D(50080)]
    assert D(result['trading_profit'])==80 and D(result['equity'])==80
    assert events[-1].cash_balance==D(10080)
    assert len(result['trace'])==3 and all(r['executed']==1 for r in result['trace'])


@pytest.mark.parametrize('opening,low,expected,hit',[('100','40','-1000',1),('40','40','-1200',1),('-10','-10','-2200',2)])
def test_actual_daily_floor_touch_gap_and_deeper_account_gap(opening,low,expected,hit):
    bars=[bar(1),bar(2,opening,opening=opening,low=low,high='100'),bar(3)]
    strategy=ControlledSignals({1:EntryIntent(1,'signal',initial_stop=D(95)),
        2:EntryIntent(1,'later opportunity',timing='next_open',initial_stop=D(-20)),3:CloseIntent('old_exit')})
    control=owner(bars,dict(kind='fixed_contracts',contracts=10))
    events=controlled(bars,strategy,control);trade,=[v for v in events if type(v) is Trade]
    result=control.finish_replay();closes=[e for e in result['control_events'] if e['event']=='trade_close']
    assert trade.net_pnl==D(expected) and trade.exit_bar_number==2
    assert closes[0]['account_hit']==hit
    assert result['outcome']==('blown' if hit==2 else 'open')
    assert strategy.accepted==1 and len(strategy.observed)==3
    assert result['sizing_decisions'][-1]['quantity']==0


def test_same_close_entry_never_uses_earlier_bar_low_but_next_open_does():
    bars=[bar(1,low='-100'),bar(2)]
    strategy=ControlledSignals({1:EntryIntent(1,'close signal',initial_stop=D(95)),2:CloseIntent('exit')})
    control=owner(bars,dict(kind='fixed_contracts',contracts=10))
    events=controlled(bars,strategy,control);trade,=[v for v in events if type(v) is Trade]
    assert trade.net_pnl==0 and trade.exit_reason=='exit'
    bars=[bar(1),bar(2,low='40'),bar(3)]
    strategy=ControlledSignals({1:EntryIntent(1,'open signal',timing='next_open',initial_stop=D(95)),3:CloseIntent('exit')})
    control=owner(bars,dict(kind='fixed_contracts',contracts=10))
    trade,=[v for v in controlled(bars,strategy,control) if type(v) is Trade]
    assert trade.net_pnl==-1000 and trade.entry_bar_number==trade.exit_bar_number==2


def test_entry_fee_jump_forces_real_exit_and_exit_fee_can_cross_deeper_account_floor():
    config=replace(CONFIG,commission_per_contract_per_side=D(110))
    bars=[bar(1),bar(2)]
    strategy=ControlledSignals({1:EntryIntent(1,'cost jump',initial_stop=D(95)),2:CloseIntent('exit')})
    control=owner(bars,dict(kind='fixed_contracts',contracts=10),config=config)
    trade,=[v for v in controlled(bars,strategy,control,config) if type(v) is Trade]
    result=control.finish_replay();closed=next(e for e in result['control_events'] if e['event']=='trade_close')
    assert trade.entry_bar_number==trade.exit_bar_number==1
    assert trade.total_commissions==2200 and trade.net_pnl==-2200
    assert closed['triggering_floor']=='daily' and closed['account_hit']==2
    assert result['outcome']=='blown'


def test_next_open_cost_planning_and_actual_gap_loss_are_distinct_and_costs_once():
    config=replace(CONFIG,slippage_ticks=1,commission_per_contract_per_side=D(1))
    bars=[bar(1),bar(2,'101',opening='101',low='100',high='102'),bar(3,'95',opening='100',low='94',high='101')]
    strategy=ControlledSignals({1:EntryIntent(1,'signal',timing='next_open',initial_stop=D(95)),2:BracketIntent(D(95),D(120))})
    control=owner(bars,dict(kind='fixed_dollar_risk',risk_dollars='100'),config=config,stop_extra=1)
    trade,=[v for v in controlled(bars,strategy,control,config,fill_assumptions=FillAssumptions(stop_extra_slippage_ticks=1)) if type(v) is Trade]
    decision=control.finish_replay()['sizing_decisions'][0]
    assert decision['quantity']==7 and D(decision['planned_total_risk'])==D('94.5')
    assert trade.entry_fill_price==D('101.25') and trade.exit_fill_price==D('94.5')
    assert trade.total_commissions==14 and trade.net_pnl==D('-108.5')


def test_skip_does_not_commit_strategy_and_later_affordable_signal_is_actually_executed():
    bars=[bar(1),bar(2),bar(3)]
    strategy=ControlledSignals({1:EntryIntent(1,'too wide',initial_stop=D(95)),
        2:EntryIntent(1,'narrow',initial_stop=D('99.5')),3:CloseIntent('exit')})
    control=owner(bars,dict(kind='fixed_dollar_risk',risk_dollars='1'))
    events=controlled(bars,strategy,control);trade,=[v for v in events if type(v) is Trade]
    result=control.finish_replay()
    assert strategy.accepted==1 and trade.entry_bar_number==2 and trade.contracts==1
    assert [d['quantity'] for d in result['sizing_decisions']]==[0,1]
    assert trade.total_commissions==0


def test_accepted_submission_then_guard_cancellation_has_no_fake_fill():
    bars=[bar(1),bar(2)]
    strategy=ControlledSignals({1:EntryIntent(1,'pending',timing='next_open',initial_stop=D(95))},allow=False)
    control=owner(bars,dict(kind='fixed_contracts',contracts=1))
    events=controlled(bars,strategy,control);result=control.finish_replay()
    assert strategy.accepted==1 and not any(type(e) is Trade for e in events)
    assert any(e['event']=='entry_cancelled' for e in result['control_events'])
    assert D(result['trading_profit'])==0


@pytest.mark.parametrize('timing',['same_close','next_open'])
def test_flat_completion_rejects_open_or_pending_without_invented_on_finish(timing):
    bars=[bar(1)];strategy=ControlledSignals({1:EntryIntent(1,'truncated',timing=timing,initial_stop=D(95))})
    with pytest.raises(ExecutionError,match='requires flat'):
        controlled(bars,strategy,owner(bars,dict(kind='fixed_contracts',contracts=1)))


def test_causal_admission_does_not_pull_next_bar_before_decision():
    source=[bar(1),bar(2),bar(3)];advanced=[]
    def bars():
        for b in source:advanced.append(b.bar_number);yield b
    strategy=ControlledSignals({1:EntryIntent(1,'signal',timing='next_open',initial_stop=D(95)),3:CloseIntent('exit')})
    events=execute(bars(),strategy,CONFIG,account_control=owner(source,dict(kind='fixed_contracts',contracts=1)),
        completion='require_flat',capture_decisions=True)
    assert type(next(events)) is EquityPoint
    decision=next(events);assert type(decision) is DecisionEvent and decision.kind=='entry_decision'
    assert advanced==[1]
    list(events)


def test_continuation_retains_original_capital_and_default_path_rejects_it():
    first=[bar(1),bar(2,'150')]
    second=[bar(1,day=1),bar(2,'105',day=1)]
    control=owner(first+second,dict(kind='fixed_contracts',contracts=1))
    orders={1:EntryIntent(1,'signal',initial_stop=D(95)),2:CloseIntent('exit')}
    before=controlled(first,ControlledSignals(orders),control)
    assert before[-1].cash_balance==10100
    events=controlled(second,ControlledSignals(orders),control,continuation=ExecutionContinuation(D(10000),before[-1].cash_balance))
    assert events[-1].cash_balance==D(10110) and events[-1].realized_net_pnl==D(110)
    result=control.finish_replay()
    assert D(result['conservation']['provider_equity_from_initial'])==D(result['trading_profit'])==110
    with pytest.raises(ExecutionError,match='requires controlled'):
        list(execute(first,ControlledSignals({}),CONFIG,continuation=ExecutionContinuation(D(10000),D(10100))))


@pytest.mark.parametrize('stop,expected,reason',[('75','-500','stop_loss'),('25','-1000','native_daily_floor')])
def test_nearest_adverse_strategy_or_account_stop_precedes_ambiguous_target(stop,expected,reason):
    bars=[bar(1),bar(2),bar(3,low='0',high='160')]
    strategy=ControlledSignals({1:EntryIntent(1,'signal',initial_stop=D(95)),2:BracketIntent(D(stop),D(150))})
    control=owner(bars,dict(kind='fixed_contracts',contracts=10))
    trade,=[v for v in controlled(bars,strategy,control) if type(v) is Trade]
    assert trade.net_pnl==D(expected) and trade.exit_reason==reason


def test_short_daily_floor_has_actual_adverse_fill():
    bars=[bar(1),bar(2,high='160'),bar(3)]
    strategy=ControlledSignals({1:EntryIntent(1,'short',side='short',initial_stop=D(105)),3:CloseIntent('exit')})
    control=owner(bars,dict(kind='fixed_contracts',contracts=10))
    trade,=[v for v in controlled(bars,strategy,control) if type(v) is Trade]
    assert trade.exit_fill_price==150 and trade.net_pnl==-1000


@pytest.mark.parametrize('gap,percentage,quantities,nets',[
    (False,True,[10,9,5],[-100,180,100]),
    (True,True,[10,9,5],[-140,180,100]),
    (False,False,[10,10,5],[-100,200,100]),
])
def test_complete_actual_mnq_vwap_session_reruns_with_independent_decision_arithmetic(gap,percentage,quantities,nets):
    from native_replay_fixtures import bars as actual_bars,parameters
    from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
    bars=actual_bars(gap=gap)
    policy=(dict(kind='percentage_risk',risk_percent='.2',reference='current_account_balance') if percentage else
            dict(kind='fixed_dollar_risk',risk_dollars='100'))
    control=owner(bars,policy)
    strategy=VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
    events=controlled(bars,strategy,control);trades=[v for v in events if type(v) is Trade]
    result=control.finish_replay()
    assert [t.contracts for t in trades]==quantities
    assert [t.net_pnl for t in trades]==[D(n) for n in nets]
    assert [d['decision_reference_price'] for d in result['sizing_decisions']]==['118']*3
    assert [D(d['initial_stop_price']) for d in result['sizing_decisions']]==[D(113),D(113),D(108)]
    assert D(result['trading_profit'])==sum(nets)
    assert strategy.session_flattening['calendar']['instrument']=='MNQ futures'
    assert len(result['trace'])==3


def test_actual_vwap_skipped_first_signal_preserves_later_accepted_opportunity():
    from native_replay_fixtures import bars as actual_bars,parameters
    from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
    bars=actual_bars(days=1,skip_retry=True)
    original=VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
    old=[v for v in execute(bars,original,CONFIG) if type(v) is Trade]
    assert len(old)==1 and old[0].entry_time_utc.minute==2 and old[0].net_pnl==-10
    strategy=VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
    control=owner(bars,dict(kind='fixed_dollar_risk',risk_dollars='1'))
    trade,=[v for v in controlled(bars,strategy,control) if type(v) is Trade]
    result=control.finish_replay()
    assert trade.entry_time_utc.minute==7 and trade.contracts==2 and trade.net_pnl==12
    assert any(d['quantity']==0 for d in result['sizing_decisions'])
    accepted=[d for d in result['sizing_decisions'] if d['quantity']]
    assert len(accepted)==1 and D(accepted[0]['initial_stop_price'])==D('117.75')
    assert strategy.trades_today==1


def test_default_control_none_preserves_exact_original_trade_equity_risk_decisions():
    from native_replay_fixtures import bars,parameters
    from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
    def strategy():return VwapPullbackRiskSizing(parameters(),execution_config=CONFIG,instrument_symbol='MNQ')
    ordinary=list(execute(bars(days=1),strategy(),CONFIG,capture_risk=True,capture_decisions=True))
    explicit=list(execute(bars(days=1),strategy(),CONFIG,capture_risk=True,capture_decisions=True,account_control=None))
    assert [asdict(event) for event in ordinary]==[asdict(event) for event in explicit]

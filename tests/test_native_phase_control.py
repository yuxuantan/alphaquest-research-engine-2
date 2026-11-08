"""Independent native fill/account/cash oracles through the ordinary engine."""
from collections import Counter
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal,localcontext

import pytest

from alphaquest.execution import execute,Trade,EquityPoint
from alphaquest.strategy import Bar,ExecutionConfig,EntryIntent,CloseIntent
from alphaquest.prop.native_control import SessionContext,ProviderCashBridge
from alphaquest.prop.phase_profiles import SizingConfiguration,EvaluationProfile,FundedProfile,rule_version
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.prop.evaluation_optimization import SequentialRetry
from alphaquest.prop.evaluation_profiles import NativeEvaluationController
from alphaquest.prop.funded_profiles import NativeFundedController

D=Decimal
FIRST=date(2026,1,5)


@pytest.fixture(autouse=True,params=['python','compiled'])
def native_backend_mode(request,monkeypatch):
    monkeypatch.setenv('ALPHAQUEST_PROP_BACKEND',request.param)


def bars_for(days):
    """Each tuple is one actual observed (open,high,low,close) bar."""
    result=[]
    for day,values in days:
        for offset,prices in enumerate(values):
            if not isinstance(prices,tuple):prices=(prices,)*4
            stamp=datetime.combine(day,time(15),timezone.utc)+timedelta(minutes=offset)
            result.append(Bar(len(result)+1,stamp,str(day),'15:00',*map(D,map(str,prices)),D(1),D(1),D(0),()))
    return result


def contexts(bars):
    from alphaquest.prop.phase_lifecycle import session_date
    counts=Counter(session_date(bar.timestamp_utc) for bar in bars)
    return {day:SessionContext(day,datetime.combine(day,time(22),timezone.utc),'synthetic-calendar-v1','a'*64,count,True)
            for day,count in counts.items()}


def sizing(kind='fixed_dollar_risk',**changes):
    policy={'kind':kind,'risk_dollars':'100'} if kind=='fixed_dollar_risk' else (
        {'kind':kind,'risk_percent':'0.2','reference':'current_account_balance'} if kind=='percentage_risk' else {'kind':kind,'contracts':10})
    policy.update(changes)
    return SizingConfiguration(policy,'50000',dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))


class ScriptedOpportunities:
    """Independent test signal program; committed entries count only acceptance."""
    def __init__(self,stops):self.stops=stops;self.accepted=[];self.seen=[]
    def on_bar(self,bar,position):raise AssertionError('Controlled path must use its explicit callback.')
    def on_bar_controlled(self,bar,position,admit):
        self.seen.append((bar.bar_number,position is not None))
        if position is not None:return CloseIntent('actual test exit')
        if bar.bar_number in self.stops:
            accepted=admit(EntryIntent(1,'synthetic known opportunity',initial_stop=D(str(self.stops[bar.bar_number]))))
            if accepted is not None:self.accepted.append(accepted.contracts)
            return accepted
        return None
    def on_finish(self,bar,position):raise AssertionError('Native flat completion cannot invent an on_finish exit.')


def controller(bars,phase='funded',profile='apex-50k-eod',size=None,cutoff=None,**kwargs):
    saved=contexts(bars);first=min(saved);cutoff=cutoff or max(saved)+timedelta(days=1)
    options=dict(session_contexts=saved,start_date=first,cutoff_date_exclusive=cutoff,max_micros=40)
    if phase=='funded':
        return NativeFundedController(FundedProfile(profile,rule_version(profile)),size or sizing(),40,
            receipt_delay_calendar_days=kwargs.pop('receipt_delay',0),**options,**kwargs)
    calendar=PhaseCalendar((str(first),),str(cutoff+timedelta(days=10)))
    return NativeEvaluationController(EvaluationProfile(profile,rule_version(profile),'30','40'),size or sizing(),40,
        calendar=calendar,retry=kwargs.pop('retry',SequentialRetry(activation_delay_sessions=0)),**options,**kwargs)


def run(bars,control,stops,fee='0',slip=0):
    strategy=ScriptedOpportunities(stops)
    events=list(execute(bars,strategy,ExecutionConfig(D(50000),D('.25'),D(2),slip,D(fee)),
        account_control=control,completion='require_flat',capture_risk=True,capture_decisions=True))
    return [event for event in events if type(event) is Trade],events[-1],control.finish_replay(),strategy


@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('kind,expected,profit',[('fixed_dollar_risk',[10,10,5],'100'),('percentage_risk',[10,9,5],'80')])
def test_actual_fill_quantities_recompute_from_exact_balance_inside_one_session(phase,kind,expected,profit):
    bars=bars_for([(FIRST,[100,95,100,110,100,100])])
    control=controller(bars,phase,size=sizing(kind))
    trades,last,result,strategy=run(bars,control,{1:95,3:95,5:90})
    assert [trade.contracts for trade in trades]==expected==strategy.accepted
    assert D(result['trading_profit'])==D(profit) and last.equity==D(50000)+D(profit)
    assert len(result['trace'])==1 and result['trace'][0]['executed']==3
    if kind=='percentage_risk':assert [D(row['denominator_value']) for row in result['sizing_decisions']]==[D(50000),D(49900),D(50080)]


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_zero_quantity_creates_no_trade_fee_or_activity_but_closes_session(phase):
    bars=bars_for([(FIRST,[100,95,100,110])])
    trades,last,result,strategy=run(bars,controller(bars,phase,size=sizing(risk_dollars='1')),{1:95,3:95},fee='.37')
    assert trades==strategy.accepted==[] and last.equity==D(50000)
    assert result['trace'][0]['executed']==0 and result['trace'][0]['skipped']==2
    assert result['sizing']['summary']['skipped_count']==2 and result['equity']=='0'


def test_dll_liquidates_actual_position_and_blocks_later_same_day_entries():
    bars=bars_for([(FIRST,[100,(100,100,70,100),100,110])])
    trades,last,result,strategy=run(bars,controller(bars,size=sizing('fixed_contracts',contracts=20)),{1:95,3:95})
    assert len(trades)==1 and trades[0].exit_fill_price==D(75) and trades[0].net_pnl==D(-1000)
    assert trades[0].exit_reason=='native_daily_floor' and strategy.seen[1]==(2,False)
    assert result['sizing_decisions'][1]['quantity']==0 and result['sizing_decisions'][1]['reasons']==['daily_halt']
    assert result['outcome']=='open' and last.equity==D(49000)


@pytest.mark.parametrize('profile,gain,gross,receipt,equity',[('apex-50k-eod',50,'1500','1500','3500'),('lucidflex-50k',10,'500.0','450.00','500.0')])
def test_existing_funded_payout_rules_deduct_gross_without_altering_trade_ledger(profile,gain,gross,receipt,equity):
    bars=bars_for([(FIRST+timedelta(days=i),[100,100+gain]) for i in range(5)])
    trades,last,result,_=run(bars,controller(bars,profile=profile,size=sizing('fixed_contracts')),{i:95 for i in range(1,11,2)})
    assert D(result['gross_account_deductions'])==D(gross) and D(result['cash_received'])==D(receipt)
    assert D(result['equity'])==D(equity)
    assert last.equity==D(50000)+sum(trade.net_pnl for trade in trades)
    assert D(result['equity'])+D(result['gross_account_deductions'])==D(result['trading_profit'])
    assert len(result['payout_events'])==1


def test_receipt_exactly_at_cutoff_remains_pending_and_no_replacement_is_created():
    bars=bars_for([(FIRST+timedelta(days=i),[100,110]) for i in range(5)])
    _,_,result,_=run(bars,controller(bars,profile='lucidflex-50k',size=sizing('fixed_contracts'),receipt_delay=1),{i:95 for i in range(1,11,2)})
    assert D(result['cash_received'])==0 and D(result['pending_cash'])==450
    assert result['payout_events'][0]['receipt_date']=='2026-01-10'
    assert not any(row['event']=='trader_receipt' for row in result['cash_ledger'])


def test_evaluation_retry_has_fresh_provider_capital_and_retains_actual_failed_trade_and_fees():
    bars=bars_for([(FIRST,[100,(-10,-10,-10,-10)]),(FIRST+timedelta(days=1),[100,250]),(FIRST+timedelta(days=2),[100])])
    trades,last,result,_=run(bars,controller(bars,'evaluation',size=sizing('fixed_contracts')),{1:95,3:95})
    assert [trade.net_pnl for trade in trades]==[D(-2200),D(3000)]
    assert last.equity==D(50800) and D(result['equity'])==D(3000)
    assert [attempt['outcome'] for attempt in result['attempts']]==['blown','passed']
    assert D(result['attempts'][1]['prior_attempt_trading_net'])==D(-2200)
    assert result['outcome']=='funded_ready' and result['ready_date']=='2026-01-07'
    assert D(result['paid_fees'])==100 and D(result['net_cash'])==-100
    assert D(result['conservation']['prior_attempt_trading_net'])==D(-2200)


@pytest.mark.parametrize('cutoff,expected',[(date(2026,1,8),'funded_ready'),(date(2026,1,7),'activation_pending')])
def test_native_readiness_at_guard_matches_forecast_but_outer_cutoff_stays_exclusive(cutoff,expected):
    days=[(FIRST,[100,250]),(FIRST+timedelta(days=1),[100])]
    if cutoff.day==8:days.append((FIRST+timedelta(days=2),[100]))
    bars=bars_for(days)
    control=controller(bars,'evaluation',size=sizing('fixed_contracts'),cutoff=cutoff,
        retry=SequentialRetry(activation_delay_sessions=1,max_calendar_days=2))
    _,_,result,_=run(bars,control,{1:95})
    assert result['outcome']==expected and D(result['paid_fees'])==70


def test_missing_declared_session_cannot_publish_a_partial_native_report():
    bars=bars_for([(FIRST,[100]),(FIRST+timedelta(days=1),[100])])
    control=controller(bars)
    list(execute(bars[:1],ScriptedOpportunities({}),ExecutionConfig(D(50000),D('.25'),D(2),0,D(0)),account_control=control,completion='require_flat'))
    with pytest.raises(ValueError,match='complete verified session inventory'):control.finish_replay()


@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('gap,expected_net,expected_balance',[(False,[-100,180,100],50180),(True,[-140,180,100],50140)])
def test_real_mnq_vwap_rerun_uses_known_decision_risk_and_actual_gap_fills(phase,gap,expected_net,expected_balance):
    from native_replay_fixtures import bars,parameters
    from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
    observed=bars(gap=gap);config=ExecutionConfig(D(50000),D('.25'),D(2),0,D(0))
    control=controller(observed,phase,size=sizing('percentage_risk'))
    strategy=VwapPullbackRiskSizing(parameters(),execution_config=config,instrument_symbol='MNQ')
    events=list(execute(observed,strategy,config,account_control=control,completion='require_flat',capture_risk=True,capture_decisions=True))
    trades=[event for event in events if type(event) is Trade];result=control.finish_replay()
    assert [trade.contracts for trade in trades]==[10,9,5]
    assert [trade.net_pnl for trade in trades]==list(map(D,expected_net))
    assert events[-1].equity==D(expected_balance)
    assert all(row['decision_reference_price']=='118' for row in result['sizing_decisions'])
    assert [D(row['denominator_value']) for row in result['sizing_decisions']]==list(map(D,[50000,49860,50040] if gap else [50000,49900,50080]))


def test_real_vwap_zero_quantity_preserves_same_session_opportunity_allowance():
    from native_replay_fixtures import bars,parameters
    from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
    observed=bars(days=1,skip_retry=True);config=ExecutionConfig(D(50000),D('.25'),D(2),0,D(0))
    control=controller(observed,size=sizing(risk_dollars='1'))
    strategy=VwapPullbackRiskSizing(parameters(),execution_config=config,instrument_symbol='MNQ')
    events=list(execute(observed,strategy,config,account_control=control,completion='require_flat',capture_risk=True,capture_decisions=True))
    trades=[event for event in events if type(event) is Trade];result=control.finish_replay()
    assert len(trades)==1 and trades[0].contracts==2 and trades[0].net_pnl==D(12)
    assert trades[0].entry_time_utc.astimezone(__import__('zoneinfo').ZoneInfo('America/Chicago')).strftime('%H:%M')=='09:07'
    assert result['sizing']['summary']['skipped_count']>=1
    assert result['sizing']['summary']['trade_count']==1 and events[-1].equity==D(50012)


def test_fractional_actual_exit_cost_can_breach_account_after_daily_trigger():
    bars=bars_for([(FIRST,[100,100])])
    size=SizingConfiguration(dict(kind='fixed_contracts',contracts=1),'50000',
        dict(tick_size='.25',point_value='2',commission_per_contract_per_side='1000.005'))
    trades,last,result,_=run(bars,controller(bars,size=size),{1:95},fee='1000.005')
    assert len(trades)==1 and trades[0].total_commissions==D('2000.010')
    assert trades[0].exit_reason=='native_daily_floor'
    assert result['outcome']=='blown' and last.equity==D('47999.990')
    close=next(row for row in result['control_events'] if row['event']=='trade_close')
    assert close['triggering_floor']=='daily' and close['account_hit']==2


def test_real_vwap_payout_keeps_generic_source_capital_separate_from_provider_base():
    from native_replay_fixtures import bars,parameters
    from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing
    observed=bars(days=7,payout=True);config=ExecutionConfig(D(10000),D('.25'),D(2),0,D(0))
    control=controller(observed,size=sizing('fixed_contracts',contracts=3),receipt_delay=2)
    strategy=VwapPullbackRiskSizing(parameters(),execution_config=config,instrument_symbol='MNQ')
    events=list(execute(observed,strategy,config,account_control=control,completion='require_flat',capture_risk=True,capture_decisions=True))
    trades=[event for event in events if type(event) is Trade];result=control.finish_replay()
    assert len(trades)==7 and all(trade.net_pnl==D(900) for trade in trades)
    assert D(result['trading_profit'])==D(6300) and events[-1].equity==D(16300)
    assert D(result['equity'])==D(4800) and D(result['cash_received'])==D(1500)
    assert result['payout_events'][0]['request_date']=='2026-01-09'
    assert result['payout_events'][0]['receipt_date']=='2026-01-11'
    assert result['conservation']['cumulative_gross_withdrawals']=='1500.0'


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_actual_native_quantity_obeys_opening_provider_tier_and_distinct_user_cap(profile):
    bars=bars_for([(FIRST,[100,140]),(FIRST+timedelta(days=1),[100,100])])
    control=NativeFundedController(FundedProfile(profile,rule_version(profile)),sizing('fixed_contracts',contracts=40),40,
        max_micros=25,session_contexts=contexts(bars),start_date=FIRST,
        cutoff_date_exclusive=FIRST+timedelta(days=2),receipt_delay_calendar_days=0)
    trades,_,result,_=run(bars,control,{1:95,3:95})
    assert [trade.contracts for trade in trades]==[20,25]
    assert [row['caps']['provider'] for row in result['sizing_decisions']]==[20,30]
    assert [row['caps']['user'] for row in result['sizing_decisions']]==[25,25]


@pytest.mark.parametrize('dll,gross,receipt,trades_taken',[(True,500,450,5),(False,600,540,6)])
def test_lucid_actual_payout_pauses_remaining_entries_only_under_declared_dll_mode(dll,gross,receipt,trades_taken):
    days=[(FIRST+timedelta(days=i),[100,110]) for i in range(4)]
    days.append((FIRST+timedelta(days=4),[100,110,100,110]))
    bars=bars_for(days)
    control=NativeFundedController(FundedProfile('lucidflex-50k',rule_version('lucidflex-50k'),daily_loss_limit=dll),
        sizing('fixed_contracts'),40,max_micros=40,session_contexts=contexts(bars),start_date=FIRST,
        cutoff_date_exclusive=FIRST+timedelta(days=5),receipt_delay_calendar_days=0)
    trades,_,result,_=run(bars,control,{i:95 for i in range(1,13,2)})
    assert len(trades)==trades_taken and D(result['gross_account_deductions'])==D(gross)
    assert D(result['cash_received'])==D(receipt)
    assert len(result['payout_events'])==1
    assert result['modeled_rules']['parameters']['daily_loss']==('1200.0' if dll else None)

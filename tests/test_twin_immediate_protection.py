"""Independent entry-bar outcomes; never assume the adverse extreme followed entry."""
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal as D

import pytest

from alphaquest.execution import execute, Trade, ExecutionError
from alphaquest.intratrade import IntratradeRisk
from alphaquest.strategy import EntryIntent, EntryProtection, StopEntriesIntent, CloseIntent, BracketIntent
from alphaquest.strategies.twin_continuation import TwinContinuation, Parameters
from test_twin_continuation import prices, config, momentum_parameters, momentum_rows, breakout_rows, CT


@pytest.mark.parametrize('short',[False,True])
def test_momentum_is_protected_during_open_entry_bar(short):
    s=TwinContinuation(momentum_parameters(immediate_protection=True))
    events=list(execute(momentum_rows(short=short),s,config(),capture_risk=True))
    t=next(e for e in events if type(e) is Trade)
    assert (t.entry_bar_number,t.exit_bar_number)==(26,26)
    assert t.exit_reason=='stop_loss' and t.net_pnl==-1507
    assert t.entry_fill_price==D('87.75' if short else '112.25')
    assert t.exit_fill_price==D('163' if short else '37')
    assert s.total_trades==1 and s.setup is None


@pytest.mark.parametrize('short',[False,True])
def test_breakout_target_activates_after_intrabar_fill_on_same_bar(short):
    s=TwinContinuation(Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1))
    events=list(execute(breakout_rows(short),s,config(),capture_risk=True))
    t=next(e for e in events if type(e) is Trade)
    assert (t.entry_bar_number,t.exit_bar_number)==(106,106)
    assert t.exit_reason=='take_profit' and t.net_pnl==318
    assert t.exit_fill_price==D('73.75' if short else '126.25')
    risk=next(e for e in events if type(e) is IntratradeRisk)
    assert risk.entry_phase=='entry_stop' and risk.exit_phase=='target'
    # Neither the later Close nor prices past the target are known held.
    assert risk.mfe_lower==D(319) and risk.mfe_upper==D(319)  # $320 less the entry-side $1 fee.
    assert risk.mae_lower==6 and risk.mae_upper==226
    assert s.total_trades==1


class EntryOnly:
    def __init__(self,entry,trigger=None): self.entry,self.trigger=entry,trigger
    def on_bar(self,bar,position):
        if bar.bar_number==1:
            return self.entry if self.trigger is None else StopEntriesIntent(((self.entry,self.trigger),))
    def on_finish(self,bar,position): return CloseIntent('end_of_data') if position is not None else None


def sample(entry_bar):
    start=datetime(2024,1,16,9,tzinfo=CT)
    return [prices(1,start,100,101,99,100),prices(2,start+timedelta(minutes=1),*entry_bar)]


@pytest.mark.parametrize('ohlc',[(100,130,85,115),(100,115,85,100)])
def test_unknown_adverse_extreme_order_rejects_instead_of_fabricating_stop(ohlc):
    entry=EntryIntent(1,'BO-L',timing='next_open',protection=EntryProtection(stop_price=D(90),target_distance=D(10)))
    with pytest.raises(ExecutionError,match='Immediate entry protection is ambiguous'):
        list(execute(sample(ohlc),EntryOnly(entry,D(110)),replace(config(),slippage_ticks=0)))


def test_stop_definitely_after_entry_when_close_beyond_it_and_target_not_reached():
    entry=EntryIntent(1,'BO-L',timing='next_open',protection=EntryProtection(stop_price=D(90),target_distance=D(20)))
    t=next(e for e in execute(sample((100,115,85,88)),EntryOnly(entry,D(110)),replace(config(),slippage_ticks=0)) if type(e) is Trade)
    assert t.exit_reason=='stop_loss' and t.exit_fill_price==90 and t.net_pnl==-402


def test_gap_entry_target_uses_actual_fill_and_frozen_distance():
    entry=EntryIntent(1,'BO-L',timing='next_open',protection=EntryProtection(stop_price=D(90),target_distance=D(16)))
    t=next(e for e in execute(sample((120,140,119,139)),EntryOnly(entry,D(110)),config()) if type(e) is Trade)
    assert t.entry_fill_price==D('120.25') and t.exit_fill_price==D('136.25') and t.net_pnl==318


def test_open_entry_stop_and_target_conflict_retains_declared_stop_first():
    entry=EntryIntent(1,'market',timing='next_open',protection=EntryProtection(stop_distance=D(5),target_distance=D(5)))
    t=next(e for e in execute(sample((100,110,90,105)),EntryOnly(entry),replace(config(),slippage_ticks=0)) if type(e) is Trade)
    assert t.exit_reason=='stop_loss' and t.exit_fill_price==95


def test_immediate_default_and_legacy_mode_are_explicit():
    assert Parameters().immediate_protection is True
    p=momentum_parameters(immediate_protection=False)
    t=next(e for e in execute(momentum_rows(),TwinContinuation(p),config()) if type(e) is Trade)
    assert t.entry_bar_number==26 and t.exit_bar_number==28 and t.net_pnl==148


def test_zero_atr_rejects_enabled_native_target_or_cap_but_allows_absolute_stop_only():
    s=TwinContinuation(Parameters())
    with pytest.raises(ValueError,match='positive frozen 15-minute ATR'):s._protection(stop=D(90))
    s=TwinContinuation(Parameters(bo_target_mult=D(0)))
    assert s._protection(stop=D(90))==EntryProtection(stop_price=D(90))


def test_stop_cap_normalizes_adversely_and_is_active_on_entry_bar():
    entry=EntryIntent(1,'BO-L',timing='next_open',protection=EntryProtection(
        stop_price=D(90),max_stop_distance=D('2.1'),target_distance=D(16)))
    t=next(e for e in execute(sample((109,113,107,107)),EntryOnly(entry,D(110)),config()) if type(e) is Trade)
    assert t.entry_fill_price==D('110.25') and t.exit_reference_price==108
    assert t.exit_fill_price==D('107.75') and t.net_pnl==-52


def test_tight_cap_can_be_marketable_at_known_entry_reference_after_slippage():
    entry=EntryIntent(1,'BO-L',timing='next_open',protection=EntryProtection(
        stop_price=D(90),max_stop_distance=D('.1')))
    events=list(execute(sample((100,113,99,112)),EntryOnly(entry,D(110)),config(),capture_risk=True))
    t=next(e for e in events if type(e) is Trade)
    assert t.exit_reason=='stop_loss' and t.exit_reference_price==110 and t.net_pnl==-12
    risk=next(e for e in events if type(e) is IntratradeRisk)
    assert risk.mfe_upper==0 and risk.mae_upper==12  # No later range belongs to this immediate fill/exit.


def test_supplied_trade_216_entry_bar_target_differs_from_delayed_next_open_fill():
    # Actual supplied prices, plus its precommitted frozen ATR. This qualifies
    # the OHLC execution calculation, not tick execution or a new MC export.
    start=datetime(2022,10,13,7,30,tzinfo=CT)
    rows=[prices(1,start,10987.5,10999,10903.75,10932.5),
          prices(2,start+timedelta(minutes=1),10920,10932.5,10550,10553.25),
          prices(3,start+timedelta(minutes=2),10551.5,10570.75,10511.75,10542.75)]
    class Example:
        def __init__(self,immediate):self.immediate=immediate
        def on_bar(self,bar,position):
            if bar.bar_number==1:
                plan=EntryProtection(stop_price=D('11039.5'),target_distance=D('52.472951907125136')) if self.immediate else None
                return StopEntriesIntent(((EntryIntent(1,'BO-S',side='short',timing='next_open',protection=plan),D('10767.25')),))
            if position is not None:return BracketIntent(D('11039.5'),D('10714.75'))
        def on_finish(self,bar,position):return CloseIntent('end_of_data') if position is not None else None
    cfg=replace(config(),slippage_ticks=0,commission_per_contract_per_side=D(0))
    immediate=next(e for e in execute(rows,Example(True),cfg) if type(e) is Trade)
    legacy=next(e for e in execute(rows,Example(False),cfg) if type(e) is Trade)
    assert immediate.exit_bar_number==2 and immediate.exit_fill_price==D('10714.75') and immediate.net_pnl==1050
    assert legacy.exit_bar_number==3 and legacy.exit_fill_price==D('10551.5') and legacy.net_pnl==4315


@pytest.mark.parametrize('args',[{},dict(stop_price=D(90),stop_distance=D(10)),dict(stop_distance=D(-1))])
def test_invalid_protection_shape_rejects(args):
    with pytest.raises(ValueError): EntryProtection(**args)

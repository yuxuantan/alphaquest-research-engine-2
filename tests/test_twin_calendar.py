"""MC export is an immutable test oracle, never a production engine input."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
import json
from pathlib import Path

import pytest

from alphaquest.backtest_data import DatasetReadError
from alphaquest.execution import execute,Trade
from alphaquest.session_calendar import CalendarError
from alphaquest.strategy import EntryIntent,BracketIntent
from alphaquest.strategies.twin_continuation import TwinContinuation,Parameters
from test_twin_continuation import CT,prices,config

REFERENCE=json.loads((Path(__file__).parent/'fixtures/twin_continuation/mc_early_close_reference.json').read_text())


class SessionProbe(TwinContinuation):
    """Supply known entries to isolate the production calendar/exit mechanics."""
    def __init__(self,ref,*,calendar=True):
        super().__init__(Parameters(max_bars_back=0,use_breakout=False,use_momentum=False,use_session_calendar=calendar))
        self.ref=ref
    def on_bar(self,bar,position):
        result=super().on_bar(bar,position)
        if bar.bar_number==1:
            long=self.ref['entry']['type']=='EntryLong'
            self.pending_setup=self.ref['entry']['signal'].split('-')[0]
            self.stop_long=D(self.ref['entry']['price'])-100
            self.stop_short=D(self.ref['entry']['price'])+100
            self.arm_atr=D(1000)
            return EntryIntent(1,self.ref['entry']['signal'],side='long' if long else 'short',timing='next_open')
        return result


def source_rows(ref):
    entry=datetime.fromisoformat(ref['entry']['time']).replace(tzinfo=CT)
    close=datetime.fromisoformat(ref['exit']['time']).replace(tzinfo=CT)
    ep,xp=D(ref['entry']['price']),D(ref['exit']['price'])
    return [prices(1,entry-timedelta(minutes=1),ep,ep+D('.25'),ep-D('.25'),ep),
            prices(2,entry,ep,ep+D('.25'),ep-D('.25'),ep),
            prices(3,close,xp,xp+D('.25'),xp-D('.25'),xp),
            prices(4,close.replace(hour=17,minute=1),xp,xp+D('.25'),xp-D('.25'),xp)]


@pytest.mark.parametrize('ref',REFERENCE['trades'],ids=lambda t:'MC-'+str(t['trade']))
@pytest.mark.parametrize('costs',[False,True])
def test_observed_mc_noon_session_exit_and_costs_once(ref,costs):
    settings=config() if costs else replace(config(),slippage_ticks=0,commission_per_contract_per_side=D(0))
    events=list(execute(source_rows(ref),SessionProbe(ref),settings,capture_risk=True))
    trade=next(e for e in events if type(e) is Trade)
    assert trade.entry_reason==ref['entry']['signal'] and trade.exit_reason=='session_close'
    assert trade.entry_time_utc==datetime.fromisoformat(ref['entry']['time']).replace(tzinfo=CT).astimezone(timezone.utc)
    assert trade.exit_time_utc==datetime.fromisoformat(ref['exit']['time']).replace(tzinfo=CT).astimezone(timezone.utc)
    assert trade.contracts==1 and trade.entry_reference_price==D(ref['entry']['price'])
    assert trade.exit_reference_price==D(ref['exit']['price'])
    assert trade.reference_gross_pnl==D(ref['entry']['profit'])
    # One market tick on each side costs 10 CU round trip plus 2 CU fees.
    assert trade.net_pnl==D(ref['entry']['profit'])-(12 if costs else 0)


def test_missing_known_early_closing_bar_rejects_before_evening_bracket():
    ref=REFERENCE['trades'][0];rows=source_rows(ref)
    rows[2]=replace(rows[2],timestamp_utc=rows[2].timestamp_utc-timedelta(minutes=1))
    with pytest.raises(DatasetReadError,match='2021-09-06 12:00'):
        list(execute(rows,SessionProbe(ref),config()))


def test_truncation_does_not_promote_1159_to_session_close():
    ref=REFERENCE['trades'][0];rows=source_rows(ref)[:3]
    rows[2]=replace(rows[2],timestamp_utc=rows[2].timestamp_utc-timedelta(minutes=1))
    trade=next(e for e in execute(rows,SessionProbe(ref),config()) if type(e) is Trade)
    assert trade.exit_reason=='end_of_data' and trade.exit_time_utc==rows[-1].timestamp_utc


def test_existing_price_exit_on_closing_bar_has_priority():
    ref=REFERENCE['trades'][0];rows=source_rows(ref)
    stop=D(ref['entry']['price'])-100
    rows[2]=replace(rows[2],low=stop-D(1))
    trade=next(e for e in execute(rows,SessionProbe(ref),replace(config(),slippage_ticks=0)) if type(e) is Trade)
    assert trade.exit_reason=='stop_loss' and trade.exit_reference_price==stop


def test_calendar_coverage_and_instrument_admission_are_explicit():
    for symbol in ('NQ','NQZ26','MNQ','MNQZ26'):
        assert TwinContinuation(instrument_symbol=symbol).calendar is not None
    for symbol in ('','ES','arbitrary_NQ_file.csv'):
        with pytest.raises(CalendarError,match='No reviewed'):TwinContinuation(instrument_symbol=symbol)
    s=TwinContinuation()
    with pytest.raises(CalendarError,match='does not cover'):
        s.on_bar(prices(1,datetime(2026,11,4,9,tzinfo=CT)),None)
    with pytest.raises(ValueError,match='Calendar session exits require'):
        Parameters(bo_session_close=1559)


def test_legacy_fixed_clock_mode_remains_explicit():
    ref=REFERENCE['trades'][0]
    with pytest.raises(DatasetReadError,match='2021-09-06 16:00'):
        list(execute(source_rows(ref),SessionProbe(ref,calendar=False),config()))
    assert not TwinContinuation(Parameters(use_session_calendar=False),instrument_symbol='ES').session_flattening['enabled']


@pytest.mark.parametrize('long,raw,expected',[(True,'100.01','100.25'),(False,'100.24','100.00'),
                                           (True,'100.25','100.25'),(False,'100.25','100.25')])
def test_target_tick_normalization_is_outward(long,raw,expected):
    # Use the real holding callback, with a deliberately fractional ATR target.
    from alphaquest.strategy import Position
    s=TwinContinuation(Parameters(max_bars_back=0,bo_target_mult=D(1)),execution_config=config())
    stamp=datetime(2024,1,16,10,tzinfo=CT).astimezone(timezone.utc)
    entry=D(99) if long else D(101)
    s.setup=s.pending_setup='BO';s.was_holding=True
    s.stop_long=D(90);s.stop_short=D(110)
    s.arm_atr=abs(D(raw)-entry)
    pos=Position(1,stamp,entry,1,'long' if long else 'short')
    intent=s.on_bar(prices(2,stamp+timedelta(minutes=1),entry,entry+D('.25'),entry-D('.25'),entry),pos)
    assert type(intent) is BracketIntent and intent.target_price==D(expected)

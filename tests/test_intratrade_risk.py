"""Independent held-bar boundaries, costs, and prop breach expectations."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D, localcontext
import csv
from hashlib import sha256
import json

import pytest

from alphaquest.execution import execute, Trade, EquityPoint
from alphaquest.intratrade import IntratradeRisk
from alphaquest.reporting import generate_report, ReportError
from alphaquest.strategy import EntryIntent, CloseIntent, BracketIntent
from alphaquest.prop.native_analysis import day_book, resolved_settings
from alphaquest.prop.native_engine import FundedAccount
from alphaquest.prop.native_backend import FundedAccount as ActiveAccount
from test_execution import bar, config


class Orders:
    def __init__(self, orders):self.orders=orders
    def on_bar(self, bar, position):return self.orders.get(bar.bar_number)
    def on_finish(self, bar, position):return CloseIntent('finish') if position else None


def candle(n, o, h, l, c):
    return replace(bar(n,str(c)),open=D(o),high=D(h),low=D(l))


def replay(bars, orders, settings=None):
    return list(execute(bars, Orders(orders), settings or config(slippage_ticks=0,commission_per_contract_per_side=D(0)),capture_risk=True))


def risk(events):return next(e for e in events if isinstance(e,IntratradeRisk))


@pytest.mark.parametrize('side,prices,adverse,favorable',[
    ('long',('100','106','80','105'),'200','60'),
    ('short',('100','120','94','95'),'200','60')])
def test_profitable_trade_can_breach_funded_account_intratrade(side,prices,adverse,favorable):
    events=replay([candle(1,'100','1000','1','100'),candle(2,*prices)],{1:EntryIntent(1,'entry',side=side),2:CloseIntent('exit')})
    r=risk(events)
    assert r.net_pnl==50 and r.mae_lower==r.mae_upper==D(adverse)
    assert r.mfe_lower==r.mfe_upper==D(favorable)
    # Locked floor +100, opening +200. Winner recovers +50 at close, but the
    # observed -200 touches/crosses the +100 account floor first.
    for cls in (FundedAccount,ActiveAccount):
        old=cls(equity=200.,high=2200.,locked=True)
        old.advance([(float(r.net_pnl),0.)],10)
        assert old.outcome=='open' and old.equity==250.
        observed=cls(equity=200.,high=2200.,locked=True)
        observed.advance([(float(r.net_pnl),float(r.mae_upper))],10)
        assert observed.outcome=='blown'


def test_entry_exit_costs_are_in_excursions_once_and_financial_events_unchanged():
    bars=[bar(1,'100'),candle(2,'100','102','99','102')]
    orders={1:EntryIntent(2,'entry'),2:CloseIntent('exit')}
    settings=config() # point10; slip.25 per market side; fee1 per side
    captured=replay(bars,orders,settings)
    original=list(execute(bars,Orders(orders),settings))
    assert [e for e in captured if type(e) in (Trade,EquityPoint)]==original
    r=risk(captured)
    # Low mark: (99 - 100.25)*2*10 - 2 entry fee = -27.
    # High mark: (102 - 100.25)*2*10 - 2 = +33.
    # Net exit: (101.75 - 100.25)*2*10 - 4 = +26.
    assert (r.mae_upper,r.mfe_upper,r.net_pnl)==(D(27),D(33),D(26))
    assert r.full_bars==1 and r.entry_phase=='close' and r.exit_phase=='close'
    with localcontext() as ctx:
        ctx.prec=1
        assert risk(replay(bars,orders,settings))==r


def test_next_open_entry_includes_entry_bar_and_open_exit_excludes_later_prices():
    r=risk(replay([bar(1),candle(2,'100','110','80','105'),candle(3,'105','999','1','106')],
        {1:EntryIntent(1,'entry',timing='next_open'),2:CloseIntent('exit',timing='next_open')}))
    assert (r.mae_lower,r.mae_upper,r.mfe_upper)==(D(200),D(200),D(100))
    assert (r.entry_phase,r.exit_phase,r.full_bars)==('open','open',1)


@pytest.mark.parametrize('side,o,h,l,expected',[
    ('long','100','120','1',(D(50),D(50),D(0),D(200),'stop')),
    ('long','100','120','97',(D(0),D(30),D(50),D(50),'target')),
    ('short','100','999','80',(D(50),D(50),D(0),D(200),'stop')),
    ('short','100','103','80',(D(0),D(30),D(50),D(50),'target')),
    ('long','90','999','1',(D(100),D(100),D(0),D(0),'open')),
    ('long','110','999','1',(D(0),D(0),D(100),D(100),'open')),
])
def test_bracket_boundaries_do_not_use_prices_after_exit(side,o,h,l,expected):
    bracket=BracketIntent(D(95),D(105)) if side=='long' else BracketIntent(D(105),D(95))
    r=risk(replay([bar(1),bar(2),candle(3,o,h,l,o)],{1:EntryIntent(1,'entry',side=side),2:bracket}))
    assert (r.mae_lower,r.mae_upper,r.mfe_lower,r.mfe_upper,r.exit_phase)==expected


def test_daily_loss_stop_is_applied_to_winners_before_recovery():
    a=FundedAccount();a.advance([(800.,1200.)],10)
    assert a.outcome=='open' and a.equity==-1000.
    a.advance([(800.,1200.)],10)
    assert a.outcome=='blown' # Second day's DLL equals the EOD floor -2000.


def test_artifact_and_overnight_rejection(tmp_path):
    settings=config(slippage_ticks=0,commission_per_contract_per_side=D(0))
    bars=[bar(1),replace(candle(2,'100','106','80','105'),timestamp_utc=bar(2).timestamp_utc+timedelta(days=1))]
    events=replay(bars,{1:EntryIntent(1,'entry'),2:CloseIntent('exit')},settings)
    manifest=generate_report(events,tmp_path/'run',settings,capture_risk=True,detail='compact')
    assert manifest['intratrade_risk']['cross_session_trades']==1
    artifact=tmp_path/'run/intratrade_risk.csv'
    assert sha256(artifact.read_bytes()).hexdigest()==manifest['intratrade_risk']['sha256']
    row=list(csv.DictReader(artifact.open()))[0]
    assert D(row['mae_upper'])==200 and row['cross_session']=='True'
    with pytest.raises(ValueError,match='overnight'):
        day_book([dict(trade_id=1,entry_utc=row['entry_time_utc'],exit_utc=row['exit_time_utc'],quantity='1',source_net_pnl='50',export_net_pnl=None,measured_mae=None,risk_cross_session=True,ohlc_mae_upper='200')],resolved_settings({}))
    with pytest.raises(ReportError,match='Missing intratrade'):
        generate_report([e for e in events if not isinstance(e,IntratradeRisk)],tmp_path/'missing',settings,capture_risk=True)
    assert not (tmp_path/'missing').exists()


@pytest.mark.parametrize('path,outcome,balance',[
    (((2500.,True),),'blown',-2500.),
    (((1100.,False),(2500.,True)),'open',-1000.),
    (((1500.,True),(2500.,False)),'open',-1500.),
    (((2000.,True),),'blown',-2000.),
])
def test_observed_gap_can_breach_both_floors_but_later_gap_after_dll_is_ignored(path,outcome,balance):
    from dataclasses import asdict
    results=[]
    for cls in (FundedAccount,ActiveAccount):
        a=cls();a.advance([(800.,path[-1][0],path)],10)
        assert a.outcome==outcome and a.equity==balance
        results.append(asdict(a))
    assert results[0]==results[1]


def test_bar_open_gap_is_in_ordered_frontier_and_affects_evaluation():
    from alphaquest.prop import native_engine,native_backend
    events=replay([bar(1),candle(2,'-150','106','-150','105')],{1:EntryIntent(1,'entry'),2:CloseIntent('exit')})
    r=risk(events)
    assert json.loads(r.adverse_path)==[['2500.00',True]]
    path=tuple((float(v),gap) for v,gap in json.loads(r.adverse_path))
    for model in (native_engine,native_backend):
        a=model.FundedAccount();a.advance([(float(r.net_pnl),float(r.mae_upper),path)],10)
        assert a.outcome=='blown' and a.equity==-2500.
        evaluation=model.evaluation([[(3000.,2500.,path)]],10,3,42)
        assert evaluation['outcomes'].tolist()==['blown']*3


def test_compressed_frontier_matches_independent_expanded_mark_ledger():
    """Check every original mark, independently of the production frontier scan."""
    from random import Random
    from alphaquest.prop.native_engine import Rules
    rng=Random(7591)
    rules=replace(Rules(),qualifying_days=100000,inactivity_window=100000)
    for _ in range(400):
        opening=float(rng.randint(-1000,5000));high=float(rng.randint(max(0,int(opening)),int(opening)+1999))
        micros=rng.randint(1,80);user_cap=rng.randint(1,60)
        cap=20 if opening<1500 else 30 if opening<3000 else 40
        dll=1000 if opening<3000 else 2000 if opening<6000 else 3000
        size=min(micros,cap,user_cap);floor=min(high-2000.,100.)
        threshold=max(opening-dll,floor)
        marks=[(float(rng.randint(-4500,3000)),bool(rng.getrandbits(1))) for i in range(20)]
        net=float(rng.randint(-2500,3000));marks.append((net,True))
        expected_balance=opening+net*size/10.;expected_outcome='open'
        # This oracle scans the uncompressed marked-equity series, not MAE or
        # the production account/first-hit functions.
        for pnl,jump in marks:
            marked=opening+pnl*size/10.
            if marked<=threshold:
                expected_balance=marked if jump else threshold
                expected_outcome='blown' if expected_balance<=floor else 'open'
                break
        frontier=[];worst=0.
        for pnl,jump in marks:
            if -pnl>worst:
                worst=-pnl;frontier.append((worst,jump))
        for cls in (FundedAccount,ActiveAccount):
            account=cls(rules=rules,equity=opening,high=high)
            account.advance([(net,worst,tuple(frontier))],micros,user_cap)
            assert account.outcome==expected_outcome
            assert account.equity==pytest.approx(expected_balance,abs=1e-9)

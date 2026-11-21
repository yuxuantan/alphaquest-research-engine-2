"""Independent risk quantities, real native execution and exact cash conservation."""
from dataclasses import asdict
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
import json

import pytest

from alphaquest.strategy import ExecutionConfig
from alphaquest.prop.native_control import SessionContext
from alphaquest.prop.phase_profiles import EvaluationProfile,FundedProfile,SizingConfiguration,rule_version
from alphaquest.prop.phase_search import PhaseCalendar
from alphaquest.prop.evaluation_optimization import SequentialRetry
from alphaquest.prop.portfolio_lifecycle import run_lineup
from alphaquest.prop.portfolio_cash import PortfolioCash
from alphaquest.prop.portfolio_search import family
from alphaquest.prop.portfolio_sources import session_coverage
from alphaquest.session_calendar import CT,session_date
from native_replay_fixtures import bars,parameter_values


def context(*,days=3,payout=False,strategies=1,profile='apex-50k-eod',kind='percentage_risk'):
    rows=bars(days=days,payout=payout);books={}
    for b in rows:books.setdefault(session_date(b.timestamp_utc),[]).append(b)
    first=min(books);last=max(books)
    sessions={day:SessionContext(day,rs[-1].timestamp_utc,'SYNTHETIC-full-session','a'*64,len(rs),True) for day,rs in books.items()}
    policy=dict(kind=kind,maximum_contracts=40,**(dict(contracts=3) if kind=='fixed_contracts' else dict(risk_percent='.2',reference='current_account_balance')))
    sizing=SizingConfiguration(policy,'50000',dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))
    common=dict(profile_id=profile,rule_version=rule_version(profile),daily_loss_limit=True)
    return dict(first=str(first),last=str(last),bars=books,sessions=sessions,
        strategies=[dict(strategy_id='vwap_pullback_risk_sizing',parameters=parameter_values(),symbol='MNQ') for _ in range(strategies)],
        execution=ExecutionConfig(initial_capital=Decimal(10000),tick_size=Decimal('.25'),point_value=Decimal(2),slippage_ticks=0,commission_per_contract_per_side=Decimal(0)),monthly_cap='500',receipt_delay=2,
        evaluation_sizing=sizing,funded_sizing=sizing,evaluation_profile=EvaluationProfile(**common,evaluation_price='49',activation_fee='129' if profile=='apex-50k-eod' else '0'),
        funded_profile=FundedProfile(**common),calendar=PhaseCalendar((str(first),),str(last+timedelta(days=2)),()),
        retry=SequentialRetry(activation_delay_sessions=1 if profile=='apex-50k-eod' else 0),sources=[])


def test_percentage_risk_reexecutes_and_matches_known_native_quantities():
    result=run_lineup(context(),dict(placement='separate',counts=[1]),capture=True)
    assert [r['contracts'] for r in result['trades']]==[10,9,5]
    assert [Decimal(r['net_pnl']) for r in result['trades']]==[-100,180,100]
    assert result['cash']['net_cash']=='-49.00' # Trading profits are not bank receipts.
    assert result['counts']['evaluation_attempts']==1
    assert [Decimal(d['decision']['denominator_value']) if 'decision' in d else Decimal(d['denominator_value']) for d in result['sizing_decisions']]==[50000,49900,50080]


def test_shared_one_strategy_matches_separate_account_and_never_invents_overlap():
    c=context();a=run_lineup(c,dict(placement='separate',counts=[1]),capture=True)
    b=run_lineup(c,dict(placement='shared',weights=[4],accounts=1),capture=True)
    assert a['cash']==b['cash'] and a['trades']==b['trades']
    mixed=run_lineup(context(strategies=2),dict(placement='shared',weights=[2,2],accounts=1),capture=True)
    assert mixed['trades'][0]['contracts']==5
    assert all(a['exit']<=b['entry'] for a,b in zip(mixed['trades'],mixed['trades'][1:]))
    assert all(Decimal(d['allocation_weight'])==Decimal('.5') for d in mixed['sizing_decisions'])


def test_initial_capital_percentage_keeps_budget_stable_and_wider_stops_reduce_size():
    c=context();p=dict(c['evaluation_sizing'].policy,reference='initial_configured_capital')
    c['evaluation_sizing']=SizingConfiguration(p,'50000',c['evaluation_sizing'].planning_execution)
    r=run_lineup(c,dict(placement='separate',counts=[1]),capture=True)
    assert [t['contracts'] for t in r['trades']]==[10,10,5]
    assert all(Decimal(d['risk_budget'])==100 for d in r['sizing_decisions'])


def test_replacements_and_receipts_reconcile_and_never_expand_fee_budget():
    c=context(days=50,payout=True,profile='lucidflex-50k',kind='fixed_contracts');c['monthly_cap']='98'
    r=run_lineup(c,dict(placement='separate',counts=[1]),capture=True)
    assert r['counts']['funded_accounts']>=1
    assert r['counts']['funded_payout_completions']>=1
    assert r['counts']['evaluation_attempts']>=2
    fees=sum(Decimal(e['paid_fee']) for e in r['cash_ledger']);received=sum(Decimal(e['trader_receipt']) for e in r['cash_ledger'])
    assert Decimal(r['cash']['net_cash'])==received-fees
    assert Decimal(r['cash']['received_trader_cash'])==received
    assert all(Decimal(m['paid_fees'])<=98 for m in r['cash']['monthly'])
    assert all(Decimal(e['paid_this_month'])<=98 for e in r['cash_ledger'])


def test_exact_budget_reservations_month_reset_and_delayed_receipts():
    c=PortfolioCash('100','2026-03-01');c.advance(date(2026,1,31))
    assert c.buy(1,'30','40');assert not c.buy(2,'31','0')
    c.release(1,'failed');assert c.buy(1,'30','40');c.activate(1,'40')
    assert c.spent==100
    c.advance(date(2026,2,1));assert c.spent==0 and c.cap==100
    c.payout(1,dict(raw_trader_entitlement='90',gross_account_deduction='100',receipt_date='2026-03-01'))
    assert c.result()['pending_receipts']=='90.00' and c.received==0
    assert c.result()['net_cash']=='-100.00'


def test_zero_purchase_baseline_and_full_finite_allocation_membership():
    allocations=family(2,2,['separate','shared'])
    assert len(allocations)==16 # Six separate vectors, five quarter-share mixes × two account counts.
    assert len({json.dumps(a,sort_keys=True) for a in allocations})==16
    zero=run_lineup(context(),allocations[0],capture=True)
    assert zero['cash']['net_cash']=='0.00' and zero['trades']==[]


def test_session_spool_bounds_worker_input_and_replays_identically(tmp_path):
    import pickle
    from alphaquest.prop.portfolio_sources import SessionBars
    c=context();spool=SessionBars(tmp_path/'sessions')
    for day,rows in c['bars'].items():spool.save(day,rows)
    assert len(pickle.dumps(spool))<2000 # Only paths and hashes cross into workers.
    a=run_lineup(c,dict(placement='separate',counts=[1]),capture=True)
    b=run_lineup(dict(c,bars=spool),dict(placement='separate',counts=[1]),capture=True)
    assert a==b
    assert list(spool.subset(c['first'],c['first']))==[date.fromisoformat(c['first'])]
    filename,_=spool.index[date.fromisoformat(c['first'])]
    from pathlib import Path
    Path(filename).write_bytes(b'corrupt temporary input')
    with pytest.raises(ValueError,match='session source changed'):spool[date.fromisoformat(c['first'])]


def test_portfolio_accepts_historical_cme_pause_in_observed_session():
    day = date(2021, 1, 4)
    start = datetime.combine(day - timedelta(days=1), time(17, 1), CT)
    close = datetime.combine(day, time(16), CT)
    minutes = [start + timedelta(minutes=i) for i in range(23 * 60)]
    # Close labels 15:16–15:30 refer to the scheduled pause. The 15:15 and
    # 15:31 bars must still be present, as must the 16:00 close.
    stamps = [t.astimezone(timezone.utc) for t in minutes if not (time(15, 15) < t.time() <= time(15, 30))]
    coverage = session_coverage(day, close.astimezone(timezone.utc), 900, stamps)
    assert coverage['observed_bars'] == coverage['expected_full_session_bars'] == 1365
    assert coverage['scheduled_pause_minutes'] == 15
    assert coverage['missing_pre_entry_bars'] == 0
    with pytest.raises(ValueError, match='missing a tradable one-minute bar at 15:31'):
        session_coverage(day, close.astimezone(timezone.utc), 900,
                         [t for t in stamps if t.astimezone(CT).time() != time(15, 31)])
    with pytest.raises(ValueError, match='observed bar at the scheduled close'):
        session_coverage(day, close.astimezone(timezone.utc), 900, stamps[:-1])


def test_portfolio_rejects_same_gap_after_cme_removed_pause():
    day = date(2021, 6, 28)
    start = datetime.combine(day, time(15, 15), CT).astimezone(timezone.utc)
    resumed = start + timedelta(minutes=16)
    stamps = [start, *(resumed + timedelta(minutes=i) for i in range(30))]
    with pytest.raises(ValueError, match='missing a tradable one-minute bar at 15:16'):
        session_coverage(day, stamps[-1], 1515, stamps)


def test_final_closed_day_counts_inactivity_without_buying_future_replacement():
    c=context(days=25,payout=True,profile='lucidflex-50k',kind='fixed_contracts')
    end=date(2026,2,8) # Sunday, 30 civil days after Friday 9 January funding.
    c['last']=str(end);c['calendar']=PhaseCalendar((c['first'],),str(end+timedelta(days=2)),())
    c['funded_sizing']=SizingConfiguration(dict(kind='percentage_risk',risk_percent='.000001',reference='initial_configured_capital',maximum_contracts=40),'50000',c['funded_sizing'].planning_execution)
    result=run_lineup(c,dict(placement='separate',counts=[1]),capture=True)
    assert result['counts']['funded_accounts']==1
    assert result['counts']['funded_inactivity_closures']==1
    assert result['counts']['evaluation_attempts']==1
    assert result['open_accounts'][0]['outcome']=='awaiting_replacement'
    assert result['transitions'][-1]['date']=='2026-02-08'
    assert all(row['date']<result['cutoff_exclusive'] for row in result['cash_ledger'])

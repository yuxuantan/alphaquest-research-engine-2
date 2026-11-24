"""Independent risk quantities, real native execution and exact cash conservation."""
from dataclasses import asdict, replace
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
from alphaquest.prop.portfolio_search import optimized_search, full_family, bounded_search, rank, sizing_policies


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
    grid=sizing_policies(dict(minimum=3,maximum=4,step=1))
    plan=dict(placement='separate',counts=[1],sizing=[dict(evaluation=grid[0],funded=grid[1])])
    r=run_lineup(c,plan,capture=True)
    assert r['counts']['funded_accounts']>=1
    assert r['counts']['funded_payout_completions']>=1
    assert r['counts']['evaluation_attempts']>=2
    assert {trade['contracts'] for trade in r['trades'] if trade['phase']=='evaluation'}=={3}
    assert {trade['contracts'] for trade in r['trades'] if trade['phase']=='funded'}=={4}
    fees=sum(Decimal(e['paid_fee']) for e in r['cash_ledger']);received=sum(Decimal(e['trader_receipt']) for e in r['cash_ledger'])
    assert Decimal(r['cash']['net_cash'])==received-fees
    assert Decimal(r['cash']['received_trader_cash'])==received
    assert all(Decimal(m['paid_fees'])<=98 for m in r['cash']['monthly'])
    assert all(Decimal(e['paid_this_month'])<=98 for e in r['cash_ledger'])
    assert run_lineup(c,plan)['cash']==r['cash']


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


def test_joint_family_and_bounded_search_have_explicit_unique_phase_sizes():
    axes=[sizing_policies(dict(minimum=1,maximum=2,step=1))]*2
    spec=optimized_search(2,1,['separate','shared'],axes,128)
    candidates=list(full_family(spec))
    assert spec['grid_size']==1+2*4+4*4==25
    assert len({json.dumps(p,sort_keys=True) for p in candidates})==25
    winner=next(p for p in candidates if p['placement']=='shared'
        and [(s['evaluation']['contracts'],s['funded']['contracts']) for s in p['sizing']]==[(1,2),(2,1)])
    def evaluate(plans,offset):
        return [dict(allocation=p,cash=dict(net_cash=str(10 if p==winner else 0))) for p in plans]
    assert min(evaluate(candidates,0),key=rank)['allocation']==winner
    bounded=optimized_search(2,1,['separate','shared'],axes,12)
    rows=bounded_search(bounded,evaluate)
    assert rows==bounded_search(bounded,evaluate)
    assert len({json.dumps(r['allocation'],sort_keys=True) for r in rows})==bounded['replay_limit']==12
    assert rows[0]['allocation']['sizing']==[None,None]
    assert all(r['allocation'] in candidates for r in rows)
    assert {row['allocation']['placement'] for row in rows}=={'separate','shared'}


@pytest.mark.parametrize('kind,expected',[('fixed_contracts',2),('percentage_risk',2)])
def test_portfolio_twin_oco_matches_standalone_and_blocks_competing_orders(kind,expected):
    from alphaquest.execution import execute,Trade
    from alphaquest.strategies.twin_continuation import TwinContinuation
    from alphaquest.reporting import json_value
    from test_twin_market_preparation import twin_catalogue
    from test_native_draws import owner
    catalogue,params=twin_catalogue(days=1)
    day=catalogue.sessions[0].context.session
    rows=list(catalogue.bars)
    # Touch both breakout entries in one bar. Open is nearer the High, so the
    # shared MultiCharts path fills the buy first and cancels the sell.
    rows[105]=replace(rows[105],open=Decimal('109.75'),low=Decimal(89))
    c=context(days=1,strategies=2)
    c.update(bars={day:rows},sessions={day:catalogue.sessions[0].context})
    c['strategies'][0]=dict(strategy_id='twin_continuation',
        parameters=json.loads(json.dumps(asdict(params),default=json_value)),symbol='MNQ')
    axis=(dict(minimum=2,maximum=2,step=1) if kind=='fixed_contracts' else
          dict(minimum='.2',maximum='.2',step='.1',reference='current_account_balance',maximum_contracts=40))
    policy=sizing_policies(axis)[0]
    profile=lambda value:dict(evaluation=value,funded=value)
    allocation=dict(placement='separate',counts=[1,0],sizing=[profile(policy),None])
    standard=owner(c['sessions'],phase='evaluation',fixed=2 if kind=='fixed_contracts' else None)
    standalone=[e for e in execute(rows,TwinContinuation(params,execution_config=c['execution'],instrument_symbol='MNQ'),
        c['execution'],account_control=standard,completion='require_flat') if type(e) is Trade]
    result=run_lineup(c,allocation,capture=True)
    assert standalone and result['trades']
    assert [(t['side'],t['contracts'],Decimal(t['net_pnl'])) for t in result['trades']]==[
        (t.side,t.contracts,t.net_pnl) for t in standalone]
    assert result['trades'][0]['side']=='long'
    assert result['trades'][0]['contracts']==expected
    assert any(e.get('reason')=='oco_sibling_cancelled' for e in result['accounts'][0]['control_events'])
    other=sizing_policies(dict(minimum=1,maximum=1,step=1))[0]
    shared=run_lineup(c,dict(placement='shared',members=[0,1],accounts=1,
        sizing=[profile(policy),profile(other)]),capture=True)
    assert shared['trades'][0]['strategy']==0 and shared['trades'][0]['contracts']==expected
    assert all(a['exit']<=b['entry'] for a,b in zip(shared['trades'],shared['trades'][1:]))
    conflict=run_lineup(dict(c,strategies=[c['strategies'][0]]*2),
        dict(placement='shared',members=[0,1],accounts=1,sizing=[profile(policy),profile(other)]),capture=True)
    assert conflict['counts']['shared_signal_conflicts']>0
    assert conflict['trades'][0]==result['trades'][0]
    assert all(a['exit']<=b['entry'] for a,b in zip(conflict['trades'],conflict['trades'][1:]))


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
    assert coverage['missing_holding_minutes'] == 0
    incomplete = session_coverage(day, close.astimezone(timezone.utc), 900,
                                 [t for t in stamps if t.astimezone(CT).time() != time(15, 31)])
    assert incomplete['missing_holding_minutes'] == 1
    assert incomplete['holding_gap_ranges_utc'] == [('2021-01-04T21:31:00+00:00',) * 2]
    with pytest.raises(ValueError, match='observed bar at the scheduled close'):
        session_coverage(day, close.astimezone(timezone.utc), 900, stamps[:-1])


def test_portfolio_counts_same_gap_after_cme_removed_pause():
    day = date(2021, 6, 28)
    start = datetime.combine(day, time(15, 15), CT).astimezone(timezone.utc)
    resumed = start + timedelta(minutes=16)
    stamps = [start, *(resumed + timedelta(minutes=i) for i in range(30))]
    coverage = session_coverage(day, stamps[-1], 1515, stamps)
    assert coverage['scheduled_pause_minutes'] == 0
    assert coverage['missing_holding_minutes'] == 15
    assert coverage['holding_gap_ranges_utc'] == [
        ('2021-06-28T20:16:00+00:00', '2021-06-28T20:30:00+00:00')
    ]


def test_portfolio_uses_next_observed_open_when_stop_is_crossed_after_gap():
    c = context(days=1)
    day = date.fromisoformat(c['first'])
    missing_time = datetime.combine(day, time(9, 3), CT).astimezone(timezone.utc)
    resumed_at = missing_time + timedelta(minutes=1)
    bars = [
        replace(bar, open=Decimal(111), low=Decimal(110)) if bar.timestamp_utc == resumed_at else bar
        for bar in c['bars'][day] if bar.timestamp_utc != missing_time
    ]
    c['bars'][day] = bars
    c['sessions'][day] = replace(c['sessions'][day], observed_bar_count=len(bars))
    c['coverage'] = [session_coverage(day, bars[-1].timestamp_utc, 900, [bar.timestamp_utc for bar in bars])]
    allocation = dict(placement='separate', counts=[1])
    result = run_lineup(c, allocation, capture=True)
    trade, = result['trades']
    assert Decimal(trade['entry_fill_price']) == 118
    assert Decimal(trade['exit_fill_price']) == 111
    assert Decimal(trade['net_pnl']) == -140
    assert trade['exit'] == resumed_at.isoformat()
    gap, = [event for event in result['accounts'][0]['control_events'] if event['event'] == 'source_gap']
    assert gap['exposure'] == 'a position is open'
    assert gap['first_missing_utc'] == gap['last_missing_utc'] == missing_time.isoformat()
    assert gap['resumed_at_source_utc'] == resumed_at.isoformat()
    assert run_lineup(c, allocation)['cash'] == result['cash']


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

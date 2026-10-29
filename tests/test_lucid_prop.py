"""Independent LucidFlex cash, drawdown, consistency and publication boundaries."""
from dataclasses import asdict,replace
from decimal import Decimal
import json
import numpy as np
import pytest
from alphaquest.prop import lucid_engine as model,lucid_backend as backend
from alphaquest.prop.native_analysis import DEFAULTS,resolved_settings,calculate
from alphaquest.prop.lucid_rules import defaults


def settings(**overrides):return resolved_settings(dict(defaults(DEFAULTS),**overrides))


def test_default_price_commissions_and_provider_contract_are_distinct():
    from alphaquest.prop.commissions import adapt
    from test_prop_commissions import source
    s=settings();assert s['EVAL_PRICE']=='80.5' and s['ACTIVATION_FEE']=='0' and s['SLOTS']=='5'
    snapshot,rows=source();adapt(snapshot,rows,s)
    # (2000 - 10) / 10 - two 50-cent sides = 198 per micro.
    assert Decimal(rows[0]['simulation_net_per_nq'])/10==198
    assert snapshot['commission_simulation']['per_side']=='0.50'
    assert resolved_settings({})==DEFAULTS
    with pytest.raises(ValueError,match='SLOTS'):settings(SLOTS='6')
    with pytest.raises(ValueError,match='zero activation'):settings(ACTIVATION_FEE='129')
    with pytest.raises(ValueError,match='Unknown'):settings(LUCID_CONSISTENCY='50')


@pytest.mark.parametrize('engine',[model,backend])
def test_evaluation_consistency_no_deadline_and_zero_extra_activation_days(engine):
    r=engine.evaluation([[(30000.,0.)]],1,4,42)
    assert r['outcomes'].tolist()==['passed']*4 and r['days'].tolist()==[3]*4
    r=engine.evaluation([[(1000.,0.)]],1,4,42,chain=True)
    assert r['outcomes'].tolist()==['passed']*4 and r['days'].tolist()==[30]*4
    r=engine.evaluation([[(10.,0.)]],1,4,42,deadline=10)
    assert r['outcomes'].tolist()==['timeout']*4 # Censoring, no provider time failure.


@pytest.mark.parametrize('engine',[model,backend])
def test_gross_withdrawals_and_net_receipts_reset_winning_days_and_force_lock(engine):
    a=engine.FundedAccount()
    for _ in range(5):a.advance([(300.,0.)],10)
    assert a.withdrawals==[(5,750.)] and a.payouts==[(5,675.)]
    assert a.equity==750 and a.locked and a.qualifying==0
    for _ in range(5):a.advance([(300.,0.)],10)
    assert a.withdrawals[-1]==(10,1125.) and a.payouts[-1]==(10,1012.5)
    a.advance([(300.,1030.)],10)
    assert a.outcome=='blown' # Intratrade balance reaches the +100 locked floor.


@pytest.mark.parametrize('engine',[model,backend])
def test_minimum_gross_request_and_five_payout_terminal_boundary(engine):
    a=engine.FundedAccount()
    for _ in range(5):a.advance([(200.,0.)],10)
    assert a.withdrawals==[(5,500.)] and a.payouts==[(5,450.)]
    a=engine.FundedAccount()
    for _ in range(25):a.advance([(1000.,0.)],10)
    assert sum(v for _,v in a.payouts)==9000 and len(a.payouts)==5 and a.outcome=='paid_all'
    with pytest.raises(ValueError,match='closed'):a.advance([],10)


@pytest.mark.parametrize('engine',[model,backend])
def test_on_demand_payout_stops_session_but_dll_off_checks_full_session(engine):
    on=engine.FundedAccount();off=engine.FundedAccount(replace(model.Rules(),daily_loss=None))
    for a in (on,off):
        for _ in range(4):a.advance([(500.,0.)],10)
        a.advance([(500.,0.),(-10000.,10000.)],10)
    assert on.outcome=='open' and on.payouts==[(5,1125.)]
    assert off.outcome=='blown' and not off.payouts
    late=engine.FundedAccount()
    for _ in range(4):late.advance([(500.,0.)],10)
    late.advance([(500.,0.,None,False),(-10000.,10000.,None,False)],10)
    # After 15:45 no early request may skip later risk: the subsequent loss
    # reaches the soft DLL at opening 2,000 minus 1,200, and no payout qualifies.
    assert late.outcome=='open' and late.equity==800 and not late.payouts


@pytest.mark.parametrize('engine',[model,backend])
def test_dll_exact_floor_gaps_and_calendar_inactivity(engine):
    a=engine.FundedAccount();a.advance([(500.,1500.)],10)
    assert a.equity==-1200 and a.outcome=='open'
    a=engine.FundedAccount();a.advance([(500.,2500.,((2500.,True),))],10)
    assert a.equity==-2500 and a.outcome=='blown'
    a=engine.FundedAccount(equity=200.,high=2200.,locked=True);a.advance([(500.,100.)],10)
    assert a.outcome=='blown' # Touch, rather than only strictly below.
    a=engine.FundedAccount()
    for _ in range(30):a.advance([(-1.,1.)],10)
    assert a.outcome=='open' # Losing trades satisfy activity; profits are not required.
    a=engine.FundedAccount()
    for _ in range(23):a.advance([],10)
    assert a.outcome=='inactive' # Monday start -> day 23 is calendar day 30.


@pytest.mark.parametrize('opening,expected',[(999.,20.),(1000.,30.),(1999.,30.),(2000.,40.)])
def test_scaling_uses_prior_close_and_exact_boundaries(opening,expected):
    for engine in (model,backend):
        a=engine.FundedAccount(equity=opening);a.advance([(10.,0.)],40)
        assert a.equity-opening==expected


def test_compiled_accounts_and_mt19937_sampling_match_python_reference():
    assert backend.compiled is not None
    days=[[(800.,40.)],[],[(-400.,700.)],[(1700.,20.)]]
    for seed,block in ((42,1),(43,5),(44,10)):
        left=model.evaluation(days,15,80,seed,block)
        right=backend.evaluation(days,15,80,seed,block)
        assert all(np.array_equal(left[k],right[k]) for k in left)
        for dll in (None,1200.):
            rules=replace(model.Rules(),daily_loss=dll)
            left=model.funded(days,15,80,seed,block,horizon=261,rules=rules)
            right=backend.funded(days,15,80,seed,block,horizon=261,rules=rules)
            assert [asdict(a) for a in left]==[asdict(a) for a in right]


def test_batch_paths_match_independent_step_ledger_and_random_draw_consumption():
    days=[[(800.,40.)],[],[(-400.,700.)],[(1700.,20.,None,False),(-300.,350.,None,False)]]
    for block in (1,5,10):
        rng=np.random.RandomState(42);expected=[]
        for _ in range(100):
            a=model.FundedAccount();remaining=0;index=0
            for day in range(261):
                if not remaining:index=int(rng.randint(len(days)));remaining=block
                a.advance(days[index],15)
                index=(index+1)%len(days);remaining-=1
                if a.outcome!='open':break
            expected.append(asdict(a))
        actual=backend.funded(days,15,100,42,block,horizon=261)
        assert [asdict(a) for a in actual]==expected


def test_standard_counts_independent_known_cash_and_separate_apex_regression():
    import pandas as pd
    rows=[dict(trade_id=i+1,entry_utc=str(d.date())+'T18:00:00Z',exit_utc=str(d.date())+'T18:01:00Z',
        source_net_pnl='3000',export_net_pnl=None,quantity='1',measured_mae='0')
        for i,d in enumerate(pd.bdate_range('2026-01-05',periods=60))]
    r=calculate(rows,settings(MAX_TOTAL_NQ='0.3'))
    t=r['training_economics'];assert (t['pass_rate'],t['cost_per_funded'],t['replacement_days'])==(1,80.5,10)
    assert t['activation_days']==0 and t['funding_chain_simulations']==20000
    assert r['funded']['selected']['micros']==3 and r['funded']['selected']['sims']==20000
    assert r['funded']['selected']['E[payout]']==9000 and r['funded']['selected']['days alive']==25
    # Two 25-day sim-funded accounts, separated by ten evaluation days, fit 60
    # weekdays. Five slots receive 2*9000*5, less 2*80.50*5 acquisition costs.
    assert r['history']['totals']['payouts']==90000
    assert r['history']['totals']['costs']==805
    assert r['history']['totals']['net']==89195
    assert all(row['simulations']==3000 for row in r['evaluation_sweep'])
    assert all(row['sims']==3000 for row in r['funded']['sweep'])


@pytest.mark.parametrize('entry,exit,accepted',[
    ('2026-01-05T20:00:00Z','2026-01-05T21:45:00Z',True),
    ('2026-01-05T20:00:00Z','2026-01-05T21:46:00Z',False),
    ('2026-01-05T22:00:00Z','2026-01-05T22:01:00Z',False),
    ('2026-07-06T18:00:00Z','2026-07-06T20:45:00Z',True),
    ('2026-07-06T18:00:00Z','2026-07-06T20:46:00Z',False),
    ('2026-01-04T23:00:00Z','2026-01-05T18:00:00Z',True),
])
def test_regular_lucid_flatten_cutoff_dst_and_sunday_reopen(entry,exit,accepted):
    from alphaquest.prop.native_analysis import day_book
    row=dict(trade_id=1,entry_utc=entry,exit_utc=exit,source_net_pnl='100',export_net_pnl=None,quantity='1',measured_mae='0')
    if accepted:day_book([row],settings())
    else:
        with pytest.raises(ValueError,match='LucidFlex'):day_book([row],settings())

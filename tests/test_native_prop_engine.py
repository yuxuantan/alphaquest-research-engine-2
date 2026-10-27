from dataclasses import replace
from itertools import islice
from alphaquest.prop.native_engine import FundedAccount,Rules,sampled_days,evaluation,funded
from alphaquest.prop.native_analysis import resolved_settings,replay_history
import numpy as np
import pandas as pd
import pytest


def test_payout_ladder_full_cap_and_approval_day_boundary():
    for approval,expected in [(True,[5,10,15,20,25,30]),(False,[5,11,17,23,29,35])]:
        a=FundedAccount(replace(Rules(),approval_day_counts=approval))
        while a.outcome=='open':a.advance([(800.,0.)],10)
        assert [d for d,_ in a.payouts]==expected
        assert sum(v for _,v in a.payouts)==13000.
        assert a.outcome=='paid_all'


def test_daily_loss_stop_survives_then_touching_drawdown_closes():
    a=FundedAccount();a.advance([(-1500.,1500.),(3000.,0.)],10)
    assert a.equity==-1000. and a.outcome=='open'
    a.advance([(-1500.,1500.)],10)
    assert a.outcome=='blown' and a.day==2


def test_inactivity_window_and_activity_day_exception():
    a=FundedAccount()
    for _ in range(20):a.advance([],10)
    assert a.outcome=='open'
    a.advance([(50.,0.)],10)
    assert a.outcome=='open'  # An active day itself does not close for inactivity.
    a.advance([],10);assert a.outcome=='inactive' and a.day==22


def test_consistency_equality_and_full_cap_cash_boundary():
    a=FundedAccount(replace(Rules(),qualifying_days=2))
    a.advance([(1800.,0.)],10);a.advance([(1800.,0.)],10)
    assert a.payouts==[(2,1500.)] and a.equity==2100.
    b=FundedAccount(replace(Rules(),qualifying_days=2,consistency=.4999))
    b.advance([(1800.,0.)],10);b.advance([(1800.,0.)],10)
    assert not b.payouts


def test_eod_lock_and_prior_close_contract_tier():
    a=FundedAccount();a.advance([(1100.,0.)],30)
    assert a.equity==2200.  # First level cuts the requested 30 to 20 MNQ.
    a.advance([(-2200.,2200.)],30)
    assert a.equity==1200. and a.outcome=='open' # DLL $1000 at prior close +$2200.
    a.advance([(-1200.,1200.)],30)
    assert a.outcome=='open' and a.equity==200.
    a.advance([(-1200.,1200.)],30)
    assert a.outcome=='blown' # Floor locked at +$100, now tighter than the DLL.


def test_streaming_blocks_wrap_and_use_legacy_mt19937():
    assert list(islice(sampled_days(np.random.RandomState(42),10,5),10))==[6,7,8,9,0,3,4,5,6,7]
    r=evaluation([[(3000.,0.)]],10,4,42)
    assert r['outcomes'].tolist()==['passed']*4 and r['days'].tolist()==[1]*4
    chain=evaluation([[(3000.,0.)]],10,4,44,chain=True)
    assert chain['days'].tolist()==[2]*4 # Activation is one additional weekday.


def test_fixed_training_assumptions_and_pricing_validation():
    assert resolved_settings({})['BLOCK_DAYS']=='5'
    assert resolved_settings(dict(EVAL_PRICE='109',ACTIVATION_FEE='0'))['EVAL_PRICE']=='109'
    for change in [dict(BLOCK_DAYS='3'),dict(MAX_TOTAL_NQ='1.55'),dict(NET_OPPOSITE=True),dict(DAILY_LOSS_LIMIT='off')]:
        with pytest.raises(ValueError):resolved_settings(change)


def test_year_totals_sum_rounded_quarters_instead_of_rerounding_year():
    grid=pd.bdate_range('2021-01-01','2021-12-31')
    # Inactivity closes an empty account every 21 sessions. Each next one waits
    # 20 sessions; quarter-level cash rounding remains visible in the output.
    result=replay_history(grid,[[] for _ in grid],9,19.519,272.7371663244353,20)
    assert result['years'][0]['costs']==sum(q['costs'] for q in result['quarters'])
    assert result['totals']['net']==-result['totals']['costs']


def test_engine_does_not_call_external_process_or_read_result_files(monkeypatch):
    import builtins,subprocess
    def reject(*a,**kw):raise AssertionError('Calculation accessed external process/file')
    monkeypatch.setattr(builtins,'open',reject);monkeypatch.setattr(subprocess,'Popen',reject)
    a=funded([[(800.,0.)]],10,3,42,horizon=40)
    assert all(x.outcome=='paid_all' and sum(v for _,v in x.payouts)==13000. for x in a)


def test_neutral_run_compaction_preserves_draws_accounts_and_exact_floor_checks():
    from dataclasses import asdict
    from alphaquest.prop.native_engine import compact_neutral_runs
    days=[[(0.,0.)]*50+[(800.,0.)]+[(0.,0.)]*30,
          [(0.,0.)]*40+[(-1200.,1200.)]+[(0.,0.)]*20,[]]
    compact=compact_neutral_runs(days)
    for seed in (42,43):
        left=evaluation(days,9,40,seed);right=evaluation(compact,9,40,seed)
        assert all(np.array_equal(left[key],right[key]) for key in left)
        left=funded(days,9,40,seed,horizon=100);right=funded(compact,9,40,seed,horizon=100)
        assert [asdict(a) for a in left]==[asdict(a) for a in right]
    # A neutral trade still performs the first boundary check at an exact floor.
    for trades in ([(0.,0.)]*50,compact_neutral_runs([[(0.,0.)]*50])[0]):
        a=FundedAccount(equity=100.,high=2100.,locked=True)
        a.advance(trades,1)
        assert a.outcome=='blown'

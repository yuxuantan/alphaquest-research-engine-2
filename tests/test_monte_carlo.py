"""Fast, independently known Monte Carlo and cancellation boundaries."""
from uuid import uuid4

import numpy as np

from alphaquest.campaign_monte_carlo import POLICY, assess, stationary_indices, summarize


def test_stationary_bootstrap_and_independent_constant_and_loss_oracles():
    # Every constant-P&L resample must have the same analytically known result.
    daily=[dict(net_pnl='2.50') for _ in range(100)]
    result,paths=assess(daily,100)
    assert result['qualifies'] and len(paths)==10000
    assert result['observed']==dict(days=100,closed_trades=100,net_profit=250,daily_close_max_drawdown=0)
    assert all(p['net_profit']==250 and p['max_drawdown']==0 for p in paths)
    assert all(s['profitable_paths_pct']==100 and s['max_drawdown_p95']==0 for s in result['scenarios'])
    assert all(s['net_profit_mean']==250 and s['net_profit_median']==250 and s['max_drawdown_median']==0 for s in result['scenarios'])
    assert all(s['historical_drawdown_percentile_pct']==50 and s['max_drawdown_p95_over_observed'] is None for s in result['scenarios'])
    assert assess(daily,99)[0]['qualifies'] is False
    losses,_=assess([dict(net_pnl='-1') for _ in range(100)],100)
    assert not losses['qualifies']
    assert all(s['net_profit_p05']==-100 and s['max_drawdown_p95']==100 for s in losses['scenarios'])
    # Positive history does not guarantee profitable bootstraps (unlike a shuffle).
    concentrated,_=assess([dict(net_pnl='-1') for _ in range(99)]+[dict(net_pnl='200')],100)
    assert concentrated['observed']['net_profit']==101 and not concentrated['qualifies']
    assert all(s['net_profit_p05']<0 for s in concentrated['scenarios'])
    # The former 2x drawdown rejection now remains a diagnostic only.
    fragile,_=assess([dict(net_pnl=str(x)) for x in [10,-1]*50],100)
    assert fragile['qualifies']
    assert fragile['observed']['daily_close_max_drawdown']==1
    assert fragile['scenarios'][0]['checks'][0]['passed']
    assert fragile['scenarios'][0]['max_drawdown_p95_over_observed']==3
    assert all(len(s['checks'])==1 for s in fragile['scenarios'])
    # Long blocks preserve adjacency; fixed seed generates the same schedule.
    a=stationary_indices(np.random.default_rng(123),30,100,20)
    b=stationary_indices(np.random.default_rng(123),30,100,20)
    assert np.array_equal(a,b)
    assert np.mean(a[:,1:]==(a[:,:-1]+1)%100)>.90
    assert not np.all(np.sort(a,axis=1)==np.arange(100))


def test_diagnostic_percentile_ties_and_unacceptable_mean_do_not_change_tail_gate():
    observed=dict(daily_close_max_drawdown=10)
    # Original DD: 25% strictly below, 50% tied => midpoint percentile 50%.
    dd=[5]*1250+[10]*2500+[20]*1250
    result=summarize(observed,[1]*5000,dd,5)
    assert result['historical_drawdown_percentile_pct']==50
    assert result['max_drawdown_median']==10 and result['max_drawdown_p95']==20
    # A large positive mean/median cannot override a failing lower tail.
    result=summarize(observed,[-100]*500+[1000]*4500,dd,5)
    assert result['net_profit_mean']==890 and result['net_profit_median']==1000
    assert result['net_profit_p05']==-100 and not result['qualifies']


def test_cancelled_analysis_does_not_publish_or_calculate(tmp_path,monkeypatch):
    from alphaquest.prop.store import AnalysisStore
    from alphaquest import campaign_monte_carlo as mc
    store=AnalysisStore(tmp_path);id=uuid4().hex
    try:
        with store.connect() as db:
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(id,'synthetic','synthetic','2026-11-11','queued','Queued',None))
            db.execute('INSERT INTO phase_analysis_control VALUES (?,1)',(id,))
        monkeypatch.setattr(mc,'assess',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Cancelled before calculation')))
        mc.run(store,id,{})
        assert store.get(id)['status']=='cancelled'
        assert not (store.root/id).exists()
    finally:store.close()



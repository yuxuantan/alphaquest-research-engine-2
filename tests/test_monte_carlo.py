"""Fast, independently known Monte Carlo and cancellation boundaries."""
from uuid import uuid4

import numpy as np

from alphaquest.campaign_monte_carlo import assess, stationary_indices


def test_stationary_bootstrap_and_independent_constant_and_loss_oracles():
    # Every constant-P&L resample must have the same analytically known result.
    daily=[dict(net_pnl='2.50') for _ in range(100)]
    result,paths=assess(daily,100)
    assert result['qualifies'] and len(paths)==10000
    assert result['observed']==dict(days=100,closed_trades=100,net_profit=250,daily_close_max_drawdown=0)
    assert all(p['net_profit']==250 and p['max_drawdown']==0 for p in paths)
    assert all(s['profitable_paths_pct']==100 and s['max_drawdown_p95']==0 for s in result['scenarios'])
    assert assess(daily,99)[0]['qualifies'] is False
    losses,_=assess([dict(net_pnl='-1') for _ in range(100)],100)
    assert not losses['qualifies']
    assert all(s['net_profit_p05']==-100 and s['max_drawdown_p95']==100 for s in losses['scenarios'])
    # Positive history does not guarantee profitable bootstraps (unlike a shuffle).
    concentrated,_=assess([dict(net_pnl='-1') for _ in range(99)]+[dict(net_pnl='200')],100)
    assert concentrated['observed']['net_profit']==101 and not concentrated['qualifies']
    assert all(s['net_profit_p05']<0 for s in concentrated['scenarios'])
    # A profitable candidate can fail clustering risk independently of profit.
    fragile,_=assess([dict(net_pnl=str(x)) for x in [10,-1]*50],100)
    assert not fragile['qualifies']
    assert fragile['observed']['daily_close_max_drawdown']==1
    assert fragile['scenarios'][0]['checks'][0]['passed']
    assert not fragile['scenarios'][0]['checks'][1]['passed']
    assert fragile['scenarios'][1]['checks'][1]['passed'] # equality at 2x passes
    # Long blocks preserve adjacency; fixed seed generates the same schedule.
    a=stationary_indices(np.random.default_rng(123),30,100,20)
    b=stationary_indices(np.random.default_rng(123),30,100,20)
    assert np.array_equal(a,b)
    assert np.mean(a[:,1:]==(a[:,:-1]+1)%100)>.90
    assert not np.all(np.sort(a,axis=1)==np.arange(100))


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



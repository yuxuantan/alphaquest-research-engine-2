"""Independent OOS threshold and bar-close measurement oracles."""
from decimal import Decimal as D

import pytest
from alphaquest.oos_criteria import POLICY, evaluate


def screening_oracle():
    reference=dict(total_net_pnl='1000',closed_trades=100,metrics=dict(is_annual_net_profit='100',is_mtm_max_drawdown='100',is_profitable_months_pct='65'))
    captured=dict(policy=POLICY,total_net_pnl='500',closed_trades=100,metrics=dict(oos_history_months=6,oos_full_months=6,
        oos_annual_net_profit='50',oos_mtm_max_drawdown='150',oos_profitable_months_pct='50',oos_stress_net_profit='1'))
    return captured,reference


def test_oos_thresholds_are_specific_inclusive_and_fail_closed():
    captured,reference=screening_oracle()
    assert evaluate(captured,reference)['qualifies']
    for key,value,failed in [('oos_annual_net_profit','49.9999','annual_retention'),
                             ('oos_mtm_max_drawdown','150.0001','drawdown'),
                             ('oos_profitable_months_pct','49.9999','profitable_months'),
                             ('oos_stress_net_profit','0','cost_stress'),
                             ('oos_history_months',5,'evidence')]:
        altered=dict(captured,metrics=dict(captured['metrics'],**{key:value}))
        result=evaluate(altered,reference)
        assert not result['qualifies']
        assert not next(c for c in result['checks'] if c['id']==failed)['passed']
    assert not evaluate(dict(captured,closed_trades=101),reference)['checks'][3]['passed']
    empty=evaluate(dict(captured,total_net_pnl='0',closed_trades=0),reference)
    assert empty['status']=='insufficient_evidence' and empty['profit_per_trade_retention_pct'] is None
    zero=dict(reference,metrics=dict(reference['metrics'],is_mtm_max_drawdown='0'))
    assert not evaluate(captured,zero)['checks'][4]['passed']
    assert evaluate(dict(captured,metrics=dict(captured['metrics'],oos_mtm_max_drawdown='0')),zero)['qualifies']


def test_oos_capture_uses_only_declared_oos_bar_close_marks():
    from datetime import datetime
    from types import SimpleNamespace
    from alphaquest.workflow_criteria import ScreeningCapture
    research=dict(plan=dict(is_start='2024-01-01',is_end='2025-12-31',oos_start='2026-01-01',oos_end='2026-12-31'),
                  oos_policy=POLICY,cost_stress=dict(summary=dict(total_net_pnl='1')))
    capture=ScreeningCapture(D(10000),research,'UTC',phase='oos')
    def point(date,equity):return SimpleNamespace(timestamp_utc=datetime.fromisoformat(date+'T12:00:00+00:00'),equity=D(equity))
    with pytest.raises(ValueError):capture.observe(point('2025-12-31','10000'))
    capture.observe(point('2026-01-01','10000'))
    capture.observe(point('2026-01-02','9800'))
    capture.observe(point('2026-01-03','10000'))
    for month in range(2,13):capture.observe(point(f'2026-{month:02}-01',str(10000+month*100)))
    capture.observe(point('2026-12-31','11200'))
    result=capture.finish(100,D(1200))
    assert result['metrics']['oos_mtm_max_drawdown']==200
    assert result['metrics']['oos_history_months']==12
    assert result['metrics']['oos_full_months']==12
    assert result['mtm_drawdown_duration_seconds']==2*86400
    assert 'is_mtm_max_drawdown' not in result['metrics']

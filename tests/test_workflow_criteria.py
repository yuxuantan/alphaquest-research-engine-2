"""Independent threshold, open-equity, calendar and unresolved-drawdown oracles."""
from datetime import datetime, timezone
from decimal import Decimal as D
from types import SimpleNamespace

from alphaquest.workflow_criteria import PREVIOUS_VERSION, ScreeningCapture, evaluate, policy


def capture(start='2024-01-01',end='2025-12-31',zone='UTC'):
    return ScreeningCapture(D(10000),dict(plan=dict(is_start=start,is_end=end),screening_policy=policy(),
        cost_stress=dict(run_id='stress',summary=dict(total_net_pnl='100'))),zone)


def mark(tracker,stamp,equity):
    tracker.observe(SimpleNamespace(timestamp_utc=datetime.fromisoformat(stamp).astimezone(timezone.utc),equity=D(equity)))


def test_every_bar_open_equity_monthly_attribution_and_true_observed_coverage():
    tracker=capture()
    mark(tracker,'2024-01-01T00:00:00+00:00',10000)
    mark(tracker,'2024-01-02T00:00:00+00:00',9000) # an open trade, recovered before trade close
    mark(tracker,'2024-01-03T00:00:00+00:00',10100)
    for index in range(1,24):
        year,month=2024+index//12,index%12+1
        mark(tracker,f'{year}-{month:02}-01T00:00:00+00:00',10000+(index+1)*100)
    mark(tracker,'2025-12-31T23:59:00+00:00',12400)
    result=tracker.finish(100,D(2400))
    assert result['qualifies']
    assert result['metrics']['is_mtm_max_drawdown']==1000
    assert result['metrics']['is_history_months']==24
    assert result['metrics']['is_full_months']==24
    assert result['metrics']['is_profitable_months_pct']==100
    assert result['mtm_drawdown_duration_seconds']==2*86400
    assert [row['net_pnl'] for row in result['months']]==[100]*24
    assert result['metrics']['is_annual_net_profit']==D(2400)*D('365.2425')/731


def test_source_timezone_complete_months_no_trade_months_and_unresolved_dd_to_is_end():
    tracker=capture('2024-01-15','2024-04-15','America/New_York')
    mark(tracker,'2024-01-15T10:00:00-05:00',10000)
    mark(tracker,'2024-01-31T23:59:00-05:00',10200) # Jan, though UTC date is Feb 1
    mark(tracker,'2024-02-29T23:59:00-05:00',10100)
    mark(tracker,'2024-04-15T10:00:00-04:00',10100) # March has no bars/trades: carry last observed mark
    result=tracker.finish(1,D(100))
    assert result['metrics']['is_full_months']==2
    assert [(r['month'],r['net_pnl'],r['complete']) for r in result['months']]==[
        ('2024-01',D(200),False),('2024-02',D(-100),True),('2024-03',D(0),True),('2024-04',D(0),False)]
    assert result['metrics']['is_profitable_months_pct']==0
    assert result['status']=='insufficient_evidence'
    peak=datetime.fromisoformat('2024-01-31T23:59:00-05:00')
    end=datetime.fromisoformat('2024-04-16T00:00:00-04:00')
    assert result['mtm_drawdown_duration_seconds']==D(str((end-peak).total_seconds()))
    short=capture();mark(short,'2025-12-30T09:00:00+00:00',10000);mark(short,'2025-12-31T09:00:00+00:00',10100)
    assert short.finish(100,D(100))['metrics']['is_history_months']==0 # padded declaration cannot create 24 months


def test_strict_thresholds_and_inclusive_minimum_evidence():
    metrics=dict(is_history_months=24,is_annual_net_profit='100.0001',is_mtm_max_drawdown='100',
        is_annual_profit_dd_ratio='1.000001',is_profitable_months_pct='50.0001',is_full_months=24,
        is_longest_dd_pct='24.9999',is_stress_net_profit='0.0001')
    assert evaluate(metrics,100,'1',policy())['qualifies']
    weaker=dict(metrics,is_annual_net_profit='1',is_annual_profit_dd_ratio='0.01')
    assert evaluate(weaker,100,'1',policy())['qualifies']
    historical=evaluate(weaker,100,'1',policy(PREVIOUS_VERSION))
    assert not historical['qualifies'] and not next(c for c in historical['checks'] if c['id']=='annual_profit_dd')['passed']
    for key,value,reason in [('is_history_months',23,'evidence'),
                             ('is_profitable_months_pct','50','profitable_months'),('is_longest_dd_pct','25','drawdown_duration'),
                             ('is_stress_net_profit','0','cost_stress')]:
        result=evaluate(dict(metrics,**{key:value}),100,'1',policy())
        assert not result['qualifies'] and not next(c for c in result['checks'] if c['id']==reason)['passed']
    assert evaluate(metrics,99,'1',policy())['status']=='insufficient_evidence'
    assert not evaluate(metrics,100,'0',policy())['qualifies']
    assert not evaluate(dict(metrics,is_full_months=0,is_profitable_months_pct=None),100,'1',policy())['qualifies']

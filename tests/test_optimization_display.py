"""Independent weekday drawdowns and global display-unit sorting."""
import csv
from datetime import datetime

import pytest

from alphaquest.optimization_display import trading_day_duration
from test_optimization import client, optimization_body, start, wait_job
from test_backtest_api import save_fixture


def saved_equity(folder, start, end, points, cme=False):
    with (folder / 'equity.csv').open('w', newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['trade_number','exit_time_utc','equity'])
        writer.writerow([0,'',100])
        for i,(timestamp,equity) in enumerate(points,1):writer.writerow([i,timestamp,equity])
    return dict(period_start_utc=start,period_end_utc=end,
        summary=dict(initial_capital='100',trades_taken=len(points)),
        run_metadata=dict(dataset=dict(source_timezone='UTC'),
            strategy=dict(session_calendar=dict(id='cme_nq') if cme else {})))


@pytest.mark.parametrize('start,end,points,expected',[
    ('2026-01-02T10:00:00Z','2026-01-05T12:00:00Z',
     [('2026-01-02T12:00:00Z',90)],1),  # Friday to Monday, includes an idle weekday.
    ('2026-01-05T10:00:00Z','2026-01-05T16:00:00Z',
     [('2026-01-05T12:00:00Z',90),('2026-01-05T15:00:00Z',100)],0),
    ('2026-01-02T10:00:00Z','2026-01-07T12:00:00Z',
     [('2026-01-02T12:00:00Z',90),('2026-01-05T10:00:00Z',100),
      ('2026-01-06T10:00:00Z',95),('2026-01-07T10:00:00Z',100)],2),
    ('2026-01-02T10:00:00Z','2026-01-07T12:00:00Z',
     [('2026-01-05T10:00:00Z',100),('2026-01-06T10:00:00Z',90)],2), # Equal peak resets.
    ('2026-01-02T10:00:00Z','2026-01-07T12:00:00Z',[],0),
])
def test_elapsed_weekday_drawdowns_use_all_peaks_recoveries_and_period_end(tmp_path,start,end,points,expected):
    record=saved_equity(tmp_path,start,end,points)
    assert trading_day_duration(tmp_path,record)==expected


def test_cme_evening_and_next_day_share_one_session_and_invalid_equity_is_rejected(tmp_path):
    record=saved_equity(tmp_path,'2026-01-04T23:00:00Z','2026-01-05T20:00:00Z',
        [('2026-01-04T23:30:00Z',90),('2026-01-05T20:00:00Z',100)],cme=True)
    assert trading_day_duration(tmp_path,record)==0
    record['summary']['trades_taken']=3
    with pytest.raises(ValueError,match='count differs'):trading_day_duration(tmp_path,record)


def test_trading_day_sort_is_global_before_pagination_and_null_last(client,monkeypatch):
    dataset=save_fixture(client);job=wait_job(client,start(client,optimization_body(dataset['id'])))
    base='/api/backtests/batches/'+job['id']+'/results'
    before=client.get(base).json()['items'];days={row['run_id']:value for row,value in zip(before,[3,1,None])}
    def saved_duration(folder,record):
        value=days[record['id']]
        if value is None:raise ValueError('Saved equity is invalid')
        return value
    monkeypatch.setattr('alphaquest.optimization_display.trading_day_duration',saved_duration)
    for direction,expected in [('asc',[2,1,3]),('desc',[1,2,3])]:
        actual=[]
        for offset in range(3):
            row=client.get(base,params=dict(sort='max_drawdown_duration_trading_days',direction=direction,offset=offset,limit=1)).json()['items'][0]
            actual.append(row['trial'])
            assert row['display_metrics']['max_drawdown_duration_trading_days']==days[row['run_id']]
            assert row['metrics']==before[row['trial']-1]['metrics']
        assert actual==expected
    assert [r['trial'] for r in client.get(base,params=dict(sort='max_drawdown_duration_seconds')).json()['items']]==[1,2,3]

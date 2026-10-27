import json
import pytest
from test_backtest_api import client,body,save_fixture


def test_exclusive_phase_times_do_not_double_count_nested_work(monkeypatch):
    from alphaquest import performance
    now=[0.0];monkeypatch.setattr(performance,'perf_counter',lambda:now[0])
    timer=performance.Performance()
    with timer.span('report'):
        now[0]=2
        with timer.span('replay'):
            now[0]=5
        now[0]=7
    assert timer.snapshot()['phases_seconds']==dict(report=4,replay=3)
    assert timer.snapshot()['elapsed_seconds']==7


def test_phase_diagnostics_are_durable_and_do_not_change_saved_financial_record(client):
    dataset=save_fixture(client)
    record=client.post('/api/backtests',json=body(dataset['id'])).json()
    base='/api/backtests/'+record['id']
    diagnostic=client.get(base+'/performance').json()
    assert set(diagnostic['phases_seconds'])=={'source_loading','replay','report_writing','prop_analysis','publication'}
    assert all(value>=0 for value in diagnostic['phases_seconds'].values())
    assert sum(diagnostic['phases_seconds'].values())<=diagnostic['elapsed_seconds']
    assert client.get(base).json()==record
    assert client.get(base+'/exports/performance').json()==diagnostic
    (client.app.state.runs.root/record['id']/'performance.json').unlink()
    assert 'unavailable' in client.get(base+'/performance').json()
    assert client.get('/api/backtests/'+'a'*32+'/performance').status_code==404

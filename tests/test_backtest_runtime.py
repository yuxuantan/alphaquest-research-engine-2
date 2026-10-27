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


def test_standalone_compact_default_and_full_detail_have_exact_same_csv_and_summary(client):
    import gzip
    dataset=save_fixture(client)
    request=body(dataset['id'])
    compact=client.post('/api/backtests',json=request).json()
    assert compact['report_storage']['detail']=='compact'
    raw=client.get(f'/api/backtests/{compact["id"]}/exports/report').json()
    assert 'trades' not in raw and 'equity' not in raw
    full=client.post('/api/backtests/'+compact['id']+'/detailed')
    assert full.status_code==201,full.text
    detailed=full.json()
    assert detailed['report_storage']['detail']=='full'
    assert detailed['summary']==compact['summary']
    assert detailed['run_metadata']['automatic_prop_analysis']==compact['run_metadata']['automatic_prop_analysis']
    for kind in ('trades','equity'):
        assert client.get(f'/api/backtests/{compact["id"]}/exports/{kind}').content==client.get(f'/api/backtests/{detailed["id"]}/exports/{kind}').content
    archive=client.get(f'/api/backtests/{detailed["id"]}/exports/report').content
    assert 'equity' in json.loads(gzip.decompress(archive))


def test_large_replay_batches_progress_with_exact_final_counts_and_financial_outputs(tmp_path,monkeypatch):
    import sys
    from review_progress_runtime import main
    output=tmp_path/'normal-progress-run'
    monkeypatch.setattr(sys,'argv',['review_progress_runtime','--output',str(output),'--bars','2501'])
    main()
    result=json.loads((output/'verification.json').read_text())
    assert 4<=result['replay_progress_updates']<=45
    assert result['final_progress']['bars_processed']==2501
    assert result['final_progress']['total_bars']==2501
    assert result['summary']['trades_taken']==0
    assert result['summary']['total_net_pnl']=='0'

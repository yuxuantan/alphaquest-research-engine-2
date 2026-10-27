"""Selected report deletion, independent saved products and failure recovery."""
import json
import sqlite3
from pathlib import Path
from hashlib import sha256

import pytest

from test_backtest_api import client,body,save_fixture
from test_optimization import optimization_body,start,wait_job


def new_run(client,dataset=None):
    dataset=dataset or save_fixture(client)
    result=client.post('/api/backtests',json=body(dataset['id']))
    assert result.status_code==201,result.text
    return dataset,result.json()


def files(folder):
    return {str(p.relative_to(folder)):sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}


def test_delete_only_selected_report_and_indexed_rows(client):
    dataset,selected=new_run(client)
    _,other=new_run(client,dataset)
    runs=client.app.state.runs
    original=files(runs.root/other['id'])
    assert client.delete('/api/backtests/'+selected['id']).status_code==204
    assert not (runs.root/selected['id']).exists()
    assert files(runs.root/other['id'])==original
    assert client.get('/api/datasets/'+dataset['id']).status_code==200
    assert client.get('/api/backtests').json()['total']==1
    for suffix in ('','/trades','/equity','/chart','/exports/trades','/exports/equity','/exports/report'):
        assert client.get('/api/backtests/'+selected['id']+suffix).status_code==404
    with runs.connect() as db:
        for table in ('runs','run_trades','run_equity'):
            key='id' if table=='runs' else 'run_id'
            assert db.execute(f'SELECT COUNT(*) FROM {table} WHERE {key}=?',(selected['id'],)).fetchone()[0]==0
    assert client.delete('/api/backtests/'+selected['id']).status_code==404
    assert client.delete('/api/backtests/not-a-uuid').status_code==422


def test_completed_prop_report_remains_byte_identical_after_source_deletion(client):
    from test_prop_analysis_api import backtest
    record=backtest(client)
    id=record['run_metadata']['automatic_prop_analysis']['id']
    base='/api/prop-analyses/'+id
    original=client.get(base+'/downloads/report.json').content
    assert client.get(base).json()['status']=='complete'
    assert client.delete('/api/backtests/'+record['id']).status_code==204
    assert client.get(base).json()['status']=='complete'
    assert client.get(base+'/downloads/report.json').content==original
    assert json.loads(original)['source']['backtest']==record


def test_active_prop_analysis_and_full_detail_prevent_deletion(client):
    _,record=new_run(client);id=record['id'];runs=client.app.state.runs
    original=files(runs.root/id)
    runs.claim_detail(id)
    try:
        response=client.delete('/api/backtests/'+id)
        assert response.status_code==409 and 'Full detail' in response.json()['detail']
    finally:runs.release_detail(id)
    analyses=client.app.state.prop_analyses
    for status in ('queued','running'):
        with analyses.connect() as db:
            db.execute('INSERT OR REPLACE INTO analyses VALUES (?,?,?,?,?,?,?)',('a'*32,'pending',id,'2026-10-27',status,'Controlled pending source use',None))
        response=client.delete('/api/backtests/'+id)
        assert response.status_code==409 and 'prop analysis' in response.json()['detail']
    with analyses.connect() as db:db.execute("UPDATE analyses SET status='error' WHERE id=?",('a'*32,))
    assert files(runs.root/id)==original
    assert client.delete('/api/backtests/'+id).status_code==204
    with pytest.raises(ValueError,match='deleted'):runs.claim_detail(id)


def test_failed_catalogue_delete_restores_files_and_rows(client):
    _,record=new_run(client);runs=client.app.state.runs;id=record['id']
    original=files(runs.root/id)
    with runs.connect() as db:
        db.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON runs BEGIN SELECT RAISE(ABORT,'Controlled delete failure'); END")
    response=client.delete('/api/backtests/'+id)
    assert response.status_code==500 and 'No deletion was committed' in response.json()['detail']
    assert client.get('/api/backtests/'+id).json()==record
    assert files(runs.root/id)==original
    assert not (runs.root/('.deleted-'+id)).exists()
    with runs.connect() as db:db.execute('DROP TRIGGER reject_delete')
    assert client.delete('/api/backtests/'+id).status_code==204


def test_failed_file_rename_preserves_report(client,monkeypatch):
    _,record=new_run(client);runs=client.app.state.runs;id=record['id']
    original=files(runs.root/id);rename=Path.rename
    def reject(path,target):
        if path==runs.root/id:raise PermissionError('Controlled rename failure')
        return rename(path,target)
    monkeypatch.setattr(Path,'rename',reject)
    response=client.delete('/api/backtests/'+id)
    assert response.status_code==500
    assert client.get('/api/backtests/'+id).json()==record
    assert files(runs.root/id)==original


def test_file_cleanup_failure_can_be_retried_without_deleting_another_run(client,monkeypatch):
    from alphaquest import backtest_runs
    dataset,record=new_run(client);_,other=new_run(client,dataset)
    runs=client.app.state.runs;id=record['id'];original=files(runs.root/other['id'])
    cleanup=backtest_runs.shutil.rmtree;attempts=[]
    def fail_once(path,*args,**kwargs):
        if path==runs.root/('.deleted-'+id) and not attempts:
            attempts.append(path);raise PermissionError('Controlled cleanup failure')
        return cleanup(path,*args,**kwargs)
    monkeypatch.setattr(backtest_runs.shutil,'rmtree',fail_once)
    failed=client.delete('/api/backtests/'+id)
    assert failed.status_code==500 and 'Retry Delete' in failed.json()['detail']
    assert client.get('/api/backtests/'+id).status_code==404
    assert (runs.root/('.deleted-'+id)).exists()
    assert client.delete('/api/backtests/'+id).status_code==204
    assert not (runs.root/('.deleted-'+id)).exists()
    assert files(runs.root/other['id'])==original


def test_delete_optimization_backtest_keeps_metrics_and_invalidates_only_its_reuse(client):
    dataset=save_fixture(client)
    request=optimization_body(dataset['id'])
    request.update(workers=1,reuse_results=True)
    request['parameter_ranges']=dict(green_bar_count=dict(start=1,end=2,step=1),hold_minutes=dict(start=1,end=1,step=0),contracts=dict(start=1,end=1,step=0))
    job=wait_job(client,start(client,request));assert job['status']=='complete',job
    base='/api/optimizations/'+job['id']
    rows=client.get(base+'/results').json()['items']
    runs=client.app.state.runs
    with runs.connect() as db:original=list(db.execute('SELECT * FROM optimization_trials'))
    assert client.delete('/api/backtests/'+rows[0]['run_id']).status_code==204
    after=client.get(base+'/results?sort=total_net_pnl&direction=desc').json()['items']
    assert next(row for row in after if row['trial']==1)['backtest_deleted'] is True
    assert {r['trial']:r['metrics'] for r in after}=={r['trial']:r['metrics'] for r in rows}
    assert client.get(base+'/exports/results').status_code==200
    with runs.connect() as db:assert list(db.execute('SELECT * FROM optimization_trials'))==original
    rerun=wait_job(client,start(client,request));assert rerun['status']=='complete',rerun
    assert rerun['reused_trials']==1
    assert client.get('/api/backtests').json()['total']==2


def test_analysis_submission_and_source_deletion_are_coordinated(client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from alphaquest.prop import native_analysis,store
    from test_prop_analysis_api import backtest
    record=backtest(client);id=record['id']
    prepared=Event();allow_submission=Event();release_worker=Event()
    prepare=native_analysis.prepare
    def paused_prepare(*args,**kwargs):
        result=prepare(*args,**kwargs);prepared.set()
        assert allow_submission.wait(10)
        return result
    def controlled_worker(*args,**kwargs):
        assert release_worker.wait(10)
        raise RuntimeError('Controlled worker stopped after source deletion rejection')
    monkeypatch.setattr(native_analysis,'prepare',paused_prepare)
    monkeypatch.setattr(store,'run_analysis',controlled_worker)
    request=dict(source_backtest_id=id,trade_file='',settings=dict(ACTIVATION_FEE='130'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        submitted=pool.submit(client.post,'/api/prop-analyses',json=request)
        try:
            assert prepared.wait(10)
            deleted=pool.submit(client.delete,'/api/backtests/'+id)
            allow_submission.set()
            assert submitted.result(timeout=10).status_code==202
            assert deleted.result(timeout=10).status_code==409
            assert client.get('/api/backtests/'+id).json()==record
        finally:
            allow_submission.set();release_worker.set()

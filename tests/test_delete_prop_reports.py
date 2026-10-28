"""Selected prop report deletion, concurrency guards, rollback and preserved inputs."""
from pathlib import Path
from hashlib import sha256
import json
import pytest
from test_prop_analysis_api import portal as client,backtest


def capture(path):return {str(p.relative_to(path)):sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}


def test_delete_prop_keeps_source_and_other_report_and_clears_calculation_cache(client):
    first=backtest(client);second=backtest(client,quantity=3)
    a=first['run_metadata']['automatic_prop_analysis']['id'];b=second['run_metadata']['automatic_prop_analysis']['id']
    store=client.app.state.prop_analyses;before=capture(store.root/b)
    with store.connect() as db:db.execute('INSERT OR REPLACE INTO calculation_reuse VALUES (?,?,?,?)',('selected-test','engine',a,'sha'))
    result=client.delete('/api/prop-analyses/'+a);assert result.status_code==204,result.text
    assert client.get('/api/prop-analyses/'+a).status_code==404
    assert client.get('/api/prop-analyses/'+a+'/downloads/report.json').status_code==404
    assert not (store.root/a).exists() and capture(store.root/b)==before
    assert client.get('/api/backtests/'+first['id']).json()==first
    assert client.get('/api/datasets/'+first['run_metadata']['dataset']['id']).status_code==200
    with store.connect() as db:
        assert not db.execute('SELECT id FROM analysis_report_checks WHERE id=?',(a,)).fetchall()
        assert not db.execute('SELECT id FROM calculation_reuse WHERE id=?',(a,)).fetchall()
    assert client.delete('/api/prop-analyses/'+a).status_code==404
    assert client.delete('/api/prop-analyses/not-valid').status_code==422


@pytest.mark.parametrize('status',['queued','running'])
def test_active_prop_report_deletion_is_blocked(client,status):
    record=backtest(client);id=record['run_metadata']['automatic_prop_analysis']['id'];store=client.app.state.prop_analyses
    before=capture(store.root/id)
    with store.connect() as db:db.execute('UPDATE analyses SET status=? WHERE id=?',(status,id))
    result=client.delete('/api/prop-analyses/'+id)
    assert result.status_code==409 and 'queued or running' in result.text
    assert capture(store.root/id)==before
    with store.connect() as db:db.execute("UPDATE analyses SET status='complete' WHERE id=?",(id,))


def test_prop_delete_sql_failure_restores_rows_and_download_bytes(client):
    record=backtest(client);id=record['run_metadata']['automatic_prop_analysis']['id'];store=client.app.state.prop_analyses
    before=capture(store.root/id)
    with store.connect() as db:db.execute("CREATE TRIGGER reject_prop_delete BEFORE DELETE ON analyses BEGIN SELECT RAISE(ABORT,'Controlled delete failure'); END")
    result=client.delete('/api/prop-analyses/'+id)
    assert result.status_code==500 and 'No deletion was committed' in result.text
    assert capture(store.root/id)==before and store.get(id)['status']=='complete'
    assert not (store.root/('.deleted-'+id)).exists()
    with store.connect() as db:db.execute('DROP TRIGGER reject_prop_delete')
    assert client.delete('/api/prop-analyses/'+id).status_code==204


def test_prop_delete_cleanup_failure_is_retryable(client,monkeypatch):
    import shutil
    record=backtest(client);id=record['run_metadata']['automatic_prop_analysis']['id'];store=client.app.state.prop_analyses
    cleanup=shutil.rmtree;attempts=[]
    def once(path,*a,**kw):
        if path==store.root/('.deleted-'+id) and not attempts:attempts.append(path);raise PermissionError('Controlled cleanup failure')
        return cleanup(path,*a,**kw)
    monkeypatch.setattr(shutil,'rmtree',once)
    result=client.delete('/api/prop-analyses/'+id)
    assert result.status_code==500 and 'Retry Delete' in result.text
    assert store.get(id) is None and (store.root/('.deleted-'+id)).exists()
    assert client.delete('/api/prop-analyses/'+id).status_code==204
    assert not (store.root/('.deleted-'+id)).exists()


def test_symbolic_link_report_directory_is_not_followed(client,tmp_path):
    record=backtest(client);id=record['run_metadata']['automatic_prop_analysis']['id'];store=client.app.state.prop_analyses
    source=store.root/id;kept=tmp_path/'kept-report';before=capture(source)
    source.rename(kept);source.symlink_to(kept,target_is_directory=True)
    try:
        result=client.delete('/api/prop-analyses/'+id)
        assert result.status_code==500 and 'symbolic-link' in result.text
        assert capture(kept)==before and store.get(id)['status']=='complete'
    finally:source.unlink();kept.rename(source)


def test_optimization_keeps_saved_metrics_and_marks_deleted_prop_link(client):
    from test_optimization import optimization_body,start,wait_job
    record=backtest(client);request=optimization_body(record['run_metadata']['dataset']['id'])
    request['workers']=1
    job=wait_job(client,start(client,request));assert job['status']=='complete',job
    base='/api/backtests/batches/'+job['id']
    rows=client.get(base+'/results').json()['items'];selected=rows[0]
    before={row['trial']:row['metrics'] for row in rows}
    assert client.delete('/api/prop-analyses/'+selected['prop_analysis']['id']).status_code==204
    after=client.get(base+'/results').json()['items']
    assert {row['trial']:row['metrics'] for row in after}==before
    assert next(row for row in after if row['trial']==selected['trial'])['prop_report_deleted']
    assert client.get('/api/backtests/'+selected['run_id']).status_code==200

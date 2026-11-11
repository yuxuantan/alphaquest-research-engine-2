"""Queued cancellation cannot start work or alter other saved activities."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier,Event
from uuid import uuid4

import pytest
from research_fixtures import ResearchClient
from alphaquest.app import create_app
from alphaquest.strategies import consecutive_green_hold as sample
from test_optimization import client,optimization_body,start,wait_job
from test_backtest_api import save_fixture


def files(root):
    return {str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_cancel_queued_keeps_other_jobs_and_survives_restart(client,monkeypatch,tmp_path):
    dataset=save_fixture(client);request=optimization_body(dataset['id'])|dict(automatic_prop=False)
    entered,release=Event(),Event();original=sample.ConsecutiveGreenHold.on_bar
    def pause(self,bar,position):
        if not release.is_set():
            entered.set();assert release.wait(30)
        return original(self,bar,position)
    monkeypatch.setattr(sample.ConsecutiveGreenHold,'on_bar',pause)
    first=start(client,request)
    try:
        assert entered.wait(10)
        cancelled=start(client,request);last=start(client,request)
        with pytest.raises(ValueError, match='Only queued'):
            client.app.state.optimizations.cancel_queued(first)
        result=client.post(f'/api/backtests/batches/{cancelled}/cancel')
        assert result.status_code==200,result.text
        saved=result.json();assert saved['status']==saved['stage']=='cancelled' and saved['completed_trials']==0
        assert 'started_at_utc' not in saved and saved['cancelled_at_utc']==saved['finished_at_utc']
        assert client.post(f'/api/optimizations/{cancelled}/cancel').json()==saved
        assert client.get(f'/api/optimizations/{last}').json()['status']=='queued'
        assert client.post(f'/api/optimizations/{uuid4().hex}/cancel').status_code==404
        assert client.post('/api/optimizations/not-a-uuid/cancel').status_code==422
    finally:release.set()
    for id in (first,last):
        assert wait_job(client,id)['status']=='complete'
        rows=client.get(f'/api/optimizations/{id}/results').json()['items']
        assert [float(row['metrics']['total_net_pnl']) for row in rows]==[13,26,39]
        before=client.get(f'/api/optimizations/{id}').json()
        assert client.post(f'/api/optimizations/{id}/cancel').status_code==409
        assert client.get(f'/api/optimizations/{id}').json()==before
    assert client.get(f'/api/optimizations/{cancelled}').json()==saved
    assert client.get(f'/api/optimizations/{cancelled}/results').json()['items']==[]
    assert client.post(f'/api/optimizations/{cancelled}/resume').status_code==409
    assert client.get('/api/backtests').json()['total']==6
    with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as restarted:
        assert restarted.get(f'/api/optimizations/{cancelled}').json()==saved


def test_cancelling_queued_resume_keeps_prior_reports_and_late_callback_is_noop(client,monkeypatch):
    dataset=save_fixture(client);original=sample.ConsecutiveGreenHold.on_bar
    def fail(self,bar,position):
        if self.parameters.contracts==2:raise RuntimeError('Synthetic failed trial')
        return original(self,bar,position)
    monkeypatch.setattr(sample.ConsecutiveGreenHold,'on_bar',fail)
    id=start(client,optimization_body(dataset['id']))
    assert wait_job(client,id)['completed_trials']==1
    monkeypatch.setattr(sample.ConsecutiveGreenHold,'on_bar',original)
    store=client.app.state.optimizations;before=files(store.runs.root);prop_before=files(store.prop_analyses.root)
    rows=client.get(f'/api/optimizations/{id}/results').json()['items']
    release=Event();blocker=store.executor.submit(lambda:release.wait(30))
    try:
        response=client.post(f'/api/optimizations/{id}/resume');assert response.status_code==202,response.text
        response=client.post(f'/api/optimizations/{id}/cancel');assert response.status_code==200,response.text
        cancelled=response.json();assert cancelled['completed_trials']==1
        assert client.get(f'/api/optimizations/{id}/results').json()['items']==rows
        assert files(store.runs.root)==before and files(store.prop_analyses.root)==prop_before
        def forbidden(*args,**kwargs):pytest.fail('Cancelled callback attempted execution or runtime admission')
        monkeypatch.setattr(store,'_run',forbidden)
        monkeypatch.setattr(store.prop_analyses.runtime,'optimization',forbidden)
        store.run(cancelled,None,None,None,None)
    finally:release.set();blocker.result(timeout=10)
    store.executor.submit(lambda:None).result(timeout=10)
    assert client.get(f'/api/optimizations/{id}').json()==cancelled
    assert files(store.runs.root)==before and files(store.prop_analyses.root)==prop_before
    # Deleting the inactive row is separate. Its already queued callback remains harmless.
    assert client.delete(f'/api/optimizations/{id}').status_code==200
    store.run(cancelled,None,None,None,None)


@pytest.mark.parametrize('status',['failed','interrupted','deleting'])
def test_nonqueued_cancel_rejects_without_mutation(client,status):
    dataset=save_fixture(client);store=client.app.state.optimizations
    release=Event();blocker=store.executor.submit(lambda:release.wait(30))
    try:
        id=start(client,optimization_body(dataset['id'])|dict(automatic_prop=False))
        before=store.update(id,status=status,stage=status)
        assert client.post(f'/api/optimizations/{id}/cancel').status_code==409
        assert store.get(id)==before
    finally:release.set();blocker.result(timeout=10)
    store.executor.submit(lambda:None).result(timeout=10)
    assert store.get(id)==before


def test_worker_claim_and_cancellation_have_exactly_one_winner(client):
    dataset=save_fixture(client);store=client.app.state.optimizations
    release=Event();blocker=store.executor.submit(lambda:release.wait(30))
    try:
        id=start(client,optimization_body(dataset['id'])|dict(automatic_prop=False))
        gate=Barrier(2)
        def claim():gate.wait();return store._claim_queued(id)
        def cancel():
            gate.wait()
            try:return store.cancel_queued(id)
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as threads:
            a=threads.submit(claim);b=threads.submit(cancel);claimed,cancelled=a.result(),b.result()
        assert (claimed is None)!=(cancelled is None)
        assert store.get(id)['status']==('running' if claimed else 'cancelled')
    finally:release.set();blocker.result(timeout=10)
    store.executor.submit(lambda:None).result(timeout=10)

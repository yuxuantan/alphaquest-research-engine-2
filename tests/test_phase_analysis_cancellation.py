"""A requested worker stop cannot publish a partial phase candidate population."""
from datetime import datetime,timezone
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alphaquest.prop.store import AnalysisStore


def test_cooperative_stop_retains_cancelled_job_and_no_report(tmp_path,monkeypatch):
    entered,release=Event(),Event()
    observed=[]
    def optimize(*args,checkpoint,**kwargs):
        observed.append('first_candidate_started');entered.set()
        assert release.wait(5)
        checkpoint()
        pytest.fail('Cancelled population continued to a partial result')
    module=SimpleNamespace(optimize_evaluation=optimize,
        write_report=lambda *args:pytest.fail('Cancelled search reached publication'))
    monkeypatch.setattr('alphaquest.prop.phase_dispatch.module_for_mode',lambda mode:module)
    store=AnalysisStore(tmp_path);id=uuid4().hex
    try:
        with store.connect() as db:
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',
                (id,'immutable-request','source',datetime.now(timezone.utc).isoformat(),'queued','Queued',None))
            db.execute('INSERT INTO phase_analysis_control(analysis_id) VALUES (?)',(id,))
        search=SimpleNamespace(mode='evaluation_optimization',native_execution=object())
        future=store.worker.submit(store._run_phase,None,id,search,[])
        assert entered.wait(5)
        stopped=store.cancel_phase(id)
        assert stopped['status']=='running' and 'Stop requested' in stopped['progress']
        release.set();future.result(timeout=5)
        result=store.get(id)
        assert result['status']=='cancelled' and 'no partial result' in result['error']
        assert not (store.root/id).exists()
        assert observed==['first_candidate_started']
        with pytest.raises(ValueError,match='Only queued or running'):store.cancel_phase(id)
    finally:
        release.set();store.close()
    reopened=AnalysisStore(tmp_path)
    try:
        assert reopened.get(id)==result
        with reopened.connect() as db:
            assert db.execute('SELECT stop_requested FROM phase_analysis_control WHERE analysis_id=?',(id,)).fetchone()==(1,)
    finally:reopened.close()

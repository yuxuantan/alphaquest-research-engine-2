"""Cancellation, retry and immutable request identity without numerical stubs as evidence."""
from copy import deepcopy
from pathlib import Path
from threading import Event
import time
from types import SimpleNamespace

import pytest

from alphaquest.prop.frozen_pairs import PairComparisonRequest
from alphaquest.prop.store import AnalysisStore
from alphaquest.research import ResearchConflict
from test_frozen_pair import input_request


def setup(analyses,monkeypatch):
    request=PairComparisonRequest.model_validate(input_request())
    policy=dict(source=dict(id='d'*32),configuration=dict(source=dict(source_backtest_id='a'*32)),package={})
    checked=dict(pairs=[dict(id='Predeclared pair',policies=dict(evaluation=deepcopy(policy),funded=deepcopy(policy)),binding=dict(engine_identity='test identity'))])
    monkeypatch.setattr('alphaquest.prop.phase_lifecycle.check_frozen_pairs',lambda *args:deepcopy(checked))
    runs=SimpleNamespace(get=lambda id:None)
    return request,checked,runs


def wait(analyses,id):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        record=analyses.get(id)
        if record['status'] not in ('queued','running'):return record
        time.sleep(.01)
    pytest.fail('Local comparison worker did not reach its checkpoint.')


def test_accepted_cancellation_retains_binding_and_retries_same_declaration(tmp_path,monkeypatch):
    analyses=AnalysisStore(tmp_path);entered=Event();release=Event()
    try:
        request,checked,runs=setup(analyses,monkeypatch)
        def stopped(*args,checkpoint,**kwargs):
            entered.set();assert release.wait(5);checkpoint()
            raise ValueError('No financial calculation is invoked by this control-path test.')
        monkeypatch.setattr('alphaquest.prop.phase_lifecycle.run_frozen_pairs',stopped)
        record=analyses.submit_pairs(None,runs,None,request);id=record['id']
        assert entered.wait(5)
        assert analyses.submit_pairs(None,runs,None,request)['id']==id
        analyses.cancel_phase(id);release.set()
        assert wait(analyses,id)['status']=='cancelled'
        assert not (analyses.root/id).exists()
        assert {'a'*32,'d'*32}<=analyses.active_sources()
        changed=request.model_copy(update=dict(continuation='invalid'))
        with pytest.raises(ResearchConflict,match='another declaration'):
            analyses.submit_pairs(None,runs,None,changed)
        # An exact retry resets the accepted cancellation and invokes the worker.
        retry=analyses.submit_pairs(None,runs,None,request);assert retry['id']==id
        assert wait(analyses,id)['status']=='error'
        with analyses.connect() as db:
            assert db.execute('SELECT stop_requested FROM phase_analysis_control WHERE analysis_id=?',(id,)).fetchone()==(0,)
        checked['pairs'][0]['binding']['engine_identity']='new identity'
        with pytest.raises(ResearchConflict,match='implementation changed'):
            analyses.submit_pairs(None,runs,None,request)
    finally:
        release.set();analyses.close()


def test_deleted_comparison_preserves_request_tombstone_but_releases_source_pins(tmp_path,monkeypatch):
    analyses=AnalysisStore(tmp_path)
    try:
        request,checked,runs=setup(analyses,monkeypatch)
        def failed(*args,**kwargs):raise ValueError('Intentional pre-calculation failure')
        monkeypatch.setattr('alphaquest.prop.phase_lifecycle.run_frozen_pairs',failed)
        id=analyses.submit_pairs(None,runs,None,request)['id']
        assert wait(analyses,id)['status']=='error'
        assert 'd'*32 in analyses.active_sources()
        assert analyses.delete(id)
        assert 'd'*32 not in analyses.active_sources()
        with pytest.raises(ResearchConflict,match='deleted'):
            analyses.submit_pairs(None,runs,None,request)
    finally:analyses.close()


def test_accepted_stop_during_report_sealing_cannot_publish_partial_comparison(tmp_path,monkeypatch):
    analyses=AnalysisStore(tmp_path)
    try:
        request,checked,runs=setup(analyses,monkeypatch)
        # This isolates publication; numerical/cash expectations use the actual
        # controllers in test_frozen_pair and the normal API product journey.
        monkeypatch.setattr('alphaquest.prop.phase_lifecycle.run_frozen_pairs',lambda *args,**kwargs:
            dict(pairs=[dict(id='Predeclared pair',evaluation=None,funded=None,pair_binding={},
                continuation_binding=None,cash=dict(cash_ledger=[]))]))
        from alphaquest.prop.store import seal_report
        def cancel_while_sealing(staged,result,id,created):
            seal_report(staged,result,id,created)
            assert analyses.cancel_phase(id)['status']=='running'
        monkeypatch.setattr('alphaquest.prop.store.seal_report',cancel_while_sealing)
        id=analyses.submit_pairs(None,runs,None,request)['id']
        assert wait(analyses,id)['status']=='cancelled'
        assert not (analyses.root/id).exists()
        with analyses.connect() as db:
            assert db.execute('SELECT 1 FROM analysis_report_checks WHERE id=?',(id,)).fetchone() is None
    finally:analyses.close()

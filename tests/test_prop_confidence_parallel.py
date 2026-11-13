"""Exact serial-reference parity and bounded live progress for historical refits."""
import json
from hashlib import sha256
from pathlib import Path
import time

import numpy as np
import pytest

from alphaquest.prop.parallel import Runtime,CAPACITY
from alphaquest.prop.oos_qualification import RULES,historical_ratios,_book_classes,_means,definitions
from alphaquest.prop.native_engine import sampled_days
from test_prop_oos_qualification import fixed_search


def serial_reference(days,other,c,search,count):
    """Independent copy of the preceding sequential seed/refit contract."""
    rows=[];precision=True;keys=[set(),set()]
    for index in range(count):
        trace=[];values=[]
        for role,book in enumerate((days,other)):
            seed=int(np.random.SeedSequence([RULES['history_seed'],role,index]).generate_state(1)[0])
            stream=sampled_days(np.random.RandomState(seed),len(book),5)
            indices=np.fromiter((next(stream) for _ in book),dtype=np.int32,count=len(book))
            means,error=_means([book[int(i)] for i in indices],c,search,lambda:None)
            keys[role].add(_book_classes(book)[indices].tobytes());values.append(means)
            precision=bool(precision and error is not None and error<=.05)
            trace.append(dict(seed=seed,indices_sha256=sha256(indices.tobytes()).hexdigest(),metrics=means,relative_inner_standard_error=error))
        ratios={key:values[1][key]/values[0][key] if values[0].get(key,0)>0 and values[1].get(key) is not None else None
            for key,_,_,_ in definitions(search.mode.removesuffix('_optimization'))}
        rows.append(dict(replicate=index,is_history=trace[0],oos_history=trace[1],ratios=ratios))
    return rows,precision,[len(k) for k in keys]


@pytest.mark.skipif(CAPACITY<2,reason='Multiple CPUs required')
@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_parallel_matches_preceding_serial_owner_exactly_and_reports_workers(phase,monkeypatch,tmp_path):
    import alphaquest.prop.oos_qualification as owner
    monkeypatch.setitem(owner.RULES,'historical_replicates',24)
    search=fixed_search(phase);c=search.candidates[0]
    # Non-identical daybooks exercise real historical uncertainty, not a constant
    # fixture where every simulated history is memoized to the same answer.
    days=[[(1600.,0.)],[(900.,0.)],[(-400.,400.)],[(1200.,0.)],[]]*6
    other=[[(1200.,0.)],[(-300.,300.)],[(1700.,0.)],[],[(850.,0.)]]*6
    expected,precision,unique=serial_reference(days,other,c,search,24)
    runtime=Runtime(workers=2);updates=[]
    try:
        with runtime.activate():data=historical_ratios(days,other,c,c,search,lambda:None,updates.append)
        assert data['replicates']==expected
        assert data['inner_precision_ok']==precision
        assert data['unique_histories_evaluated']==unique
        assert data['execution']['workers_used']==2 and len(data['execution']['worker_pids'])==2
        assert runtime.occupied==0
    finally:runtime.close()
    assert updates[0]['completed']==0 and updates[-1]['completed']==updates[-1]['total']==24
    assert updates[-1]['active_workers']==0 and updates[-1]['worker_count']==2
    (tmp_path/(phase+'-parity.json')).write_text(json.dumps(dict(exact=True,replicates=24,distinct_histories=unique,
        execution=data['execution'],progress=updates),indent=2))


def cooperative_task(value):
    marker,number=value
    # Test-only worker: a short task completes first; siblings must stop before
    # the shared CPU reservation can be released.
    if number==0:time.sleep(.1);return 0
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if Path(marker).exists():return 'stopped'
        time.sleep(.01)
    raise AssertionError('Cancellation was not propagated')


@pytest.mark.skipif(CAPACITY<2,reason='Multiple CPUs required')
def test_reported_map_cancels_children_before_releasing_budget_and_reuses_pool(tmp_path):
    runtime=Runtime(workers=2);marker=tmp_path/'cancel'
    class Stop(Exception):pass
    def notify(done,*args):
        if done:raise Stop()
    try:
        with runtime.activate():
            with pytest.raises(Stop):runtime.map_reported(cooperative_task,[(str(marker),i) for i in range(3)],
                checkpoint=lambda:None,notify=notify,cancel=marker.touch)
        assert marker.exists() and runtime.occupied==0
        with runtime.activate():
            assert runtime.map_reported(abs,[-2,-3],checkpoint=lambda:None,notify=lambda *a:None,cancel=lambda:None)==[2,3]
    finally:runtime.close()


from test_research_workflow import client


def test_job_and_prop_metadata_share_lightweight_progress_without_report_reads(client,monkeypatch):
    from uuid import uuid4
    store=client.app.state.prop_analyses;id=uuid4().hex
    with store.connect() as db:db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',
        (id,'SYNTHETIC metadata only','a'*32,'2026-11-13T00:00:00Z','running','Historical confidence',None))
    details=dict(stage='historical_confidence',phase='evaluation',micros=3,completed=125,total=10000,unit='resamples',
        candidate_index=2,candidate_count=3,overall_completed=10125,overall_total=30000,worker_count=4,active_workers=4,
        elapsed_seconds=10.,eta_seconds=790.,updated_at_utc='2026-11-13T00:00:10Z')
    store._update(id,'running','Historical confidence',progress_details=details)
    # This endpoint may read catalogue metadata but must never load numerical reports.
    monkeypatch.setattr(store,'fingerprint',lambda *a:pytest.fail('Progress read opened sealed reports'))
    job=client.get('/api/jobs/prop_analysis/'+id).json()
    assert job['progress']['details']==details and job['progress']['completed']==10125 and job['progress']['total']==30000
    assert store.get(id)['progress_details']==details
    with store.connect() as db:
        store.remove_catalogue_record(db,id)
        assert db.execute('SELECT COUNT(*) FROM phase_analysis_progress').fetchone()[0]==0

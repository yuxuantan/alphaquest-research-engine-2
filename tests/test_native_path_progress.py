"""Exact path counts and ETA arithmetic, independent of account calculations."""
from alphaquest.prop.native_progress import NativeProgress, ETA_BASIS


class Clock:
    def __init__(self):self.now = 0
    def __call__(self):return self.now


def test_eta_excludes_serial_evidence_and_startup_waits_for_worker_sample_and_finishes_exactly():
    clock=Clock();updates=[]
    meter=NativeProgress(19,1,dict(stage='native_execution',phase='evaluation',micros=40),updates.append,clock=clock)
    meter.evidence(0)
    clock.now=1000;meter.evidence(1,preparing=True)
    clock.now=2000;meter.notify(0,18,4,[])
    assert updates[-1]['eta_seconds'] is None
    assert updates[-1]['completed']==1 and updates[-1]['eta_sample_paths']==0
    for number in range(1,9):
        clock.now=2010+number
        meter.received(([{'path_index':number}],2010))
        meter.notify(number,18,4,[1,2,3,4])
        if number<8:assert updates[-1]['eta_seconds'] is None
    row=updates[-1]
    # Eight actual worker paths in eight seconds; ten remain. Neither the
    # 1,000-second evidence capture nor 1,010-second startup inflates this.
    assert row['eta_seconds']==10
    assert row['elapsed_seconds']==2018 and row['worker_elapsed_seconds']==8
    assert row['completed']==9 and type(row['completed']) is int
    assert row['eta_basis']==ETA_BASIS and row['eta_status']=='ready'
    clock.now=2018.1
    meter.notify(8,18,4,[1,2,3,4]);assert updates[-1]==row  # metadata writes <= once/sec
    for number in range(9,19):
        clock.now=2010+number
        meter.received(([{'path_index':number}],2010))
        meter.notify(number,18,4,[1,2,3,4])
    assert updates[-1]['completed']==19 and updates[-1]['eta_seconds']==0
    assert updates[-1]['active_workers']==0 and updates[-1]['eta_status']=='complete'


def test_waits_for_all_workers_and_uses_actual_short_final_task_counts():
    clock=Clock();updates=[]
    meter=NativeProgress(10,1,{},updates.append,clock=clock)
    for number in range(8):meter.received(([number],100))
    clock.now=110;meter.notify(8,9,4,[1,2,3])
    assert updates[-1]['completed']==9 and updates[-1]['eta_seconds'] is None
    assert updates[-1]['active_workers']==1
    meter.received(([9],100));meter.notify(9,9,4,[1,2,3,4])
    assert updates[-1]['completed']==10 and updates[-1]['eta_seconds']==0


def test_captured_only_run_completes_without_eta_and_no_fabricated_worker_results():
    updates=[];meter=NativeProgress(1,1,{},updates.append)
    meter.evidence(1)
    assert updates[-1]['completed']==1 and updates[-1]['active_workers']==0
    assert updates[-1]['eta_seconds']==0 and updates[-1]['eta_sample_paths']==0


def test_single_worker_progress_is_per_path_even_when_no_parallel_runtime(monkeypatch,tmp_path):
    """The ordinary fallback calls on_result once per task, not after 32 paths."""
    import pickle
    from types import SimpleNamespace
    import alphaquest.prop.native_preparation as native
    monkeypatch.setattr(native,'worker_programme',lambda programme,*a,**k:SimpleNamespace(catalogue='checked'))
    monkeypatch.setattr(native,'_run_one',lambda programme,pattern,schedule,*a,**k:dict(path_index=schedule['path_index']))
    clock=Clock()
    def execute(task):
        clock.now+=2
        return [dict(path_index=task[2])],0
    monkeypatch.setattr('alphaquest.prop.native_progress.execute_path',execute)
    monkeypatch.setattr('alphaquest.prop.native_progress.NativeProgress',lambda *a:NativeProgress(*a,clock=clock))
    class Pattern:
        simulations=5;phase='funded'
        def paths(self,*a):return iter([dict(path_index=i) for i in range(5)])
    pattern=Pattern();updates=[]
    # Avoid serializing this local, test-only pattern. Production patterns remain checked.
    monkeypatch.setattr(pickle,'dumps',lambda *a,**k:b'fixture')
    result=native.run_prepared_accounts(None,pattern,dict(micros=40),capture_paths=1,
        checkpoint=lambda:None,progress=updates.append)
    assert result==[dict(path_index=i) for i in range(5)]
    assert {row['completed'] for row in updates}=={0,1,2,3,4,5}
    assert [row['completed'] for row in updates]==sorted(row['completed'] for row in updates)
    assert updates[-1]['completed']==5 and updates[-1]['active_workers']==0


def test_progress_revision_compatibility_is_exact_directed_and_rejects_calculation_changes():
    from copy import deepcopy
    from alphaquest.prop.evaluation_optimization import implementation_identity
    from alphaquest.prop.phase_dispatch import implementations_compatible
    current=implementation_identity();saved=deepcopy(current)
    saved['files']['native_preparation.py']='6777f00ea2a980c02175e5982196098684bd45cb1d5c6075e6714a0725d0dfee'
    snapshot=deepcopy(saved)
    assert implementations_compatible(saved,current)
    assert saved==snapshot
    assert not implementations_compatible(current,saved)
    for name in ('native_preparation.py','native_control.py','twin_preparation.py','evaluation_profiles.py'):
        changed=deepcopy(current);changed['files'][name]='unreviewed'
        assert not implementations_compatible(saved,changed)

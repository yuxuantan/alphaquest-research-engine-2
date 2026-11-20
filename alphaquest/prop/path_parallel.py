"""Indexed dated paths on the existing Runtime, with ordered exact reduction.

Only independent paths are dispatched. Original global indices own RNG seeds,
calendar strata and trace labels. Account controllers remain the original owners.
"""
from pathlib import Path
from tempfile import TemporaryDirectory


def available():
    from .parallel import _active,_optimizing
    runtime=_active.get()
    return runtime is not None and not _optimizing.get() and runtime.selected_workers>1


class Schedule:
    def __init__(self): self.parts=[]
    def update(self,value): self.parts.append(value)
    def hexdigest(self): return b''.join(self.parts)


def task(value):
    kind,kwargs,indices,marker=value
    from .phase_profiles import SizingTrace
    sizing=kwargs.get('sizing');trace=SizingTrace(sizing) if sizing is not None else None
    sink=Schedule()
    def checkpoint():
        if Path(marker).exists():raise RuntimeError('Account path execution stopped')
    kwargs=dict(kwargs,trace=trace,checkpoint=checkpoint,path_indices=indices,schedule_sink=sink,_parallel=False)
    if kind=='evaluation':
        from .evaluation_profiles import calendar_evaluation_paths
        rows,_=calendar_evaluation_paths(**kwargs)
    else:
        from .funded_profiles import _dated_funded_paths
        rows,_,_= _dated_funded_paths(**kwargs)
    return rows,sink.hexdigest(),trace.result() if trace else None


def run(kind,kwargs,count,trace,checkpoint,progress):
    from hashlib import sha256
    from time import monotonic
    from .parallel import map_reported
    from .saved_trade_simulation import PathProgress,enabled
    # Small chunks yield frequent completed-path updates and bounded stop delay.
    chunks=[tuple(range(i,min(i+4,count))) for i in range(0,count,4)]
    completed=0;started=monotonic();last=0
    label=(PathProgress(lambda v:None,kwargs['sizing']).label if enabled(kwargs.get('sizing')) else f"{kwargs['micros']} MNQ")
    def notify(done,total,workers,pids):
        nonlocal last
        now=monotonic()
        if now-last<1 and done not in (0,total):return
        last=now;elapsed=now-started
        progress(dict(stage='saved_trade_execution',sizing_label=label,completed=completed,total=count,
            unit='account paths',worker_count=workers,active_workers=min(workers,total-done),worker_pids=pids,
            elapsed_seconds=round(elapsed,2),eta_seconds=round(elapsed*(count-completed)/completed,2) if completed>=8 else None))
    def arrived(value):
        nonlocal completed
        completed+=len(value[0])
    with TemporaryDirectory(prefix='aq-account-paths-') as directory:
        marker=Path(directory)/'stop'
        results=map_reported(task,[(kind,kwargs,indices,str(marker)) for indices in chunks],
            checkpoint=checkpoint,notify=notify,cancel=lambda:marker.touch(),on_result=arrived)
    schedule=sha256();rows=[]
    for paths,raw,partial in results:
        rows.extend(paths);schedule.update(raw)
        if trace is not None:merge_trace(trace,partial)
    return rows,schedule.hexdigest()


def merge_trace(trace,partial):
    from decimal import Decimal
    from ..decimal_math import add
    target=trace.summary
    for key,value in partial['summary'].items():
        if key in ('min_quantity','max_quantity'):
            if value is not None:target[key]=value if target.get(key) is None else (min if key.startswith('min') else max)(target[key],value)
        elif key=='maximum_actual_risk_percent':target[key]=str(max(Decimal(target.get(key,'0')),Decimal(value)))
        elif key.startswith('total_'):target[key]=str(add(Decimal(target.get(key,'0')),Decimal(value)))
        elif key=='behavior_examples':
            groups=target.setdefault(key,{})
            for name,examples in value.items():groups[name]=(groups.get(name,[])+examples)[:5]
        elif isinstance(value,dict):
            group=target.setdefault(key,{})
            for name,n in value.items():group[name]=group.get(name,0)+n
        else:target[key]=target.get(key,0)+value
    trace.decisions.extend(partial['decisions'][:max(0,trace.limit-len(trace.decisions))])


def candidate_task(value):
    directory,search,check,training,marker=value
    from ..prop_sim_preparation import read_context
    from .evaluation_optimization import optimize_evaluation
    def checkpoint():
        if Path(marker).exists():raise RuntimeError('Evaluation sizing stopped')
    result=optimize_evaluation(read_context(directory).app.state.runs,search,[check],
        training_context=training,checkpoint=checkpoint)
    return result['candidates'][0]


def run_candidates(runs,search,checks,training,checkpoint,progress):
    from dataclasses import replace,asdict
    from .adapter import canonical
    from .parallel import map_reported
    configurations={canonical(asdict(c)):c for c in search.candidates}
    def notify(done,total,workers,pids):
        progress(dict(stage='saved_trade_execution',sizing_label='Independent Evaluation sizes',completed=done,total=total,
            unit='sizes',worker_count=workers,active_workers=min(workers,total-done),worker_pids=pids))
    with TemporaryDirectory(prefix='aq-evaluation-sizes-') as temporary:
        marker=Path(temporary)/'stop';values=[]
        for check in checks:
            candidate=configurations[canonical(check['manifest']['configuration'])]
            one=replace(search,source_backtest_id=candidate.source.source_backtest_id,candidates=(candidate,))
            values.append((str(runs.path.parent),one,check,training,str(marker)))
        return map_reported(candidate_task,values,checkpoint=checkpoint,notify=notify,cancel=marker.touch)

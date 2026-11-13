"""Deterministic historical refits on the existing bounded prop process pool.

Only internally written, ephemeral context files are read by workers. Numerical
account paths are still calculated by oos_qualification._means and phase owners.
"""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import pickle
from tempfile import TemporaryDirectory
from time import monotonic

import numpy as np

_loaded_path=None
_loaded_context=None


def _replicate(task):
    global _loaded_path,_loaded_context
    filename,expected,index=task
    if _loaded_path!=filename:
        raw=Path(filename).read_bytes()
        if sha256(raw).hexdigest()!=expected:raise ValueError('Historical worker context changed.')
        _loaded_context=pickle.loads(raw)  # Trusted internal temporary calculation input only.
        _loaded_context['caches']=({},{});_loaded_path=filename
    context=_loaded_context
    from .native_engine import sampled_days
    from .oos_qualification import _means
    next_check=0.
    def checkpoint():
        nonlocal next_check
        now=monotonic()
        if now>=next_check:
            if Path(context['cancel_file']).exists():raise RuntimeError('Historical refit stopped.')
            next_check=now+.1
    checkpoint();values=[];trace=[];keys=[];precision=True
    for role,(days,candidate,labels,cache) in enumerate(zip(context['books'],context['candidates'],context['codes'],context['caches'])):
        seed=int(np.random.SeedSequence([context['history_seed'],role,index]).generate_state(1)[0])
        stream=sampled_days(np.random.RandomState(seed),len(days),context['outer_block'])
        indices=np.fromiter((next(stream) for _ in days),dtype=np.int32,count=len(days))
        key=labels[indices].tobytes()
        if key not in cache:cache[key]=_means([days[int(i)] for i in indices],candidate,context['search'],checkpoint)
        means,error=cache[key];values.append(means)
        precision=bool(precision and error is not None and error<=context['maximum_inner_relative_standard_error'])
        keys.append(sha256(key).hexdigest())
        trace.append(dict(seed=seed,indices_sha256=sha256(indices.tobytes()).hexdigest(),
            metrics=means,relative_inner_standard_error=error))
    ratio={key:values[1][key]/values[0][key] if values[0].get(key,0)>0 and values[1].get(key) is not None else None
           for key in context['metrics']}
    return dict(replicate=dict(replicate=index,is_history=trace[0],oos_history=trace[1],ratios=ratio),
        precision=precision,history_keys=keys)


def run(is_days,oos_days,is_candidate,oos_candidate,search,checkpoint,progress):
    from .parallel import map_reported
    from .oos_qualification import RULES,_book_classes,definitions
    started=monotonic();last_write=0.;worker_count=1;worker_pids=[]
    total=RULES['historical_replicates'];phase=search.mode.removesuffix('_optimization')
    outer_block=max(RULES['minimum_outer_block_weekdays'],oos_candidate.sampling.block_weekdays)
    def notify(completed,count,workers,pids):
        nonlocal last_write,worker_count,worker_pids
        worker_count=workers;worker_pids=pids;now=monotonic()
        if completed not in (0,count) and now-last_write<1:return
        if completed==0 and last_write and now-last_write<1:return
        elapsed=now-started;rate=completed/elapsed if elapsed and completed else None
        progress(dict(stage='historical_confidence',phase=phase,micros=oos_candidate.micros,
            completed=completed,total=count,unit='resamples',worker_count=workers,
            active_workers=0 if completed==count else workers,elapsed_seconds=round(elapsed,2),
            resamples_per_second=round(rate,4) if rate else None,
            eta_seconds=round((count-completed)/rate,1) if rate and completed>=max(10,workers) else None,
            updated_at_utc=datetime.now(timezone.utc).isoformat()))
        last_write=now
    checkpoint();notify(0,total,1,[])
    with TemporaryDirectory(prefix='aq-historical-refits-') as temp:
        marker=Path(temp)/'stop';context_path=Path(temp)/'context.pkl'
        context=dict(books=(is_days,oos_days),candidates=(is_candidate,oos_candidate),search=search,
            codes=(_book_classes(is_days),_book_classes(oos_days)),cancel_file=str(marker),
            history_seed=RULES['history_seed'],outer_block=outer_block,
            maximum_inner_relative_standard_error=RULES['maximum_inner_relative_standard_error'],
            metrics=[k for k,_,_,_ in definitions(phase)])
        raw=pickle.dumps(context,protocol=pickle.HIGHEST_PROTOCOL);context_path.write_bytes(raw)
        signature=sha256(raw).hexdigest()
        tasks=[(str(context_path),signature,index) for index in range(total)]
        rows=map_reported(_replicate,tasks,checkpoint=checkpoint,notify=notify,cancel=marker.touch)
    checkpoint()
    return dict(replicates=[r['replicate'] for r in rows],inner_precision_ok=all(r['precision'] for r in rows),
        outer_block_weekdays=outer_block,
        unique_histories_evaluated=[len({r['history_keys'][role] for r in rows}) for role in (0,1)],
        memoization='Only numerically identical entire resampled daybooks reuse the same phase calculation. No requested path count is reduced.',
        execution=dict(workers_used=worker_count,worker_pids=worker_pids,nested_pool=False,
            elapsed_seconds=round(monotonic()-started,2),ordered_by='replicate_index',
            context='Internal temporary input loaded once per process; removed after workers finish'))

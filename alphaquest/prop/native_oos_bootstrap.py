"""Frozen percentage-policy historical refits using actual native phase owners.

Only origin frequencies are resampled. Prices, causal prefixes, rules and the
selected policy are unchanged. Existing Runtime/checkpoints own execution.
"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
import pickle
import numpy as np
from .adapter import canonical

VERSION='native-percentage-two-history-v1'
_loaded=None
_context=None


def means(inputs,candidate,search,weights,checkpoint):
    from .evaluation_profiles import forecast_native_evaluation,native_acquisition_metrics
    from .funded_profiles import forecast_native_funded
    options=dict(inputs,forecast=inputs['forecast'].model_copy(update={'capture_paths':0}),
        origin_weights=weights,parallel=False,checkpoint=checkpoint)
    if search.mode=='evaluation_optimization':
        forecast=forecast_native_evaluation(**options,retry=candidate.retry,chain_sampling=candidate.sampling)
        result=native_acquisition_metrics(forecast)
        keys=('cost_per_funded','expected_calendar_days_to_funded')
        values={k:result['metrics'].get(k) for k in keys}
        errors=[result['uncertainty'].get(k) for k in ('cost_se','calendar_mean_se')]
    else:
        forecast=forecast_native_funded(**options,receipt_delay_calendar_days=search.receipt_delay_calendar_days,
            receipt_amount_convention='kernel_entitlement_unrounded')
        estimate=forecast['uncertainty']['metrics']['mean_received_cash']
        values={'expected_funded_cash_payouts_within_horizon':estimate['mean']}
        errors=[estimate['mc_standard_error']]
    ratios=[error/value for error,value in zip(errors,values.values()) if error is not None and value is not None and value>0]
    error=max(ratios) if len(ratios)==len(values) else None
    schedules=sha256(canonical([s['schedule_sha256'] for s in forecast['schedules']]).encode()).hexdigest()
    return values,error,schedules


def _replicate(task):
    global _loaded,_context
    filename,signature,index=task
    if _loaded!=filename:
        raw=Path(filename).read_bytes()
        if sha256(raw).hexdigest()!=signature:raise ValueError('Native historical worker context changed.')
        _context=pickle.loads(raw)  # Internally written, checksummed ephemeral input.
        _context['memo']=({},{});_loaded=filename
    c=_context;last=0.
    def checkpoint():
        nonlocal last
        now=monotonic()
        if now-last>=.1:
            if Path(c['cancel_file']).exists():raise RuntimeError('Native historical refit stopped.')
            last=now
    from .native_draws import history_origin_weights,NativeHistoryPoolUnavailable
    checkpoint();histories=[];values=[];precision=True;keys=[]
    for role,(inputs,candidate,cache) in enumerate(zip(c['inputs'],c['candidates'],c['memo'])):
        role_seed=int(np.random.SeedSequence([c['rules']['history_seed'],role]).generate_state(1)[0])
        weights=history_origin_weights(inputs['catalogue'],block_sessions=c['outer_block'],history_seed=role_seed,replicate=index)
        key=sha256(np.asarray(weights['origin_counts'],dtype='<i8').tobytes()).hexdigest()
        # Bounded exact-law reuse; never reduce the requested inner count.
        if key not in cache:
            try:cache[key]=means(inputs,candidate,c['search'],weights,checkpoint)
            except NativeHistoryPoolUnavailable:cache[key]=({},None,None)
            if len(cache)>64:cache.pop(next(iter(cache)))
        metrics,error,schedule_hash=cache[key];values.append(metrics);keys.append(key)
        precision=precision and error is not None and error<=c['rules']['maximum_inner_relative_standard_error']
        histories.append(dict(role_seed=role_seed,derived_history_seed=weights['derived_history_seed'],
            weights_sha256=weights['weights_sha256'],origin_counts_sha256=key,inner_schedule_sha256=schedule_hash,
            metrics=metrics,relative_inner_standard_error=error,inner_paths=candidate.simulation.simulations))
    ratios={k:values[1][k]/values[0][k] if values[0].get(k) is not None and values[0][k]>0 and values[1].get(k) is not None else None for k in c['metrics']}
    return dict(replicate=dict(replicate=index,is_history=histories[0],oos_history=histories[1],ratios=ratios),precision=bool(precision),history_keys=keys,preparation_cache_bytes=0)


def run(is_inputs,oos_inputs,is_candidate,oos_candidate,search,checkpoint,progress,*,resume=None):
    from .oos_qualification import RULES,definitions,implementation
    from .parallel import map_reported
    from .native_preparation import worker_programme
    from .phase_dispatch import module_for_mode
    from .sizing_search import axis
    total=RULES['historical_replicates'];phase=search.mode.removesuffix('_optimization')
    identity=dict(version=VERSION,catalogues=[i['catalogue'].metadata() for i in (is_inputs,oos_inputs)],
        candidates=[asdict(c) for c in (is_candidate,oos_candidate)],search=asdict(search),rules=RULES,
        implementation=implementation(),phase_implementation=module_for_mode(search.mode).implementation_identity())
    context_key=sha256(canonical(identity).encode()).hexdigest()
    restored=resume[0].load_refits(context_key,total) if resume else {};reused=len(restored)
    started=monotonic();last=0.;workers_used=1;worker_pids=[]
    def notify(done,count,workers,pids):
        nonlocal last,workers_used,worker_pids
        now=monotonic();workers_used=workers;worker_pids=pids
        if done not in (0,total) and now-last<1:return
        elapsed=now-started;rate=(done-reused)/elapsed if done>reused and elapsed else None
        progress(dict(stage='historical_confidence',phase=phase,sizing_label=axis(asdict(oos_candidate))['label'],
            completed=done,total=total,unit='refits',worker_count=workers,active_workers=0 if done==total else workers,
            reused_resamples=reused,elapsed_seconds=round(elapsed,2),eta_seconds=(total-done)/rate if rate else None))
        last=now
    outer_block=max(RULES['minimum_outer_block_weekdays'],oos_candidate.sampling.block_weekdays)
    with TemporaryDirectory(prefix='aq-native-historical-') as tmp:
        path=Path(tmp);inputs=[]
        for role,original in enumerate((is_inputs,oos_inputs)):
            directory=path/str(role);directory.mkdir()
            programme=worker_programme(original['preparation'],directory,checkpoint=checkpoint)
            inputs.append(dict(original,preparation=programme,catalogue=programme.catalogue,strategy_factory=programme.factory))
        marker=path/'stop';context=path/'context.pkl'
        payload=dict(inputs=inputs,candidates=(is_candidate,oos_candidate),search=search,rules=RULES,outer_block=outer_block,
            metrics=[k for k,_,_,_ in definitions(phase)],cancel_file=str(marker))
        raw=pickle.dumps(payload,protocol=pickle.HIGHEST_PROTOCOL);context.write_bytes(raw);signature=sha256(raw).hexdigest()
        pending=[];last_flush=monotonic()
        def flush():
            nonlocal last_flush
            if resume and pending:resume[0].save_refits(resume[1],context_key,pending);pending.clear()
            last_flush=monotonic()
        def completed(row):
            if resume:
                pending.append(row)
                if monotonic()-last_flush>=1:flush()
        tasks=[(str(context),signature,i) for i in range(total) if i not in restored]
        notify(reused,total,1,[])
        try:fresh=map_reported(_replicate,tasks,checkpoint=checkpoint,notify=lambda d,n,w,p:notify(d+reused,total,w,p),cancel=marker.touch,on_result=completed)
        finally:flush()
        restored.update((r['replicate']['replicate'],r) for r in fresh)
        rows=[restored[i] for i in range(total)];notify(total,total,workers_used,worker_pids)
    return dict(version=VERSION,replicates=[r['replicate'] for r in rows],inner_precision_ok=all(r['precision'] for r in rows),
        outer_block_origin_positions=outer_block,unique_histories_evaluated=[len({r['history_keys'][role] for r in rows}) for role in (0,1)],
        memoization='Only identical complete origin-frequency laws reuse full native inner calculations; bounded to 64 laws per role/worker.',
        execution=dict(checkpoint_context_sha256=context_key,reused_resamples=reused,workers_used=workers_used,
            worker_pids=worker_pids,nested_pool=False,elapsed_seconds=round(monotonic()-started,2),
            inner_path_counts=[c.simulation.simulations for c in (is_candidate,oos_candidate)]))

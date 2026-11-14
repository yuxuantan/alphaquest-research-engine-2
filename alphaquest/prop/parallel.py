"""Bounded independent prop tasks; optimization children never create pools."""
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager,nullcontext
from contextvars import ContextVar
import multiprocessing as mp
import os
from threading import Condition,Lock

CAPACITY=max(1,min(8,(os.cpu_count() or 1)-1))
_active=ContextVar('prop_runtime',default=None)
_diagnostics=ContextVar('prop_execution',default=None)
_budget_owner=ContextVar('prop_budget_owner',default=None)
_optimizing=ContextVar('prop_optimizing',default=False)


def _task(function,value):return function(value),os.getpid()


class Runtime:
    def __init__(self,workers=None):
        self.workers=int(os.environ.get('ALPHAQUEST_PROP_WORKERS',str(min(4,CAPACITY)))) if workers is None else workers
        if not 1<=self.workers<=CAPACITY:raise ValueError(f'Prop workers must be between 1 and {CAPACITY}.')
        self.condition=Condition();self.occupied=0;self.pool=None;self.pool_lock=Lock()

    @contextmanager
    def reserve(self,count,exact=False):
        if not 1<=count<=CAPACITY:raise ValueError('Worker reservation exceeds capacity.')
        with self.condition:
            while CAPACITY-self.occupied < (count if exact else 1):self.condition.wait()
            taken=count if exact else min(count,CAPACITY-self.occupied)
            self.occupied+=taken
        try:yield taken
        finally:
            with self.condition:self.occupied-=taken;self.condition.notify_all()

    @contextmanager
    def activate(self,*,reserve=True):
        # Serial validation/replay also occupies a slot. A waiting parallel map
        # transfers that slot to its workers, avoiding upgrade deadlocks when
        # several concurrent analyses have each reserved one serial slot.
        with self.reserve(1) if reserve else nullcontext():
            token=_active.set(self);owner=_budget_owner.set(self if reserve else None)
            diagnostic=_diagnostics.set(dict(workers_used=1,worker_pids=[],nested_pool=False))
            try:yield
            finally:_diagnostics.reset(diagnostic);_budget_owner.reset(owner);_active.reset(token)

    @contextmanager
    def parallel_slots(self,count):
        transfer=_budget_owner.get() is self
        if transfer:
            with self.condition:self.occupied-=1;self.condition.notify_all()
        try:
            with self.reserve(count) as slots:yield slots
        finally:
            if transfer:
                with self.condition:
                    while self.occupied>=CAPACITY:self.condition.wait()
                    self.occupied+=1

    @contextmanager
    def optimization(self,workers):
        token=_optimizing.set(True)
        try:
            with self.reserve(workers,exact=True),self.activate(reserve=False):yield
        finally:_optimizing.reset(token)

    def close(self):
        if self.pool is not None:self.pool.shutdown(wait=True,cancel_futures=True)

    def map(self,function,values,work):
        threshold=2_000_000 if self.pool is not None else 20_000_000
        if self.workers==1 or work<threshold or len(values)<2:return [function(v) for v in values]
        with self.parallel_slots(min(self.workers,len(values))) as slots:
            if slots==1:return [function(v) for v in values]
            with self.pool_lock:
                if self.pool is None:self.pool=ProcessPoolExecutor(max_workers=CAPACITY,mp_context=mp.get_context('spawn'))
                pool=self.pool
            results=[];pending=[];source=iter(values)
            try:
                for _ in range(slots):
                    value=next(source,None)
                    if value is not None:pending.append(pool.submit(_task,function,value))
                while pending:
                    result,pid=pending.pop(0).result();results.append(result)
                    diagnostic=_diagnostics.get()
                    if diagnostic is not None:
                        diagnostic['workers_used']=max(diagnostic['workers_used'],slots)
                        diagnostic['worker_pids']=sorted(set([*diagnostic['worker_pids'],pid]))
                    value=next(source,None)
                    if value is not None:pending.append(pool.submit(_task,function,value))
                return results
            except BrokenProcessPool:
                with self.pool_lock:
                    if self.pool is pool:self.pool=None
                pool.shutdown(wait=False,cancel_futures=True)
                raise
            except BaseException:
                # Keep the reservation until any already-running siblings stop.
                for future in pending:future.cancel()
                for future in pending:
                    try:future.result()
                    except BaseException:pass
                raise

    def map_reported(self,function,values,*,checkpoint,notify,cancel,on_result=lambda result:None):
        """Bounded completion-order dispatch, ordered output and responsive stop.

        Uses this same pool/budget; the worker does not recursively dispatch.
        Notifications contain metadata only and never change calculation inputs.
        """
        values=list(values);total=len(values)
        if not total:return []
        with self.parallel_slots(min(self.workers,total)) as slots:
            if slots==1:
                results=[]
                for value in values:
                    checkpoint();result=function(value);on_result(result);results.append(result);notify(len(results),total,1,[os.getpid()])
                return results
            with self.pool_lock:
                if self.pool is None:self.pool=ProcessPoolExecutor(max_workers=CAPACITY,mp_context=mp.get_context('spawn'))
                pool=self.pool
            results=[None]*total;pending={};next_index=0;completed=0;pids=set()
            def submit():
                nonlocal next_index
                pending[pool.submit(_task,function,values[next_index])]=next_index;next_index+=1
            try:
                for _ in range(slots):submit()
                notify(0,total,slots,[])
                while pending:
                    checkpoint()
                    done,_=wait(pending,timeout=.25,return_when=FIRST_COMPLETED)
                    for future in done:
                        result,pid=future.result();on_result(result);results[pending.pop(future)]=result
                        completed+=1;pids.add(pid)
                        if next_index<total:submit()
                    notify(completed,total,slots,sorted(pids))
                diagnostic=_diagnostics.get()
                if diagnostic is not None:
                    diagnostic['workers_used']=max(diagnostic['workers_used'],slots)
                    diagnostic['worker_pids']=sorted(set(diagnostic['worker_pids'])|pids)
                return results
            except BaseException as exc:
                cancel()  # Workers observe the marker before the reservation releases.
                for future in pending:future.cancel()
                for future in pending:
                    try:future.result()
                    except BaseException:pass
                if isinstance(exc,BrokenProcessPool):
                    with self.pool_lock:
                        if self.pool is pool:self.pool=None
                    pool.shutdown(wait=False,cancel_futures=True)
                raise


def map_sweep(function,values,work):
    runtime=_active.get()
    # An optimization's parent already reserves its child processes' CPU slots.
    if runtime is None or _optimizing.get() or mp.current_process().name!='MainProcess':return [function(v) for v in values]
    return runtime.map(function,list(values),work)


def diagnostics():
    return dict(_diagnostics.get() or dict(workers_used=1,worker_pids=[os.getpid()],nested_pool=False))


def map_reported(function,values,*,checkpoint,notify,cancel,on_result=lambda result:None):
    runtime=_active.get()
    # The uvicorn reload child is a legitimate owner. Actual pool children have
    # no active runtime context; never infer nesting from the process's name.
    if runtime is not None and not _optimizing.get():
        return runtime.map_reported(function,values,checkpoint=checkpoint,notify=notify,cancel=cancel,on_result=on_result)
    results=[]
    for value in values:
        checkpoint();result=function(value);on_result(result);results.append(result);notify(len(results),len(values),1,[os.getpid()])
    return results

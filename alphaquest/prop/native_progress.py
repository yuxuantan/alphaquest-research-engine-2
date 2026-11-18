"""Metadata-only native path progress; never persisted in numerical outputs."""
from time import monotonic

ETA_BASIS = 'completed-worker-paths-v1'


def execute_path(task):
    """Load the shared checked source once per worker, then time actual replay."""
    from .native_preparation import _native_context, _native_batch
    _native_context(task[0], task[1])
    started = monotonic()
    return _native_batch(task), started


class NativeProgress:
    def __init__(self, total, captured, metadata, publish, *, clock=monotonic):
        self.total = total
        self.captured = captured
        self.metadata = metadata
        self.publish = publish
        self.clock = clock
        self.started = clock()
        self.worker_started = None
        self.completed = 0
        self.last_write = None
        self.last_state = None

    def received(self, packet):
        rows, started = packet
        self.completed += len(rows)
        self.worker_started = started if self.worker_started is None else min(self.worker_started, started)

    def evidence(self, complete, *, preparing=False):
        state = 'complete' if complete == self.total else 'preparing_workers' if preparing else 'capturing_evidence'
        self._publish(complete, 1, 0 if preparing or complete == self.total else 1,
                      state, 0 if complete == self.total else None, 0, force=True)

    def notify(self, done, total, workers, pids):
        complete = self.captured + self.completed
        remaining = self.total - complete
        minimum = min(self.total - self.captured, max(4, workers * 2))
        elapsed = self.clock() - self.worker_started if self.worker_started is not None else 0
        ready = self.completed >= minimum and len(pids) >= min(workers, total) and elapsed > 0
        state = 'complete' if not remaining else 'ready' if ready else 'warming_up'
        eta = 0 if not remaining else remaining * elapsed / self.completed if ready else None
        self._publish(complete, workers, min(workers, remaining), state, eta, minimum)

    def _publish(self, complete, workers, active, state, eta, minimum, *, force=False):
        now = self.clock()
        if not force and self.last_write is not None and now - self.last_write < 1 and state == self.last_state:
            return
        self.publish(dict(self.metadata, completed=complete, total=self.total, unit='account paths',
            worker_count=workers, active_workers=active, elapsed_seconds=round(now-self.started, 2),
            eta_seconds=eta, eta_basis=ETA_BASIS, eta_status=state,
            eta_sample_paths=self.completed, eta_minimum_paths=minimum,
            worker_elapsed_seconds=round(now-self.worker_started, 2) if self.worker_started is not None else None))
        self.last_write = now
        self.last_state = state

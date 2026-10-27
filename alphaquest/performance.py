"""Exclusive wall-clock timings; diagnostics never enter financial arithmetic."""
from contextlib import contextmanager
import json
from pathlib import Path
from time import perf_counter


class Performance:
    def __init__(self):
        self.started = perf_counter()
        self.phases = {}
        self.stack = []
        self.details = {}

    @contextmanager
    def span(self, name):
        frame = [name, perf_counter(), 0.0]
        self.stack.append(frame)
        try:
            yield
        finally:
            elapsed = perf_counter() - frame[1]
            self.stack.pop()
            self.phases[name] = self.phases.get(name, 0.0) + max(0.0, elapsed - frame[2])
            if self.stack:
                self.stack[-1][2] += elapsed

    def iterate(self, values, name):
        iterator = iter(values)
        try:
            while True:
                with self.span(name):
                    try:
                        value = next(iterator)
                    except StopIteration:
                        return
                yield value
        finally:
            close = getattr(iterator, 'close', None)
            if close:
                close()

    def snapshot(self):
        return dict(version=1, elapsed_seconds=perf_counter()-self.started,
                    phases_seconds=dict(self.phases), details=dict(self.details))


def save_performance(directory, result):
    """A failed optional diagnostic must not invalidate a published backtest."""
    import logging
    try:
        (Path(directory)/'performance.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    except OSError:
        logging.getLogger(__name__).warning('Could not save backtest timing diagnostics', exc_info=True)

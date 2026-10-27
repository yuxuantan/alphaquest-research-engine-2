"""Pure calculation reuse from verified AlphaQuest reports, never external output.

A source is adapted/reconciled afresh. Workers receive immutable references and
checksums, never catalogue handles. Reuse does not skip source validation or
change the new report's source identity.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import json
from pathlib import Path
from ..optimization_cache import digest,engine_identity

_active=ContextVar('prop_calculation_cache',default={})


@contextmanager
def use(entries):
    token=_active.set(entries or {})
    try:yield
    finally:_active.reset(token)


def calculate(rows,settings,snapshot,progress,compute):
    key=digest(dict(engine=engine_identity(),rows=rows,settings=settings,
                    trades=snapshot['trades_sha256'],excursions=snapshot['excursion_input'],
                    timezone=snapshot['source_timezone'],sessions=snapshot['session_grid']))
    entry=_active.get().get(key)
    if entry:
        try:
            raw=Path(entry['path']).read_bytes()
            if sha256(raw).hexdigest()==entry['sha256']:
                result=json.loads(raw)
                progress('Reusing verified local calculations; source checks complete')
                return result,entry['id'],key
        except (OSError,ValueError):pass
    return compute(rows,settings,progress),None,key

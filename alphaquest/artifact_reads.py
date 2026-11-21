"""Request-local reuse of verified artifact hashes, never a durable authority."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import file_digest
from pathlib import Path

_current = ContextVar('artifact_read_scope', default=None)


def stamp(path):
    path=Path(path)
    try:
        link=path.lstat()
        value=(str(path),link.st_dev,link.st_ino,link.st_mode,link.st_size,link.st_mtime_ns,link.st_ctime_ns)
        if path.is_symlink():
            target=path.stat()
            value+=(str(path.resolve()),target.st_dev,target.st_ino,target.st_size,target.st_mtime_ns,target.st_ctime_ns)
        return value
    except FileNotFoundError:
        return (str(path),None)


def read_hash(path):
    scope=_current.get()
    if scope is None:
        with Path(path).open('rb') as source:return file_digest(source,'sha256').hexdigest()
    before=stamp(path);key=str(path)
    if key in scope['stamps'] and scope['stamps'][key]!=before:
        raise ValueError('Saved artifact changed during verification.')
    scope['stamps'][key]=before
    if key not in scope['hashes']:
        with Path(path).open('rb') as source:scope['hashes'][key]=file_digest(source,'sha256').hexdigest()
        if stamp(path)!=before:raise ValueError('Saved artifact changed during verification.')
    return scope['hashes'][key]


def memo_value(key,calculate):
    scope=_current.get()
    if scope is None:return calculate()
    if key not in scope['values']:scope['values'][key]=calculate()
    return scope['values'][key]


@contextmanager
def verified_reads():
    """Verify shared bytes once, checking all file identities again before return."""
    if _current.get() is not None:
        yield
        return
    scope=dict(stamps={},hashes={},values={});token=_current.set(scope)
    try:
        yield
        if any(stamp(path)!=value for path,value in scope['stamps'].items()):
            raise ValueError('Saved artifact changed during verification.')
    finally:_current.reset(token)

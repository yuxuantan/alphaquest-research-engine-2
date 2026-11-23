"""Reuse verified observed-session metadata for a saved dataset version."""

from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock
from weakref import WeakValueDictionary
from zoneinfo import TZPATH

from .backtest_data import DatasetReadError, saved_source_timezone


_locks = WeakValueDictionary()
_locks_guard = Lock()


@lru_cache(maxsize=1)
def _reader_identity():
    root = Path(__file__).parent
    # Changes to parsing, session labels or observation hashing expire the index.
    files = ('research_folds.py', 'backtest_data.py', 'datasets.py',
             'research_access.py', 'session_calendar.py', 'tick_data.py')
    return {name: sha256((root / name).read_bytes()).hexdigest() for name in files}


@lru_cache(maxsize=64)
def _zone_identity(name):
    for root in TZPATH:
        path = Path(root) / name
        if path.is_file():
            return sha256(path.read_bytes()).hexdigest()
    from importlib import resources
    return sha256(resources.files('tzdata.zoneinfo').joinpath(*name.split('/')).read_bytes()).hexdigest()


def _source_key(dataset, convention):
    zone = saved_source_timezone(dataset).key
    evidence = {name: dataset.get(name) for name in (
        'id', 'sha256', 'csv_sha256', 'source_timezone', 'row_count', 'bytes',
        'columns', 'tick_data', 'instrument_settings')}
    binding = dict(version=1, convention=convention, dataset=evidence, readers=_reader_identity(),
                   zones={name: _zone_identity(name) for name in {zone, 'America/Chicago'}})
    return sha256(json.dumps(binding, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _verify_source_bytes(source, dataset):
    digest = sha256()
    length = 0
    for chunk in source.iter_csv(dataset['id']):
        digest.update(chunk)
        length += len(chunk)
    if length != dataset['bytes'] or digest.hexdigest() != dataset.get('csv_sha256', dataset['sha256']):
        raise DatasetReadError('Saved CSV bytes do not match the dataset metadata; the dataset may be unavailable or incomplete.')
    if dataset.get('tick_data'):
        from .tick_data import check_sources
        check_sources(dataset)


def load_or_build(source, dataset, convention, build):
    """Publish atomically. Recheck source bytes even when the derived index hits."""
    dataset_id = dataset['id']
    with _locks_guard:
        lock = _locks.setdefault((source.path, dataset_id), Lock())
    with lock:
        key = _source_key(dataset, convention)
        with source.connect() as db:
            row = db.execute('SELECT payload,sha256 FROM dataset_session_inventory '
                             'WHERE dataset_id=? AND source_key=?', (dataset_id, key)).fetchone()
        cached = None
        if row and sha256(row[0].encode()).hexdigest() == row[1]:
            try:
                cached = json.loads(row[0])
            except ValueError:
                pass
        if cached is None:
            value = build(source, dataset)
        else:
            _verify_source_bytes(source, dataset)
            value = cached
        current = source.get(dataset_id)
        if current is None or _source_key(current, convention) != key:
            raise DatasetReadError('Saved dataset changed while inventorying its observed sessions.')
        if cached is not None:
            return value
        # Retain the session insertion order, as with a freshly computed inventory.
        payload = json.dumps(value, separators=(',', ':'), allow_nan=False)
        with source.connect() as db:
            db.execute('INSERT INTO dataset_session_inventory VALUES (?,?,?,?) '
                       'ON CONFLICT(dataset_id) DO UPDATE SET source_key=excluded.source_key, '
                       'payload=excluded.payload,sha256=excluded.sha256',
                       (dataset_id, key, payload, sha256(payload.encode()).hexdigest()))
        return value

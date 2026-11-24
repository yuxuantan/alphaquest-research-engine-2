"""Compact Portfolio summaries and the existing sealed evidence ZIP."""
import csv
import json
import os

from .adapter import canonical
from .store import seal_report

MAX_BYTES = 100_000_000
DETAILS = frozenset({'cash_ledger','trades','sizing_decisions','transitions','pending_settlements','accounts'})
CSV_DETAILS = ('cash_ledger','trades','sizing_decisions','transitions')


def summary(result):
    return {key: value for key, value in result.items() if key not in DETAILS}


def write_evidence(staged, name, result):
    for key in CSV_DETAILS:
        rows = result[key]
        fields = list(dict.fromkeys(field for row in rows for field in row))
        with (staged/f'{name}_{key}.csv').open('w', encoding='utf-8', newline='') as stream:
            writer=csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    (staged/f'{name}_accounts.json').write_text(canonical(result['accounts']))


def seal_portfolio(staged, report, id, created):
    report['portfolio_storage'] = dict(version=1, maximum_bytes=MAX_BYTES,
        evidence='CSV details and account summaries are stored once in the evidence ZIP.')
    seal_report(staged, report, id, created, size_limit_bytes=None)
    size = sum(path.stat().st_size for path in staged.rglob('*') if path.is_file())
    if size > MAX_BYTES:
        raise ValueError('Portfolio report exceeds the 100 MB storage limit.')
    return size


def read_summary(store, id):
    from hashlib import sha256
    with store.connect() as db:
        saved = db.execute('SELECT payload FROM analysis_report_checks WHERE id=?',(id,)).fetchone()
    with (store.root/id/'report.json').open('rb') as stream:
        size=os.fstat(stream.fileno()).st_size
        if size>MAX_BYTES:raise ValueError('This legacy Portfolio report requires compacting before it can be opened.')
        raw = stream.read(size+1)
    if not saved or sha256(raw).hexdigest()!=json.loads(saved[0])['report.json']:
        raise ValueError('Portfolio report is incomplete or changed.')
    return json.loads(raw)

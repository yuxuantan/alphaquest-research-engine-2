"""Convert saved bar comparisons to shared DAY storage without replaying trades.

Requires an idle optimization queue. Evidence preserves the catalogue, original
small manifests/reports, hashes and conversion journal, not the large old CSVs.
Only verified, published conversions reclaim their original CSV space.
"""

import argparse
from contextlib import ExitStack, closing
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from .compress_optimization_reports import maintenance_lock
from .database import connection
from .market_benchmark import load_comparison
from .market_equity import (DailyEquityWriter, STRATEGY_FILE, daily_storage,
                            equity_csv, legacy_daily_rows, file_hash, publish_holding)


def _write_report(path, report):
    opener = gzip.open if path.name.endswith('.gz') else open
    with opener(path, 'wt', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')


def migrate_existing(directory, evidence, progress=print):
    root, evidence = Path(directory).expanduser().resolve(), Path(evidence).expanduser().resolve()
    database = root / 'backtests.sqlite3'
    if not database.is_file():
        raise ValueError(f'Backtest catalogue not found: {database}')
    outcomes = []
    with maintenance_lock(root):
        shared_before = sum(p.stat().st_size for p in (root / 'market_benchmarks').glob('*.csv'))
        with connection(database) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='optimizations'").fetchone():
                if any(json.loads(row[0])['status'] in ('queued', 'running') for row in db.execute('SELECT payload FROM optimizations')):
                    raise ValueError('Wait for queued/running optimizations to finish before converting saved comparisons.')
            rows = list(db.execute('SELECT id, manifest FROM runs ORDER BY id'))
            evidence.mkdir(parents=True, exist_ok=False)
            with closing(sqlite3.connect(evidence / 'backtests-before.sqlite3')) as backup:
                db.backup(backup)
        (evidence / 'before.json').write_text(json.dumps(dict(
            created_at_utc=datetime.now(timezone.utc).isoformat(), data_directory=str(root),
            reports=[json.loads(payload) for _, payload in rows]), indent=2) + '\n')
        with (evidence / 'journal.jsonl').open('x') as journal:
            for run_id, payload in rows:
                record = json.loads(payload)
                descriptor = record.get('market_benchmark')
                if not descriptor:
                    continue
                if len(run_id) != 32 or any(c not in '0123456789abcdef' for c in run_id):
                    raise ValueError('Invalid saved run ID.')
                folder = root / 'backtest_runs' / run_id
                if folder.is_symlink():
                    raise ValueError('Refusing to convert a symbolic-link report directory.')
                if descriptor.get('storage'):
                    # Finish cleanup if a previous process stopped after commit.
                    original = folder / 'market_equity.csv'
                    if original.exists():
                        previous_hash = descriptor['storage'].get('previous_bar_equity_sha256')
                        if not previous_hash or file_hash(original) != previous_hash:
                            raise ValueError('Unexpected original CSV beside daily report; no files removed.')
                        load_comparison(folder, descriptor)
                        if hashlib.sha256(equity_csv(folder, descriptor)).hexdigest() != descriptor['equity_sha256']:
                            raise ValueError('Daily conversion failed verification; original CSV preserved.')
                        entry = dict(run_id=run_id, status='recovered_cleanup', original_bytes=original.stat().st_size,
                                     strategy_bytes=(folder / STRATEGY_FILE).stat().st_size)
                        journal.write(json.dumps(entry) + '\n'); journal.flush(); os.fsync(journal.fileno())
                        original.unlink()
                        outcomes.append(entry)
                    continue
                if (folder / STRATEGY_FILE).exists():
                    raise ValueError('Unexpected daily strategy file beside legacy report; no files replaced.')
                data = load_comparison(folder, descriptor)
                original = folder / 'market_equity.csv'
                old_size = original.stat().st_size
                old_identity = original.stat()
                report_name = record['artifacts']['report']
                if report_name not in ('report.json', 'report.json.gz'):
                    raise ValueError('Unsupported saved report artifact.')
                report_path = folder / report_name
                small_before = {name: (folder / name).read_bytes() for name in ('market_benchmark.json', report_name)}
                saved = evidence / run_id
                saved.mkdir()
                for name, content in small_before.items():
                    (saved / name).write_bytes(content)
                unchanged = {name: file_hash(folder / name) for name in ('trades.csv', 'equity.csv', 'intratrade_risk.csv') if (folder / name).exists()}
                with TemporaryDirectory(prefix='.daily-', dir=folder) as temporary:
                    staging = Path(temporary)
                    with ExitStack() as stack:
                        writer = DailyEquityWriter(staging, stack, data['source']['dataset']['source_timezone'])
                        for point in legacy_daily_rows(folder, descriptor, data['source']['dataset']['source_timezone']):
                            writer.observe(point)
                        writer.finish_day()
                    converted_data = deepcopy(data)
                    converted_data['storage'] = daily_storage(staging, converted_data, writer.days)
                    converted_data['storage']['previous_bar_equity_sha256'] = descriptor['equity_sha256']
                    content = equity_csv(staging, converted_data)
                    converted_data['equity_sha256'] = hashlib.sha256(content).hexdigest()
                    (staging / 'market_benchmark.json').write_text(json.dumps(converted_data, indent=2) + '\n')
                    converted = deepcopy(record)
                    converted['market_benchmark'].update(
                        storage=converted_data['storage'], equity_sha256=converted_data['equity_sha256'],
                        sha256=file_hash(staging / 'market_benchmark.json'))
                    converted['artifacts'].pop('market_equity_csv', None)
                    converted['artifacts']['strategy_equity_day_csv'] = STRATEGY_FILE
                    opener = gzip.open if report_name.endswith('.gz') else open
                    with opener(report_path, 'rt', encoding='utf-8') as stream:
                        report = json.load(stream)
                    report['market_benchmark'] = converted['market_benchmark']
                    report['artifacts'] = converted['artifacts']
                    _write_report(staging / report_name, report)
                    publish_holding(staging, root, converted['market_benchmark'])
                    entry = dict(run_id=run_id, status='prepared', original_bytes=old_size,
                                 original_sha256=descriptor['equity_sha256'], observed_day_count=writer.days,
                                 storage=converted_data['storage'], unchanged_sha256=unchanged)
                    journal.write(json.dumps(entry) + '\n'); journal.flush(); os.fsync(journal.fileno())
                    replaced = False
                    try:
                        with connection(database) as db:
                            db.execute('BEGIN IMMEDIATE')
                            current = db.execute('SELECT manifest FROM runs WHERE id=?', (run_id,)).fetchone()
                            if not current or current[0] != payload or original.stat() != old_identity:
                                raise ValueError('Saved report changed during conversion; original CSV preserved.')
                            replaced = True
                            for name in (STRATEGY_FILE, 'market_benchmark.json', report_name):
                                os.replace(staging / name, folder / name)
                            db.execute('UPDATE runs SET manifest=? WHERE id=?', (json.dumps(converted), run_id))
                            db.execute('DELETE FROM backtest_reuse WHERE run_id=?', (run_id,))
                            if db.execute("SELECT 1 FROM sqlite_master WHERE name='optimization_trial_cache'").fetchone():
                                db.execute("DELETE FROM optimization_trial_cache WHERE json_extract(payload, '$.row.run_id')=?", (run_id,))
                    except BaseException:
                        if replaced:
                            for name, before in small_before.items():
                                (folder / name).write_bytes(before)
                            (folder / STRATEGY_FILE).unlink(missing_ok=True)
                        raise
                    # Publication and post-publication read/export verification precede deletion.
                    load_comparison(folder, converted['market_benchmark'])
                    if equity_csv(folder, converted['market_benchmark']) != content:
                        raise ValueError('Published daily comparison differs; original CSV preserved.')
                    if any(file_hash(folder / name) != sha for name, sha in unchanged.items()):
                        raise ValueError('Trade/risk records changed; original CSV preserved.')
                    journal.write(json.dumps({**entry, 'status': 'published'}) + '\n'); journal.flush(); os.fsync(journal.fileno())
                    original.unlink()
                    entry.update(status='converted', strategy_bytes=(folder / STRATEGY_FILE).stat().st_size,
                                 export_sha256=converted_data['equity_sha256'])
                    outcomes.append(entry)
                    journal.write(json.dumps(entry) + '\n'); journal.flush(); os.fsync(journal.fileno())
                    progress(f'[{len(outcomes)}] {run_id}: {descriptor["observed_bar_count"]:,} bars → {writer.days:,} days')
        shared = list((root / 'market_benchmarks').glob('*.csv')) if (root / 'market_benchmarks').exists() else []
        result = dict(converted_reports=len(outcomes), before_csv_bytes=sum(x['original_bytes'] for x in outcomes),
                      after_strategy_bytes=sum(x['strategy_bytes'] for x in outcomes),
                      shared_holding_files=len(shared), shared_holding_bytes=sum(p.stat().st_size for p in shared), reports=outcomes)
        result['new_shared_holding_bytes'] = result['shared_holding_bytes'] - shared_before
        new_strategy_bytes = sum(x['strategy_bytes'] for x in outcomes if x['status'] == 'converted')
        result['reclaimed_csv_bytes'] = result['before_csv_bytes'] - new_strategy_bytes - result['new_shared_holding_bytes']
        (evidence / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True, help='New directory for catalogue backup, original small reports and verification')
    args = parser.parse_args()
    result = migrate_existing(args.data_dir, args.evidence)
    print(f'Converted {result["converted_reports"]} reports; reclaimed {result["reclaimed_csv_bytes"]:,} CSV bytes.')


if __name__ == '__main__':
    main()

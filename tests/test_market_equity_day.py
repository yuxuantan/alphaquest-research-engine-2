"""Daily sampling, shared storage, publication, migration and saved export checks."""

import csv
from decimal import Decimal
import hashlib
import io
import json

import pytest

from test_market_benchmark import client, start as single, save, request_body, EXPECTED
from test_optimization import start, wait_job
from alphaquest.market_equity import FIELDS, STRATEGY_FILE, holding_path, equity_csv, file_hash
from alphaquest.migrate_market_equity import migrate_existing


def optimize(client, workers=1):
    dataset = save(client)
    body = request_body(dataset)
    body.pop('strategy_parameters')
    body.update(method='exhaustive', workers=workers, reuse_results=True, parameter_ranges=dict(
        green_bar_count=dict(start=1, end=1, step=0), hold_minutes=dict(start=2, end=2, step=0),
        contracts=dict(start=1, end=3, step=1)))
    job = wait_job(client, start(client, body))
    assert job['status'] == 'complete', job
    rows = client.get(f'/api/optimizations/{job["id"]}/results').json()['items']
    runs = [client.get('/api/backtests/' + row['run_id']).json() for row in rows]
    return dataset, body, job, runs


@pytest.mark.parametrize('workers', [1, 2])
def test_optimization_shares_one_holding_and_keeps_independent_daily_strategy_equity(client, workers):
    dataset, body, job, runs = optimize(client, workers)
    root = client.app.state.runs.root
    shared = root.parent / 'market_benchmarks'
    assert len(list(shared.glob('*.csv'))) == 1
    assert len({r['market_benchmark']['storage']['holding_key'] for r in runs}) == 1
    expected = {1: Decimal(168), 2: Decimal(336), 3: Decimal(504)}
    for run in runs:
        folder = root / run['id']
        assert not (folder / 'market_equity.csv').exists()
        assert not (folder / 'holding_equity_day.csv').exists()
        assert (folder / STRATEGY_FILE).read_text().splitlines()[0] == 'bar_number,strategy_equity,strategy_contracts'
        base = '/api/backtests/' + run['id']
        response = client.get(base + '/exports/market_equity')
        assert response.status_code == 200
        assert 'market_equity_day.csv' in response.headers['content-disposition']
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert [r['date'] for r in rows] == ['', '2026-01-05', '2026-01-06']
        assert [int(r['bar_number']) for r in rows] == [0, 3, 4]
        assert [Decimal(r['holding_equity']) for r in rows] == [10000, 10194, 10188]
        quantity = run['run_metadata']['strategy']['parameters']['contracts']
        assert Decimal(rows[-1]['strategy_equity']) == 10000 + expected[quantity]
        comparison = client.get(base + '/market-benchmark').json()
        assert comparison['chart']['granularity'] == 'DAY'
        assert comparison['chart']['total'] == 3
        assert Decimal(comparison['accounts']['holding']['max_drawdown_amount']) == 220
        assert comparison['storage']['observed_day_count'] == 2
        report = client.get(base + '/exports/report').json()
        assert report['market_benchmark']['storage']['granularity'] == 'DAY'
    repeated = wait_job(client, start(client, body))
    assert repeated['reused_trials'] == 3, repeated
    remaining = runs[-1]
    before = client.get('/api/backtests/' + remaining['id'] + '/exports/market_equity').content
    assert client.delete('/api/backtests/' + runs[0]['id']).status_code == 204
    assert client.delete('/api/datasets/' + dataset['id']).status_code == 204
    assert client.get('/api/backtests/' + remaining['id'] + '/exports/market_equity').content == before
    assert len(list(shared.glob('*.csv'))) == 1


def test_shared_corruption_rejects_chart_download_and_reuse_without_overwrite(client):
    dataset, run = single(client)
    root = client.app.state.runs.root
    path = holding_path(root / run['id'], run['market_benchmark'])
    path.write_bytes(b'controlled corruption')
    base = '/api/backtests/' + run['id']
    assert client.get(base + '/market-benchmark').status_code == 500
    assert client.get(base + '/exports/market_equity').status_code == 500
    body = request_body(dataset)
    body['reuse_results'] = True
    assert client.post('/api/backtests', json=body).status_code == 500
    assert path.read_bytes() == b'controlled corruption'
    assert client.get('/api/backtests').json()['total'] == 1


@pytest.mark.parametrize('change', ['quantity', 'cost', 'capital', 'dates'])
def test_different_holding_inputs_do_not_share(client, change):
    dataset, first = single(client)
    body = request_body(dataset)
    if change == 'quantity': body['market_benchmark']['contracts'] = 2
    if change == 'cost': body['execution_settings'] = {**body['execution_settings'], 'commission_per_contract_per_side': '2'}
    if change == 'capital': body['execution_settings'] = {**body['execution_settings'], 'initial_capital': '20000'}
    if change == 'dates': body['sample_split'] = {**body['sample_split'], 'is_end': '2026-01-05'}
    response = client.post('/api/backtests', json=body)
    assert response.status_code == 201, response.text
    assert response.json()['market_benchmark']['storage']['holding_key'] != first['market_benchmark']['storage']['holding_key']


def legacy_report(client):
    """Build the old saved representation from independently known fixture marks."""
    dataset, run = single(client)
    folder = client.app.state.runs.root / run['id']
    comparison = json.loads((folder / 'market_benchmark.json').read_text())
    # A real pre-daily report has no shared holding artifact yet.
    holding_path(folder, run['market_benchmark']).unlink()
    comparison.pop('storage')
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    times = ['', '2026-01-05T10:00:00Z', '2026-01-05T10:01:00Z', '2026-01-05T10:02:00Z', '2026-01-06T10:00:00Z']
    for i in range(5):
        s, h = EXPECTED['is']['strategy_equity'][i], EXPECTED['is']['holding_equity'][i]
        writer.writerow(dict(bar_number=i, timestamp_utc=times[i], close=['', '101', '90', '110', '110'][i],
                             strategy_equity=s, holding_equity=h, excess_net_pnl=Decimal(s)-Decimal(h),
                             strategy_contracts=int(i in (1, 2)), holding_contracts=int(i in (1, 2, 3))))
    old_csv = output.getvalue().encode()
    (folder / 'market_equity.csv').write_bytes(old_csv)
    comparison['equity_sha256'] = hashlib.sha256(old_csv).hexdigest()
    (folder / 'market_benchmark.json').write_text(json.dumps(comparison, indent=2) + '\n')
    run['market_benchmark'].pop('storage')
    run['market_benchmark'].update(sha256=file_hash(folder / 'market_benchmark.json'), equity_sha256=comparison['equity_sha256'])
    run['artifacts'].pop('strategy_equity_day_csv')
    run['artifacts']['market_equity_csv'] = 'market_equity.csv'
    report = json.loads((folder / 'report.json').read_text())
    report.update(market_benchmark=run['market_benchmark'], artifacts=run['artifacts'])
    (folder / 'report.json').write_text(json.dumps(report))
    (folder / STRATEGY_FILE).unlink()
    with client.app.state.runs.connect() as db:
        db.execute('UPDATE runs SET manifest=? WHERE id=?', (json.dumps(run), run['id']))
    return dataset, run, folder, old_csv


def test_migration_changes_all_comparison_exports_preserves_metrics_and_never_replays(client, tmp_path, monkeypatch):
    dataset, run, folder, old_csv = legacy_report(client)
    before = {name: (folder / name).read_bytes() for name in ('trades.csv', 'equity.csv', 'intratrade_risk.csv')}
    base = '/api/backtests/' + run['id']
    assert client.get(base + '/exports/market_equity').content == old_csv
    monkeypatch.setattr('alphaquest.backtest_api.execute', lambda *a, **k: pytest.fail('Migration must not replay'))
    evidence = tmp_path / 'migration-evidence'
    result = migrate_existing(folder.parent.parent, evidence)
    assert result['converted_reports'] == 1
    assert not (folder / 'market_equity.csv').exists()
    saved = client.get(base).json()
    assert saved['summary'] == run['summary']
    assert saved['market_benchmark']['storage']['granularity'] == 'DAY'
    comparison = client.get(base + '/market-benchmark').json()
    assert comparison['chart']['total'] == 3
    for kind in ('market_benchmark', 'report'):
        data = client.get(base + '/exports/' + kind).json()
        storage = data['storage'] if kind == 'market_benchmark' else data['market_benchmark']['storage']
        assert storage['granularity'] == 'DAY'
    rows = list(csv.DictReader(io.StringIO(client.get(base + '/exports/market_equity').text)))
    assert [Decimal(p['holding_equity']) for p in rows] == [10000, 10194, 10188]
    assert [Decimal(p['strategy_equity']) for p in rows] == [10000, 10168, 10168]
    assert {name: (folder / name).read_bytes() for name in before} == before
    assert (evidence / 'backtests-before.sqlite3').exists()
    repeated = migrate_existing(folder.parent.parent, tmp_path / 'repeat')
    assert repeated['converted_reports'] == 0
    assert repeated['reclaimed_csv_bytes'] == 0


def test_migration_failed_catalogue_update_preserves_original_exports(client, tmp_path):
    _, run, folder, original = legacy_report(client)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    with client.app.state.runs.connect() as db:
        db.execute("CREATE TRIGGER reject_conversion BEFORE UPDATE ON runs BEGIN SELECT RAISE(ABORT,'Controlled migration failure'); END")
    with pytest.raises(Exception, match='Controlled migration failure'):
        migrate_existing(folder.parent.parent, tmp_path / 'failed')
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    assert client.get('/api/backtests/' + run['id'] + '/exports/market_equity').content == original


def test_daily_boundary_tracks_source_dates_across_dst_and_fractional_midnight():
    from alphaquest.market_equity import SourceDate
    date = SourceDate('America/New_York')
    assert [date(t) for t in ['2026-03-08T04:59:00Z', '2026-03-08T05:00:00Z',
                             '2026-03-08T07:00:00Z', '2026-03-09T03:59:59Z',
                             '2026-03-09T04:00:00.123Z']] == [
        '2026-03-07', '2026-03-08', '2026-03-08', '2026-03-08', '2026-03-09']


def test_migration_finishes_cleanup_interrupted_after_publication(client, tmp_path):
    _, run, folder, original = legacy_report(client)
    migrate_existing(folder.parent.parent, tmp_path / 'first-conversion')
    # Recreate the exact state just after catalogue commit but before unlink.
    (folder / 'market_equity.csv').write_bytes(original)
    before = client.get('/api/backtests/' + run['id'] + '/exports/market_equity').content
    result = migrate_existing(folder.parent.parent, tmp_path / 'recovered-conversion')
    assert result['reports'][0]['status'] == 'recovered_cleanup'
    assert result['reclaimed_csv_bytes'] == len(original)
    assert not (folder / 'market_equity.csv').exists()
    assert client.get('/api/backtests/' + run['id'] + '/exports/market_equity').content == before


def test_migration_rejects_active_optimization_before_changing_files(client, tmp_path):
    _, _, folder, original = legacy_report(client)
    with client.app.state.runs.connect() as db:
        db.execute('INSERT INTO optimizations (id, created_at, payload) VALUES (?, ?, ?)',
                   ('a' * 32, '2026-10-30', json.dumps(dict(status='running'))))
    evidence = tmp_path / 'must-not-be-created'
    with pytest.raises(ValueError, match='queued/running'):
        migrate_existing(folder.parent.parent, evidence)
    assert not evidence.exists()
    assert (folder / 'market_equity.csv').read_bytes() == original

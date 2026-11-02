"""Whole-activity deletion, isolation, rollback and durable cleanup retries."""
from pathlib import Path

import pytest

from test_backtest_api import client, save_fixture, body
from test_delete_backtests import files
from test_optimization import optimization_body, start, wait_job


def batch(client, dataset, count=2, reuse=False):
    request = optimization_body(dataset['id'])
    # Deliberately insufficient bars: real saved reports, no trades/prop samples.
    request.update(reuse_results=reuse)
    request['parameter_ranges'] = dict(green_bar_count=dict(start=99, end=99, step=0),
                                     hold_minutes=dict(start=1, end=1, step=0),
                                     contracts=dict(start=1, end=count, step=1 if count > 1 else 0))
    job = wait_job(client, start(client, request))
    assert job['status'] == 'complete', job
    rows = client.get('/api/backtests/batches/' + job['id'] + '/results?limit=1000').json()['items']
    return job, rows


def test_delete_100_reports_across_pages_and_preserve_other_products(client):
    dataset = save_fixture(client)
    other = client.post('/api/backtests', json=body(dataset['id'])).json()
    runs = client.app.state.runs
    original = files(runs.root / other['id'])
    job, rows = batch(client, dataset, 100, reuse=True)
    base = '/api/backtests/batches/' + job['id']
    assert len(rows) == 100
    assert len(client.get(base + '/results').json()['items']) == 50
    prop = rows[0]['prop_analysis']['id']
    analyses = client.app.state.prop_analyses
    prop_files = files(analyses.root / prop)
    assert client.delete(base).json() == dict(deleted_reports=100, shared_reports_kept=0)
    assert client.get('/api/backtests/batches').json()['total'] == 0
    for suffix in ('', '/results', '/exports/results'):
        assert client.get(base + suffix).status_code == 404
    assert client.post(base + '/resume').status_code == 404
    assert client.delete(base).status_code == 404
    assert client.delete('/api/backtests/batches/not-a-uuid').status_code == 422
    assert client.get('/api/backtests').json()['total'] == 1
    for row in rows:
        assert client.get('/api/backtests/' + row['run_id']).status_code == 404
        assert not (runs.root / row['run_id']).exists()
    assert not list(runs.root.glob('.deleted-*'))
    assert files(runs.root / other['id']) == original
    assert files(analyses.root / prop) == prop_files
    assert client.get('/api/prop-analyses/' + prop).status_code == 200
    assert client.get('/api/datasets/' + dataset['id']).status_code == 200
    with runs.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM optimization_trials').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM optimization_trial_cache').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(DISTINCT run_id) FROM run_equity').fetchone()[0] == 1


def test_shared_reused_reports_kept_until_last_activity_deleted(client):
    dataset = save_fixture(client)
    first, rows = batch(client, dataset, reuse=True)
    second, reused = batch(client, dataset, reuse=True)
    assert second['reused_trials'] == 2
    assert {r['run_id'] for r in rows} == {r['run_id'] for r in reused}
    before = {r['run_id']: files(client.app.state.runs.root / r['run_id']) for r in rows}
    assert client.delete('/api/backtests/batches/' + first['id']).json() == dict(deleted_reports=0, shared_reports_kept=2)
    assert client.get('/api/backtests/batches/' + second['id']).status_code == 200
    for id, original in before.items():
        assert client.get('/api/backtests/' + id).status_code == 200
        assert files(client.app.state.runs.root / id) == original
    assert client.delete('/api/optimizations/' + second['id']).json() == dict(deleted_reports=2, shared_reports_kept=0)
    assert client.get('/api/backtests').json()['total'] == 0


def test_previously_deleted_report_and_empty_activity_can_be_deleted(client):
    dataset = save_fixture(client)
    job, rows = batch(client, dataset)
    assert client.delete('/api/backtests/' + rows[0]['run_id']).status_code == 204
    assert client.delete('/api/backtests/batches/' + job['id']).json()['deleted_reports'] == 1
    job, _ = batch(client, dataset, 1)
    store = client.app.state.optimizations
    # Model an interrupted job that failed before publishing its first trial.
    with store.runs.connect() as db:
        db.execute('DELETE FROM optimization_trials WHERE optimization_id=?', (job['id'],))
    store.update(job['id'], status='interrupted', completed_trials=0)
    assert client.delete('/api/backtests/batches/' + job['id']).json()['deleted_reports'] == 0


@pytest.mark.parametrize('status', ['queued', 'running'])
def test_active_activity_rejects_without_removing_anything(client, status):
    dataset = save_fixture(client)
    job, rows = batch(client, dataset)
    client.app.state.optimizations.update(job['id'], status=status)
    try:
        assert client.delete('/api/backtests/batches/' + job['id']).status_code == 409
        assert all(client.get('/api/backtests/' + row['run_id']).status_code == 200 for row in rows)
    finally:
        client.app.state.optimizations.update(job['id'], status='complete')


@pytest.mark.parametrize('busy', ['detail', 'queued', 'running'])
def test_one_busy_source_blocks_whole_activity_before_removing_files(client, busy):
    dataset = save_fixture(client)
    job, rows = batch(client, dataset)
    runs = client.app.state.runs
    originals = {r['run_id']: files(runs.root / r['run_id']) for r in rows}
    id = rows[-1]['run_id']
    analyses = client.app.state.prop_analyses
    if busy == 'detail':runs.claim_detail(id)
    else:
        with analyses.connect() as db:
            db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)', ('e' * 32, 'pending', id, '2026-10-31', busy, 'Controlled source use', None))
    try:
        response = client.delete('/api/backtests/batches/' + job['id'])
        assert response.status_code == 409, response.text
        assert client.get('/api/backtests/batches/' + job['id']).json()['status'] == 'complete'
        for id, original in originals.items():assert files(runs.root / id) == original
        assert client.get('/api/backtests').json()['total'] == 2
    finally:
        runs.release_detail(rows[-1]['run_id'])
        with analyses.connect() as db:db.execute("UPDATE analyses SET status='error' WHERE id=?", ('e' * 32,))


@pytest.mark.parametrize('failure', ['rename', 'sql'])
def test_mid_deletion_failure_restores_every_report_and_activity(client, monkeypatch, failure):
    dataset = save_fixture(client)
    job, rows = batch(client, dataset, reuse=True)
    runs = client.app.state.runs
    originals = {r['run_id']: files(runs.root / r['run_id']) for r in rows}
    last = sorted(originals)[-1]
    if failure == 'rename':
        rename = Path.rename
        def fail(path, target):
            if path == runs.root / last:raise PermissionError('Controlled second rename failure')
            return rename(path, target)
        monkeypatch.setattr(Path, 'rename', fail)
    else:
        with runs.connect() as db:
            db.execute(f"CREATE TRIGGER fail_delete BEFORE DELETE ON runs WHEN OLD.id='{last}' BEGIN SELECT RAISE(ABORT,'Controlled second SQL failure'); END")
    response = client.delete('/api/backtests/batches/' + job['id'])
    assert response.status_code == 500, response.text
    assert client.get('/api/backtests/batches/' + job['id']).json() == job
    assert client.get('/api/backtests').json()['total'] == 2
    for id, original in originals.items():assert files(runs.root / id) == original
    assert not list(runs.root.glob('.deleted-*'))
    with runs.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM optimization_trial_cache').fetchone()[0] == 2


def test_cleanup_failure_retains_activity_and_retry_ids_after_reopening(client, monkeypatch):
    from alphaquest import backtest_runs
    from alphaquest.optimization import OptimizationStore
    dataset = save_fixture(client)
    job, rows = batch(client, dataset)
    runs = client.app.state.runs
    cleanup = backtest_runs.shutil.rmtree
    attempts = []
    def fail_once(path, *args, **kwargs):
        if path.parent == runs.root and not attempts:
            attempts.append(path)
            raise PermissionError('Controlled cleanup failure')
        return cleanup(path, *args, **kwargs)
    monkeypatch.setattr(backtest_runs.shutil, 'rmtree', fail_once)
    base = '/api/backtests/batches/' + job['id']
    response = client.delete(base)
    assert response.status_code == 500 and 'Retry Delete activity' in response.json()['detail']
    pending = client.get(base).json()
    assert pending['status'] == 'deleting'
    assert set(pending['deletion']['run_ids']) == {r['run_id'] for r in rows}
    assert client.post(base + '/resume').status_code == 409
    assert client.get('/api/backtests').json()['total'] == 0
    reopened = OptimizationStore(runs, client.app.state.prop_analyses)
    try:
        assert reopened.delete(job['id']) == dict(deleted_reports=2, shared_reports_kept=0)
    finally:reopened.close()
    assert client.get(base).status_code == 404
    assert not list(runs.root.glob('.deleted-*'))


def test_final_activity_commit_failure_stays_retryable(client):
    dataset = save_fixture(client)
    job, rows = batch(client, dataset)
    runs = client.app.state.runs
    with runs.connect() as db:
        db.execute("CREATE TRIGGER fail_activity_delete BEFORE DELETE ON optimizations BEGIN SELECT RAISE(ABORT,'Controlled final commit failure'); END")
    base = '/api/backtests/batches/' + job['id']
    assert client.delete(base).status_code == 500
    assert client.get(base).json()['status'] == 'deleting'
    assert client.get(base + '/results').json()['total'] == 2
    assert client.get('/api/backtests').json()['total'] == 0
    with runs.connect() as db:db.execute('DROP TRIGGER fail_activity_delete')
    assert client.delete(base).json() == dict(deleted_reports=2, shared_reports_kept=0)
    assert client.get(base).status_code == 404


def test_concurrent_reuse_publishes_shared_reference_before_deletion(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    dataset = save_fixture(client)
    first, rows = batch(client, dataset, 1, reuse=True)
    store = client.app.state.optimizations
    entered, release = Event(), Event()
    record_trial = store._record_trial
    def paused_reference(job_id, row):
        if row['execution'].get('reused'):
            entered.set()
            assert release.wait(10)
        return record_trial(job_id, row)
    monkeypatch.setattr(store, '_record_trial', paused_reference)
    request = optimization_body(dataset['id'])
    request.update(reuse_results=True)
    request['parameter_ranges'] = dict(green_bar_count=dict(start=99, end=99, step=0),
                                     hold_minutes=dict(start=1, end=1, step=0),
                                     contracts=dict(start=1, end=1, step=0))
    second = start(client, request)
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            assert entered.wait(10)
            deletion = pool.submit(client.delete, '/api/backtests/batches/' + first['id'])
        finally:release.set()
        assert deletion.result(timeout=10).json() == dict(deleted_reports=0, shared_reports_kept=1)
    assert wait_job(client, second)['reused_trials'] == 1
    assert client.get('/api/backtests/' + rows[0]['run_id']).status_code == 200


def test_resume_racing_with_delete_rejects_deleted_activity(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    dataset = save_fixture(client)
    job, _ = batch(client, dataset, 1)
    store = client.app.state.optimizations
    store.update(job['id'], status='interrupted')
    entered, release = Event(), Event()
    resume = store.resume
    def paused_resume(id):
        entered.set()
        assert release.wait(10)
        return resume(id)
    monkeypatch.setattr(store, 'resume', paused_resume)
    base = '/api/backtests/batches/' + job['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        response = pool.submit(client.post, base + '/resume')
        try:
            assert entered.wait(10)
            assert client.delete(base).status_code == 200
        finally:release.set()
        assert response.result(timeout=10).status_code == 409
    assert client.get(base).status_code == 404

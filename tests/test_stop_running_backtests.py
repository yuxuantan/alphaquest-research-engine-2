"""A stop request ends active native backtests without losing completed reports."""
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
from uuid import uuid4

from alphaquest.strategies import consecutive_green_hold as sample
from test_optimization import client, optimization_body, start, wait_job
from test_backtest_api import body, save_fixture
from test_campaign_mechanics import create_workflow


def test_stop_running_batch_keeps_completed_trial_and_can_resume(client, monkeypatch):
    dataset = save_fixture(client)
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    def pause_second(self, bar, position):
        if self.parameters.contracts == 2 and not release.is_set():
            entered.set()
            assert release.wait(30)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', pause_second)
    job_id = start(client, optimization_body(dataset['id']) | dict(automatic_prop=False))
    try:
        assert entered.wait(10)
        first = client.get(f'/api/optimizations/{job_id}/results').json()['items']
        assert len(first) == 1
        report_id = first[0]['run_id']
        report = client.get('/api/backtests/' + report_id)
        fingerprint = sha256(report.content).hexdigest()
        history = client.get(f'/api/jobs/backtest_batch/{job_id}').json()
        assert history['status'] == 'running' and history['stop_url'].endswith(f'/{job_id}/cancel')
        response = client.post(history['stop_url'])
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'running' and response.json()['stage'] == 'stopping'
        assert response.json()['stop_requested_at_utc']
        assert client.post(history['stop_url']).json() == response.json()
        assert client.get(f'/api/jobs/backtest_batch/{job_id}').json()['stop_requested_at_utc']
    finally:
        release.set()
    stopped = wait_job(client, job_id)
    assert stopped['status'] == stopped['stage'] == 'cancelled'
    assert stopped['completed_trials'] == 1 and stopped['failed_trials'] == []
    assert stopped['cancelled_at_utc'] == stopped['finished_at_utc']
    assert client.get(f'/api/optimizations/{job_id}/results').json()['items'] == first
    assert sha256(client.get('/api/backtests/' + report_id).content).hexdigest() == fingerprint
    assert client.get('/api/jobs?status=attention').json()['items'][0]['id'] == job_id
    monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', original)
    response = client.post(f'/api/backtests/batches/{job_id}/resume')
    assert response.status_code == 202, response.text
    complete = wait_job(client, job_id)
    assert complete['status'] == 'complete' and complete['completed_trials'] == 3
    assert complete['previous_attempts'][0]['status'] == 'cancelled'
    assert not complete.get('stop_requested_at_utc')
    rows = client.get(f'/api/optimizations/{job_id}/results').json()['items']
    assert rows[:1] == first
    assert [float(row['metrics']['total_net_pnl']) for row in rows] == [13, 26, 39]
    assert client.post(f'/api/backtests/batches/{job_id}/cancel').status_code == 409


def test_stop_mechanic_validation_retains_no_partial_report_and_allows_new_run(client, monkeypatch):
    dataset, body, workflow = create_workflow(client)
    prefix = '/api/campaign-workflows/' + workflow['id']
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    def pause(self, bar, position):
        if not release.is_set():
            entered.set()
            assert release.wait(30)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', pause)
    response = client.post(prefix + '/run?background=true')
    assert response.status_code == 202, response.text
    run_id = response.json()['run_id']
    try:
        assert entered.wait(10)
        history = client.get(f'/api/jobs/mechanic_validation/{run_id}').json()
        assert history['status'] == 'running'
        assert history['stop_url'] == prefix + f'/runs/{run_id}/stop'
        wrong = client.post(prefix + '/runs/00000000-0000-0000-0000-000000000000/stop')
        assert wrong.status_code == 409
        requested = client.post(history['stop_url'])
        assert requested.status_code == 200, requested.text
        assert requested.json()['stop_requested_at_utc']
        assert client.post(history['stop_url']).status_code == 200
    finally:
        release.set()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        saved = client.get(prefix).json()
        if saved['status'] != 'running':
            break
        time.sleep(.02)
    assert saved['status'] == 'cancelled' and saved['review'] is None
    stopped_history = client.get(f'/api/jobs/mechanic_validation/{run_id}').json()
    assert stopped_history['status'] == 'cancelled' and stopped_history['stop_requested_at_utc']
    assert client.get('/api/backtests/' + run_id).status_code == 404
    assert client.get('/api/backtests').json()['total'] == 0
    assert client.get(prefix + '/phases/is_broad').status_code == 409
    monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', original)
    rerun = client.post(prefix + '/run')
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()['status'] == 'review_required' and rerun.json()['run_id'] != run_id
    assert float(rerun.json()['report']['summary']['total_net_pnl']) == 78


def test_stop_one_off_backtest_before_publication(client, monkeypatch):
    dataset = save_fixture(client)
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    def pause(self, bar, position):
        if not release.is_set():
            entered.set()
            assert release.wait(30)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', pause)
    progress_id = uuid4().hex
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, '/api/backtests', params={'progress_id': progress_id},
                             json=body(dataset['id']))
        try:
            assert entered.wait(10)
            stopped = client.post(f'/api/backtests/progress/{progress_id}/stop')
            assert stopped.status_code == 200 and stopped.json()['status'] == 'stopping'
        finally:
            release.set()
        response = future.result(timeout=10)
    assert response.status_code == 409 and 'stopped by user' in response.json()['detail']
    assert client.get('/api/backtests').json()['total'] == 0
    assert client.post(f'/api/backtests/progress/{progress_id}/stop').status_code == 409
    monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', original)
    rerun = client.post('/api/backtests', params={'progress_id': uuid4().hex},
                        json=body(dataset['id']))
    assert rerun.status_code == 201 and rerun.json()['status'] == 'complete'

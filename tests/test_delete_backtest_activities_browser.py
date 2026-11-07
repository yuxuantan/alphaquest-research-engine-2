"""Whole-activity deletion through the existing portal, including all pages."""
import json
import sqlite3
import tarfile
import time

from test_backtests_browser import browser, page, portal, playwright
from test_optimization import optimization_body


def seed_batch(page, portal, count=2, reuse=False):
    dataset = portal['saved']['arithmetic_5m']
    request = optimization_body(dataset['id'])
    request.update(reuse_results=reuse)
    request['parameter_ranges'] = dict(green_bar_count=dict(start=99, end=99, step=0),
                                     hold_minutes=dict(start=1, end=1, step=0),
                                     contracts=dict(start=1, end=count, step=1 if count > 1 else 0))
    response = page.request.post(portal['url'] + '/api/backtests', data=request)
    assert response.status == 202, response.text()
    id = response.json()['id']
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        job = page.request.get(portal['url'] + '/api/backtests/batches/' + id).json()
        if job['status'] == 'complete':break
        assert job['status'] != 'failed', job
        time.sleep(.02)
    assert job['status'] == 'complete', job
    rows = page.request.get(portal['url'] + '/api/backtests/batches/' + id + '/results?limit=1000').json()['items']
    return dataset, job, rows


def test_delete_100_reports_cancel_busy_rejection_confirm_and_reload(page, portal, tmp_path):
    dataset, job, rows = seed_batch(page, portal, 100)
    base = portal['url'] + '/api/backtests/batches/' + job['id']
    page.goto(portal['url'] + '/#backtests/batches/' + job['id'])
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(50)
    page.locator('#optimization-next').click()
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(50)
    playwright.expect(page.locator('#optimization-results tbody tr').first.locator('td[data-column="trial"]')).to_have_text('51')
    # Immutable evidence of the actual reports before exercising deletion.
    runs = portal['app'].state.runs
    with runs.connect() as source, sqlite3.connect(tmp_path / 'catalogue-before.sqlite3') as target:
        source.backup(target)
    with tarfile.open(tmp_path / 'reports-before.tar.gz', 'w:gz') as archive:
        archive.add(runs.root, arcname='backtest_runs')
    (tmp_path / 'activity-before.json').write_text(json.dumps(job, indent=2))
    (tmp_path / 'results-before.json').write_text(json.dumps(rows, indent=2))
    page.screenshot(path=str(tmp_path / 'activity-100-before-delete.png'), full_page=True)
    deletes = []
    dialogs = []
    page.on('request', lambda r: deletes.append(r.url) if r.method == 'DELETE' else None)
    def cancel(dialog):
        dialogs.append(dialog.message)
        dialog.dismiss()
    page.once('dialog', cancel)
    page.locator('#optimization-delete').click()
    assert not deletes
    assert page.request.get(base).status == 200
    assert '100 saved trials' in dialogs[0]
    assert 'every results page' in dialogs[0]
    analyses = portal['app'].state.prop_analyses
    with analyses.connect() as db:
        db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)', ('e' * 32, 'pending', rows[-1]['run_id'], '2026-10-31', 'queued', 'Controlled source use', None))
    page.once('dialog', lambda d: d.accept())
    page.locator('#optimization-delete').click()
    playwright.expect(page.locator('#optimization-delete-status')).to_contain_text('referenced by a research campaign or running prop analysis; it cannot be deleted')
    playwright.expect(page.locator('#optimization-delete')).to_be_enabled()
    assert page.request.get(portal['url'] + '/api/backtests').json()['total'] == 100
    page.screenshot(path=str(tmp_path / 'activity-busy-rejected.png'), full_page=True)
    with analyses.connect() as db:db.execute("UPDATE analyses SET status='error' WHERE id=?", ('e' * 32,))
    page.once('dialog', lambda d: d.accept())
    page.locator('#optimization-delete').click()
    playwright.expect(page).to_have_url(portal['url'] + '/#backtests/batches')
    playwright.expect(page.locator('#optimization-delete-status')).to_contain_text('100 saved reports deleted')
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(0)
    assert len(deletes) == 2
    assert page.request.get(base).status == 404
    for row in rows:
        assert page.request.get(portal['url'] + '/api/backtests/' + row['run_id']).status == 404
    assert page.request.get(portal['url'] + '/api/datasets/' + dataset['id']).status == 200
    assert page.request.get(portal['url'] + '/api/prop-analyses/' + rows[0]['prop_analysis']['id']).status == 200
    page.screenshot(path=str(tmp_path / 'activity-100-deleted.png'), full_page=True)
    page.reload()
    playwright.expect(page.locator('#optimization-status')).to_contain_text('No backtest batches yet')
    assert page.request.get(portal['url'] + '/api/backtests').json()['total'] == 0
    (tmp_path / 'verification.json').write_text(json.dumps(dict(synthetic_fixture=True,
        batch_id=job['id'], report_count=100, report_ids=[r['run_id'] for r in rows],
        expected_reports_deleted=100, observed_reports_remaining=0, activity_status_after_delete=404,
        cancel_sent_no_request=True, busy_rejected_all_reports_preserved=True,
        dataset_preserved=True, prop_report_preserved=True, reload_verified=True,
        confirmation_messages=dialogs), indent=2))


def test_delete_from_activity_list_keeps_shared_reports_and_other_activity(page, portal, tmp_path):
    dataset, first, rows = seed_batch(page, portal, reuse=True)
    _, second, reused = seed_batch(page, portal, reuse=True)
    assert second['reused_trials'] == 2
    page.goto(portal['url'] + '/#backtests/batches')
    button = page.get_by_role('button', name='Delete activity and reports ' + first['id'], exact=True)
    playwright.expect(button).to_be_visible()
    page.once('dialog', lambda d: d.accept())
    button.click()
    playwright.expect(page.locator('#optimization-delete-status')).to_contain_text('2 reports shared with other activities kept')
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(1)
    for row in rows:
        assert page.request.get(portal['url'] + '/api/backtests/' + row['run_id']).status == 200
    assert page.request.get(portal['url'] + '/api/backtests/batches/' + second['id']).status == 200
    page.set_viewport_size(dict(width=390, height=844))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path / 'activity-shared-reports-kept-mobile.png'), full_page=True)
    page.reload()
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(1)


def test_file_cleanup_failure_can_be_retried_from_the_same_activity(page, portal, monkeypatch, tmp_path):
    from alphaquest import backtest_runs
    _, job, rows = seed_batch(page, portal, 1)
    runs = portal['app'].state.runs
    cleanup = backtest_runs.shutil.rmtree
    attempts = []
    def fail_once(path, *args, **kwargs):
        if path.parent == runs.root and not attempts:
            attempts.append(path)
            raise PermissionError('Controlled cleanup failure')
        return cleanup(path, *args, **kwargs)
    monkeypatch.setattr(backtest_runs.shutil, 'rmtree', fail_once)
    page.goto(portal['url'] + '/#backtests/batches/' + job['id'])
    button = page.locator('#optimization-delete')
    playwright.expect(button).to_be_visible()
    page.once('dialog', lambda d: d.accept())
    button.click()
    playwright.expect(page.locator('#optimization-delete-status')).to_contain_text('file cleanup failed')
    playwright.expect(button).to_have_text('Retry Delete activity and reports')
    playwright.expect(button).to_be_enabled()
    assert page.request.get(portal['url'] + '/api/backtests/' + rows[0]['run_id']).status == 404
    page.reload()
    playwright.expect(page.locator('#optimization-status')).to_contain_text('DELETING')
    playwright.expect(button).to_have_text('Retry Delete activity and reports')
    page.screenshot(path=str(tmp_path / 'activity-cleanup-retry.png'), full_page=True)
    page.once('dialog', lambda d: d.accept())
    button.click()
    playwright.expect(page).to_have_url(portal['url'] + '/#backtests/batches')
    playwright.expect(page.locator('#optimization-delete-status')).to_contain_text('1 saved reports deleted')
    assert not list(runs.root.glob('.deleted-*'))


def test_activity_list_last_page_deletion_returns_to_previous_page(page, portal):
    jobs = [seed_batch(page, portal, 1)[1] for _ in range(26)]
    page.goto(portal['url'] + '/#backtests/batches')
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(25)
    page.locator('#optimization-next').click()
    playwright.expect(page.locator('#optimization-page')).to_have_text('26–26 of 26')
    page.once('dialog', lambda d: d.accept())
    page.get_by_role('button', name='Delete activity and reports ' + jobs[0]['id'], exact=True).click()
    playwright.expect(page.locator('#optimization-page')).to_have_text('1–25 of 25')
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(25)
    playwright.expect(page.locator('#optimization-previous')).to_be_disabled()
    assert page.request.get(portal['url'] + '/api/backtests').json()['total'] == 25

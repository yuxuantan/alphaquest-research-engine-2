"""Stop a live batch from Job history and reopen its retained result in the portal."""
import json
from threading import Event

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright, prepare
from test_optimization import optimization_body
from test_campaign_mechanics import create_workflow
from alphaquest.strategies import consecutive_green_hold as sample


def test_stop_running_batch_from_job_history_and_resume(page, portal, tmp_path, monkeypatch):
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    def pause_second(self, bar, position):
        if self.parameters.contracts == 2 and not release.is_set():
            entered.set()
            assert release.wait(90)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', pause_second)
    dataset = portal['saved']['arithmetic_5m']
    with ResearchHTTPClient(base_url=portal['url'], timeout=120) as client:
        response = client.post('/api/optimizations', json=optimization_body(dataset['id']) |
                               dict(automatic_prop=False))
        assert response.status_code == 202, response.text
        job_id = response.json()['id']
        try:
            assert entered.wait(10)
            first = client.get(f'/api/optimizations/{job_id}/results').json()
            assert first['total'] == 1
            first_run_id = first['items'][0]['run_id']
            page.goto(portal['url'] + f'/#jobs/backtest_batch/{job_id}')
            stop = page.get_by_role('button', name='Stop running job', exact=True)
            playwright.expect(stop).to_be_visible()
            page.screenshot(path=str(tmp_path / '01-running.png'), full_page=True)
            page.once('dialog', lambda dialog: dialog.accept())
            stop.click()
            playwright.expect(page.get_by_role('button', name='Stop requested')).to_be_disabled()
            playwright.expect(page.locator('#jobs-detail-content')).to_contain_text('Stopping')
            page.screenshot(path=str(tmp_path / '02-stopping.png'), full_page=True)
        finally:
            release.set()
        playwright.expect(page.locator('#jobs-detail-content')).to_contain_text('Stopped', timeout=15000)
        stopped = client.get(f'/api/optimizations/{job_id}').json()
        assert stopped['status'] == 'cancelled' and stopped['completed_trials'] == 1
        page.screenshot(path=str(tmp_path / '03-stopped.png'), full_page=True)
        page.get_by_role('link', name='Open batch progress / results', exact=True).click()
        playwright.expect(page.locator('#optimization-status')).to_contain_text('CANCELLED')
        playwright.expect(page.locator('#optimization-resume')).to_be_visible()
        monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', original)
        page.locator('#optimization-resume').click()
        playwright.expect(page.locator('#optimization-status')).to_contain_text('COMPLETE', timeout=15000)
        result = client.get(f'/api/optimizations/{job_id}/results').json()
        assert [float(row['metrics']['total_net_pnl']) for row in result['items']] == [13, 26, 39]
        assert result['items'][0]['run_id'] == first_run_id
        page.screenshot(path=str(tmp_path / '04-resumed.png'), full_page=True)
        (tmp_path / 'journey.json').write_text(json.dumps({
            'synthetic': True, 'job_id': job_id, 'completed_before_stop': 1,
            'retained_trial': result['items'][0]['run_id'], 'completed_after_resume': 3,
            'expected_net_pnl': [13, 26, 39],
            'temporary_server': 'Stopped and joined by portal fixture.'}, indent=2) + '\n')


def test_stop_mechanic_on_its_page_and_reopen_history(page, portal, monkeypatch):
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    def pause(self, bar, position):
        if not release.is_set():
            entered.set()
            assert release.wait(90)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', pause)
    with ResearchHTTPClient(base_url=portal['url'], timeout=120) as client:
        _, _, workflow = create_workflow(client)
        page.goto(portal['url'] + f'/#campaigns/workflows/{workflow["id"]}/mechanic_validation')
        try:
            page.locator('#mechanic-run').click()
            assert entered.wait(10)
            stop = page.locator('#mechanic-stop')
            playwright.expect(stop).to_be_visible()
            page.once('dialog', lambda dialog: dialog.accept())
            stop.click()
            playwright.expect(page.locator('#mechanic-stop')).to_be_disabled()
        finally:
            release.set()
        playwright.expect(page.locator('#mechanic-run')).to_be_enabled(timeout=15000)
        saved = client.get(f'/api/campaign-workflows/{workflow["id"]}').json()
        assert saved['status'] == 'cancelled' and saved['stop_requested_at_utc']
        assert client.get('/api/backtests').json()['total'] == 0
        page.get_by_role('link', name='View job progress / history').click()
        playwright.expect(page.locator('#jobs-detail-content')).to_contain_text('Stopped')
        playwright.expect(page.locator('#jobs-detail-content')).to_contain_text('no mechanic validation report was saved')


def test_stop_one_off_backtest_from_its_live_progress(page, portal, monkeypatch):
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    def pause(self, bar, position):
        if not release.is_set():
            entered.set()
            assert release.wait(90)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, 'on_bar', pause)
    prepare(page, portal)
    try:
        page.locator('#start-backtest').click()
        assert entered.wait(10)
        stop = page.locator('#backtest-stop')
        playwright.expect(stop).to_be_visible()
        page.once('dialog', lambda dialog: dialog.accept())
        stop.click()
        playwright.expect(stop).to_have_text('Stop requested')
    finally:
        release.set()
    playwright.expect(page.locator('#backtest-error')).to_contain_text('Backtest stopped', timeout=15000)
    playwright.expect(page.locator('#backtest-stop')).to_be_hidden()
    assert page.request.get(portal['url'] + '/api/backtests').json()['total'] == 0

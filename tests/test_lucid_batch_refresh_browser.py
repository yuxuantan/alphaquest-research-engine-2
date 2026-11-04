"""Refresh old N/A trials in the existing batch UI, preserving source outputs."""
import csv
import io
import json
from threading import Event

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal,playwright
from test_lucid_batch_refresh import historical_batch


def test_batch_refresh_pending_reload_sort_download_and_report_source_check(page,portal,monkeypatch,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        base,rows=historical_batch(client,monkeypatch)
        original=client.get('/api/prop-analyses/'+rows[0]['prop_companions'][0]['id']+'/downloads/report.json').content
        source_trades=client.get('/api/backtests/'+rows[0]['run_id']+'/exports/trades').content
    from alphaquest.prop import store as analysis_module
    run=analysis_module.run_analysis;entered=Event();release=Event()
    def paused(*args,**kwargs):
        entered.set();assert release.wait(30)
        return run(*args,**kwargs)
    monkeypatch.setattr(analysis_module,'run_analysis',paused)
    posts=[]
    page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    url=portal['url']+'/#backtests/batches/'+base.rsplit('/',1)[-1]
    page.goto(url)
    playwright.expect(page.locator('#optimization-lucid-status')).to_contain_text('0 / 1 Lucid values available')
    cell=page.locator('td[data-column="lucid_historical_net"]')
    playwright.expect(cell).to_contain_text('Joint sizing is unavailable')
    page.screenshot(path=str(tmp_path/'01-original-na.png'),full_page=True)
    try:
        with page.expect_response(lambda r:r.url.endswith('/lucid-refresh') and r.request.method=='POST') as response:
            page.locator('#optimization-lucid-run').click()
        assert response.value.status==202,response.value.text()
        assert response.value.json()['queued']==1
        assert entered.wait(5)
        playwright.expect(page.locator('#optimization-lucid-status')).to_contain_text('1 pending')
        playwright.expect(cell).to_contain_text('Lucid analysis pending')
        page.reload()
        playwright.expect(page.locator('#optimization-lucid-status')).to_contain_text('1 pending')
        with page.expect_response(lambda r:r.url.endswith('/lucid-refresh') and r.request.method=='POST') as duplicate:
            page.locator('#optimization-lucid-run').click()
        assert duplicate.value.json()['already_pending']==1
        assert duplicate.value.json()['queued']==0
        page.screenshot(path=str(tmp_path/'02-durable-pending.png'),full_page=True)
    finally:release.set()
    playwright.expect(page.locator('#optimization-lucid-status')).to_contain_text('1 / 1 Lucid values available',timeout=180000)
    playwright.expect(cell).to_contain_text('$17,758')
    playwright.expect(cell.locator('small')).to_have_count(0)
    page.locator('th[data-column="lucid_historical_net"] button').click()
    page.locator('th[data-column="lucid_historical_net"] button').click()
    playwright.expect(page.locator('th[data-column="lucid_historical_net"]')).to_have_attribute('aria-sort','descending')
    page.screenshot(path=str(tmp_path/'03-updated-batch.png'),full_page=True)
    with page.expect_download() as download:page.locator('#optimization-download').click()
    download.value.save_as(tmp_path/'updated-results.csv')
    current=list(csv.DictReader(io.StringIO((tmp_path/'updated-results.csv').read_text())))
    assert current[0]['lucid_historical_net']=='88792'
    with page.expect_download() as download:page.locator('#optimization-original-download').click()
    download.value.save_as(tmp_path/'original-results.csv')
    assert list(csv.DictReader(io.StringIO((tmp_path/'original-results.csv').read_text())))[0]['lucid_historical_net']==''
    id=current[0]['lucid_analysis_id']
    cell.locator('a').click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
    assert page.url.endswith(id)
    page.get_by_role('tab',name='Historical replay',exact=True).click()
    playwright.expect(page.locator('#prop-view-history')).to_contain_text('$88,792')
    page.get_by_role('link',name='Configure new analysis',exact=True).click()
    playwright.expect(page.locator('#prop-model')).to_have_value('1')
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    page.locator('#prop-run').click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
    assert page.url.endswith(id)
    page.goto(url)
    playwright.expect(cell).to_contain_text('$17,758')
    posts.clear();page.reload()
    playwright.expect(cell).to_contain_text('$17,758')
    assert not posts
    assert page.request.get(portal['url']+'/api/prop-analyses/'+rows[0]['prop_companions'][0]['id']+'/downloads/report.json').body()==original
    assert page.request.get(portal['url']+'/api/backtests/'+rows[0]['run_id']+'/exports/trades').body()==source_trades
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,analysis_id=id,source_id=rows[0]['run_id'],
        expected_historical_net=88792,observed_historical_net=int(current[0]['lucid_historical_net']),
        original_csv_preserved=True,old_report_preserved=True,source_trades_preserved=True,
        pending_survives_reload=True,duplicate_did_not_queue=True,reload_read_only=True),indent=2))

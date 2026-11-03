"""Normal batch UI refreshes both providers without changing trial snapshots."""
import csv
import io
import json
from threading import Event

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal,playwright
from test_batch_prop_refresh import historical_accounts


def test_all_prop_refresh_pending_reload_download_and_durable_results(page,portal,monkeypatch,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        base,old=historical_accounts(client,monkeypatch)
        originals={item['id']:client.get('/api/prop-analyses/'+item['id']+'/downloads/report.json').content
            for item in [old[0]['prop_analysis'],old[0]['prop_companions'][0]]}
    from alphaquest.prop import store as module
    run=module.run_analysis;entered=Event();release=Event()
    def paused(*args,**kwargs):
        entered.set();assert release.wait(30)
        return run(*args,**kwargs)
    monkeypatch.setattr(module,'run_analysis',paused)
    page.goto(portal['url']+'/#backtests/batches/'+base.rsplit('/',1)[-1])
    playwright.expect(page.locator('th[data-column="historical_net"]')).to_contain_text('Apex historical net /slot')
    playwright.expect(page.locator('th[data-column="lucid_historical_net"]')).to_contain_text('Lucid historical net / slot')
    playwright.expect(page.locator('th[data-column="max_drawdown_duration_seconds"]')).to_contain_text('trading days')
    assert page.locator('td[data-column="max_drawdown_pct"]').inner_text().endswith('.00')
    playwright.expect(page.locator('td[data-column="max_drawdown_duration_seconds"]')).to_have_text('0')
    status=page.locator('#optimization-prop-status')
    playwright.expect(status).to_contain_text('Apex: 0 / 1 available')
    playwright.expect(status).to_contain_text('Lucid: 0 / 1 available')
    page.screenshot(path=str(tmp_path/'01-original-na.png'),full_page=True)
    try:
        with page.expect_response(lambda r:r.url.endswith('/prop-refresh') and r.request.method=='POST') as response:
            page.locator('#optimization-prop-run').click()
        assert response.value.status==202 and response.value.json()['queued']==2
        assert entered.wait(5)
        playwright.expect(page.locator('td[data-column="historical_net"]')).to_contain_text('Apex analysis pending')
        playwright.expect(page.locator('td[data-column="lucid_historical_net"]')).to_contain_text('Lucid analysis pending')
        page.reload();playwright.expect(status).to_contain_text('1 pending')
        with page.expect_response(lambda r:r.url.endswith('/prop-refresh') and r.request.method=='POST') as duplicate:
            page.locator('#optimization-prop-run').click()
        assert duplicate.value.json()['queued']==0 and duplicate.value.json()['already_pending']==2
        page.screenshot(path=str(tmp_path/'02-pending-both-accounts.png'),full_page=True)
    finally:release.set()
    playwright.expect(status).to_contain_text('Apex: 1 / 1 available',timeout=180000)
    playwright.expect(status).to_contain_text('Lucid: 1 / 1 available',timeout=180000)
    apex=page.locator('td[data-column="historical_net"]');lucid=page.locator('td[data-column="lucid_historical_net"]')
    playwright.expect(apex).to_contain_text('$22,644');playwright.expect(apex).to_contain_text('Updated Apex analysis')
    playwright.expect(lucid).to_contain_text('$17,758')
    for column in ['historical_net','lucid_historical_net']:
        page.locator(f'th[data-column="{column}"] button').click()
        page.locator(f'th[data-column="{column}"] button').click()
        playwright.expect(page.locator(f'th[data-column="{column}"]')).to_have_attribute('aria-sort','descending')
    page.screenshot(path=str(tmp_path/'03-updated-both-accounts.png'),full_page=True)
    for selector,name in [('#optimization-download','updated.csv'),('#optimization-original-download','original.csv')]:
        with page.expect_download() as download:page.locator(selector).click()
        download.value.save_as(tmp_path/name)
    current=list(csv.DictReader(io.StringIO((tmp_path/'updated.csv').read_text())))[0]
    original=list(csv.DictReader(io.StringIO((tmp_path/'original.csv').read_text())))[0]
    assert current['historical_net']=='452880' and current['lucid_historical_net']=='88792'
    assert original['historical_net']==original['lucid_historical_net']==''
    assert current['prop_original_analysis_id']==old[0]['prop_analysis']['id']
    apex.locator('a').click();playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert page.url.endswith(current['prop_analysis_id'])
    page.get_by_role('tab',name='Historical replay',exact=True).click()
    playwright.expect(page.locator('#prop-view-history')).to_contain_text('$452,880')
    for id,raw in originals.items():assert page.request.get(portal['url']+'/api/prop-analyses/'+id+'/downloads/report.json').body()==raw
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,source_id=old[0]['run_id'],
        apex_id=current['prop_analysis_id'],lucid_id=current['lucid_analysis_id'],
        expected_apex=452880,expected_lucid=88792,pending_survives_reload=True,
        duplicate_queues=0,original_values_preserved=True,original_reports_preserved=True),indent=2))

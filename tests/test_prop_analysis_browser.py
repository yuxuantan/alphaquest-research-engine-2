import json
import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_prop_analysis_api import backtest,export_for


def test_local_report_reload_reopen_and_download(page,portal,tmp_path):
    from types import SimpleNamespace
    with httpx.Client(base_url=portal['url']) as client:r=backtest(client)
    adapter=SimpleNamespace(app=portal['app'])
    path=export_for(adapter,r,tmp_path)
    page.goto(portal['url']+f"/#backtests/report/{r['id']}");page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    page.locator('#prop-trade-file').fill(str(path));page.locator('#prop-export-timezone').select_option('UTC')
    page.locator('#prop-check').click();playwright.expect(page.locator('#prop-run')).to_be_enabled()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('52.00')
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=20000)
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('AlphaQuest local')
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('52.00')
    with page.expect_download() as result:page.get_by_role('link',name='report.json ↓',exact=True).click()
    destination=tmp_path/'download.json';result.value.save_as(destination);data=json.loads(destination.read_text());assert data['format_version']==3
    posts=[];page.on('request',lambda req:posts.append(req.url) if req.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=10000);assert not posts
    page.locator('#prop-back').click();page.locator('#report-prop-setup').click();page.locator('#prop-saved a').first.click()
    playwright.expect(page.locator('#prop-report')).to_be_visible();assert not posts

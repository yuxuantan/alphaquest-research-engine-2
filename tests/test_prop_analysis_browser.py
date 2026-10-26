import json
import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_prop_analysis_api import backtest


def test_report_to_analysis_reload_reopen_download(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url']) as client:r=backtest(client)
    page.goto(portal['url']+f"/#backtests/report/{r['id']}")
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    page.locator('#prop-sims').fill('32')
    page.locator('#prop-increment').select_option('1')
    page.locator('#prop-overrides').fill(json.dumps(dict(OOS_START_DATE=None,VALIDATION_SPLIT=0)))
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('13.00')
    page.locator('#prop-run').click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=20000)
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('average_net')
    with page.expect_download() as result:page.get_by_role('link',name='report.json ↓',exact=True).click()
    destination=tmp_path/'download.json';result.value.save_as(destination);data=json.loads(destination.read_text())
    assert data['statistics']['average_net']==13
    posts=[];page.on('request',lambda req:posts.append(req.url) if req.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=10000)
    assert not posts
    page.locator('#prop-back').click();page.locator('#report-prop-setup').click()
    page.locator('#prop-saved a').first.click();playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert not posts

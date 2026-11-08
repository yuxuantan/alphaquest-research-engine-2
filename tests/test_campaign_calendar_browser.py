"""Saved backtest → automatically dated campaign → durable report/downloads."""
from prop_setup_helpers import open_prop_task
import json
from hashlib import sha256

import httpx
import pytest

from test_backtests_browser import browser, page, portal, playwright
from test_campaign_calendar import saved_grid_source


@pytest.mark.parametrize('phase,end', [('evaluation','2049-12-30'),('funded','2040-01-16')])
def test_automatic_calendar_from_saved_report(page, portal, tmp_path, phase, end):
    with httpx.Client(base_url=portal['url'], timeout=300) as client:
        source, job_id = saved_grid_source(client)
    page.goto(portal['url']+'/#backtests/report/'+source['id'])
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'compare', close_outer=True)
    page.locator('#campaign-new-'+phase).click()
    assert page.locator('#campaign-calendar-end').count() == 0
    playwright.expect(page.locator('#campaign-form')).to_contain_text('Calendar coverage is calculated automatically')
    page.locator('#campaign-start').fill('2040-01-02')
    page.locator('#campaign-paths').fill('8')
    page.locator('#campaign-block').select_option('1')
    page.locator('.campaign-sizes').fill('10' if phase=='evaluation' else '3')
    if phase == 'evaluation':
        page.locator('#campaign-chains').fill('8')
    else:
        # A horizon edit must rederive coverage and invalidate the prior check.
        page.locator('#campaign-horizon').fill('8')
        page.locator('#campaign-delay').fill('4')
        page.locator('#campaign-check').click()
        playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
        playwright.expect(page.locator('#campaign-status')).to_contain_text('2040-01-10')
        page.locator('#campaign-horizon').fill('14')
        playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    assert page.locator('#campaign-is-start').input_value() == '2026-01-05'
    assert page.locator('#campaign-is-end').input_value() == '2026-01-14'
    with page.expect_request(lambda r:r.method=='POST' and r.url.endswith('/api/research-campaigns')) as sent:
        page.locator('#campaign-check').click()
    request = sent.value.post_data_json
    assert request['search_settings']['calendar'] == dict(start_dates=['2040-01-02'])
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    playwright.expect(page.locator('#campaign-status')).to_contain_text(end)
    page.screenshot(path=str(tmp_path/'checked-auto-calendar.png'), full_page=True)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign',timeout=30000)
    id = page.url.rsplit('/',1)[-1]
    prefix = portal['url']+'/api/research-campaigns/'+id
    campaign = page.request.get(prefix).json()
    assert campaign['manifest']['request']['calendar']['coverage_end'] == end
    analysis_id = campaign['analysis_id']
    report = page.request.get(portal['url']+f'/api/prop-analyses/{analysis_id}/downloads/report.json').json()
    assert report['request']['calendar']['coverage_end'] == end
    row = report['calculations']['candidates'][0]
    if phase == 'evaluation':
        assert row['metrics']['cost_per_funded'] == 70
        assert row['metrics']['expected_calendar_days_to_funded'] == 2
        assert {p['funded_date'] for p in row['paths']} == {'2040-01-04'}
    else:
        assert row['metrics']['expected_payouts'] == row['metrics']['expected_pending_cash'] == 1500
        assert row['metrics']['expected_gross_account_deductions'] == 3000
        for path in row['paths']:
            assert [e['request_date'] for e in path['payout_events']] == ['2040-01-06','2040-01-13']
            assert [e['receipt_date'] for e in path['payout_events']] == ['2040-01-10','2040-01-17']
    page.screenshot(path=str(tmp_path/'saved-auto-calendar-results.png'), full_page=True)
    snapshots = {}
    for kind in ('campaign.json','source_checks.json','results.json','results.csv','report.json','analysis.zip'):
        response = page.request.get(prefix+'/exports/'+kind)
        assert response.ok
        snapshots[kind] = response.body()
        (tmp_path/kind).write_bytes(response.body())
    posts = []
    page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.reload()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign')
    assert posts == []
    for kind,data in snapshots.items():
        assert page.request.get(prefix+'/exports/'+kind).body() == data
    (tmp_path/'workflow.json').write_text(json.dumps(dict(phase=phase,source_id=source['id'],grid_id=job_id,
        campaign_id=id,analysis_id=analysis_id,scenario_start='2040-01-02',expected_coverage_end=end,
        submitted_calendar=request['search_settings']['calendar'],reopen_posts=posts,
        downloads={name:sha256(data).hexdigest() for name,data in snapshots.items()},
        synthetic=True,server='Stopped by portal fixture cleanup.'),indent=2))

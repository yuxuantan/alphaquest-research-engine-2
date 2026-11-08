"""Saved report → valid common IS default → checks, run and durable downloads."""
from prop_setup_helpers import open_prop_task
from hashlib import sha256
import json

import httpx
import pytest

from test_backtests_browser import browser,page,portal,playwright
from test_campaign_window import saved_window_grid


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_observed_is_default_in_product(page,portal,tmp_path,phase):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        records,job,rows=saved_window_grid(client)
    page.goto(portal['url']+'/#backtests/report/'+records[0]['id'])
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'compare', close_outer=True)
    page.locator('#campaign-new-'+phase).click()
    first=page.locator('#campaign-is-start');last=page.locator('#campaign-is-end')
    playwright.expect(first).to_have_value('2021-01-04')
    playwright.expect(last).to_have_value('2021-01-15')
    playwright.expect(page.locator('#campaign-window-status')).to_contain_text('derived from all selected sources')
    page.screenshot(path=str(tmp_path/'observed-default.png'),full_page=True)
    # Manual narrowing survives other research-setting edits, and resets explicitly.
    first.fill('2021-01-05');last.fill('2021-01-14')
    page.locator('#campaign-paths').fill('8');page.locator('#campaign-block').select_option('1')
    assert first.input_value()=='2021-01-05' and last.input_value()=='2021-01-14'
    playwright.expect(page.locator('#campaign-window-status')).to_contain_text('Custom IS window')
    page.screenshot(path=str(tmp_path/'intentional-override.png'),full_page=True)
    page.locator('#campaign-window-reset').click()
    playwright.expect(first).to_have_value('2021-01-04')
    playwright.expect(last).to_have_value('2021-01-15')
    # Adding/removing a selected source rederives common coverage.
    page.locator('#campaign-add-source').click()
    playwright.expect(page.locator('#campaign-check')).to_be_disabled()
    page.locator('.campaign-source-search').nth(1).fill(records[1]['id'])
    playwright.expect(page.locator('.campaign-source-status').nth(1)).to_contain_text('1 of 1')
    page.locator('.campaign-reference').nth(1).select_option(records[1]['id'])
    playwright.expect(page.locator('#campaign-check')).to_be_enabled()
    page.locator('#campaign-sources fieldset').nth(1).get_by_role('button',name='Remove source').click()
    playwright.expect(page.locator('#campaign-check')).to_be_enabled()
    # Explicit job subsets use the saved coverage even when first/last sessions
    # have no trades. A new trial list must refresh its metadata before checking.
    page.locator('.campaign-kind').select_option('optimization_id')
    page.locator('.campaign-source-search').fill(job['id'])
    playwright.expect(page.locator('.campaign-source-status')).to_contain_text('1 of 1')
    page.locator('.campaign-reference').select_option(job['id'])
    playwright.expect(page.locator('#campaign-check')).to_be_enabled()
    trial={r['run_id']:r['trial'] for r in rows}
    with page.expect_response(lambda r:r.url.endswith('/api/research-campaigns/source-window')) as secondary:
        page.locator('.campaign-trials').fill(str(trial[records[1]['id']]))
    metadata=secondary.value.json()
    assert [r['source_backtest_id'] for r in metadata['sources']]==[records[1]['id']]
    playwright.expect(first).to_have_value('2021-01-04')
    playwright.expect(last).to_have_value('2021-01-15')
    page.screenshot(path=str(tmp_path/'zero-trade-edge-source.png'),full_page=True)
    with page.expect_response(lambda r:r.url.endswith('/api/research-campaigns/source-window')):
        page.locator('.campaign-trials').fill(str(trial[records[0]['id']]))
    playwright.expect(page.locator('#campaign-check')).to_be_enabled()
    # Outside coverage stays invalid; defaults do not silently clip explicit edits.
    first.fill('2021-01-01')
    assert first.evaluate('(input)=>input.validity.rangeUnderflow')
    playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    page.locator('#campaign-window-reset').click()
    playwright.expect(first).to_have_value('2021-01-04')
    page.locator('#campaign-start').fill('2021-01-04')
    page.locator('.campaign-sizes').fill('10' if phase=='evaluation' else '3')
    if phase=='evaluation':page.locator('#campaign-chains').fill('8')
    else:
        page.locator('#campaign-horizon').fill('14');page.locator('#campaign-delay').fill('4')
    with page.expect_request(lambda r:r.method=='POST' and r.url.endswith('/api/research-campaigns')) as sent:
        page.locator('#campaign-check').click()
    assert sent.value.post_data_json['is_window']==dict(first_session='2021-01-04',last_session='2021-01-15')
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    page.screenshot(path=str(tmp_path/'checked-valid-window.png'),full_page=True)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign',timeout=30000)
    id=page.url.rsplit('/',1)[-1];prefix=portal['url']+'/api/research-campaigns/'+id
    campaign=page.request.get(prefix).json();snapshots={}
    for kind in ('campaign.json','source_checks.json','results.json','results.csv','report.json','analysis.zip'):
        response=page.request.get(prefix+'/exports/'+kind);assert response.ok
        snapshots[kind]=response.body();(tmp_path/kind).write_bytes(response.body())
    report=json.loads(snapshots['report.json']);row=report['calculations']['candidates'][0]
    assert row['manifest']['source']['profile_research_period']['weekdays']==10
    if phase=='evaluation':assert row['metrics']['cost_per_funded']==70 and row['metrics']['expected_calendar_days_to_funded']==2
    else:assert row['metrics']['expected_payouts']==row['metrics']['expected_pending_cash']==1500
    page.screenshot(path=str(tmp_path/'saved-window-results.png'),full_page=True)
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign')
    assert posts==[]
    for kind,data in snapshots.items():assert page.request.get(prefix+'/exports/'+kind).body()==data
    (tmp_path/'window-metadata.json').write_text(json.dumps(metadata,indent=2))
    (tmp_path/'workflow.json').write_text(json.dumps(dict(synthetic=True,phase=phase,grid_id=job['id'],
        source_id=records[0]['id'],zero_edge_source_id=records[1]['id'],campaign_id=id,analysis_id=campaign['analysis_id'],
        expected_is_window=dict(first_session='2021-01-04',last_session='2021-01-15'),reopen_posts=posts,
        downloads={name:sha256(data).hexdigest() for name,data in snapshots.items()},
        server='Stopped by portal fixture cleanup.'),indent=2))

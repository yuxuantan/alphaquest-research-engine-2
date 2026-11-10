"""Opt-out research grid → existing report → phase campaign → saved downloads."""
from prop_setup_helpers import open_prop_task
import json
import re

import httpx
import pytest

from research_fixtures import declare_in_form
from test_backtests_browser import browser, page, portal, playwright, set_parameter
from test_prop_phases import phase_history


def test_single_combination_opt_out_uses_normal_batch(page, portal):
    from test_backtests_browser import prepare
    prepare(page, portal)
    page.locator('#optimization-automatic-prop').uncheck()
    page.locator('#start-backtest').click()
    playwright.expect(page).to_have_url(re.compile(r'/#backtests/batches/[a-f0-9]{32}$'))
    playwright.expect(page.locator('#optimization-status')).to_contain_text('COMPLETE', timeout=30000)
    id = page.url.rsplit('/', 1)[-1]
    job = page.request.get(portal['url']+'/api/optimizations/'+id).json()
    assert job['completed_trials'] == job['total_trials'] == 1
    assert job['default_prop_profile'] is None
    page.locator('#optimization-results tbody td[data-column="run_id"] a').click()
    playwright.expect(page.locator('#report-summary')).to_contain_text('26.00')


@pytest.mark.parametrize('phase', ['evaluation', 'funded'])
def test_opt_out_grid_to_independent_campaign(page, portal, tmp_path, phase):
    with httpx.Client(base_url=portal['url']) as client:
        response = client.post('/api/datasets', params=dict(filename='SYNTHETIC-cleanup.csv',
            name='SYNTHETIC architecture qualification', source_timezone='UTC',
            tick_size='.25', point_value='20', symbol='NQ'), content=phase_history(24))
        assert response.status_code == 201, response.text
        dataset = response.json()
    page.goto(portal['url']+'/#optimizations')
    playwright.expect(page.locator('#optimization-ranges tr')).to_have_count(3)
    page.locator('#backtest-dataset').select_option(dataset['id'])
    set_parameter(page, 'green_bar_count', '1')
    page.get_by_label('Green bar count end', exact=True).fill('2')
    set_parameter(page, 'hold_minutes', '1')
    set_parameter(page, 'contracts', '1')
    page.locator('#backtest-slippage-ticks').fill('0')
    page.locator('#backtest-commission').fill('0')
    page.locator('#optimization-workers').select_option('1')
    playwright.expect(page.locator('#optimization-automatic-prop')).to_be_checked()
    page.locator('#optimization-automatic-prop').uncheck()
    declare_in_form(page, dict(is_start='2026-01-05', is_end='2026-01-14',
        oos_start='2026-01-15', oos_end='2026-02-05'))
    page.screenshot(path=str(tmp_path/'grid-configuration.png'), full_page=True)
    page.locator('#start-backtest').click()
    playwright.expect(page).to_have_url(re.compile(r'/#backtests/batches/[a-f0-9]{32}$'))
    playwright.expect(page.locator('#optimization-status')).to_contain_text('COMPLETE', timeout=30000)
    job_id = page.url.rsplit('/', 1)[-1]
    job = page.request.get(portal['url']+'/api/optimizations/'+job_id).json()
    assert job['request']['automatic_prop'] is False and job['default_prop_profile'] is None
    rows = page.request.get(portal['url']+f'/api/optimizations/{job_id}/results').json()['items']
    assert len(rows) == 2 and all('prop_analysis' not in row for row in rows)
    page.locator('#optimization-results tbody td[data-column="run_id"] a').first.click()
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'compare', close_outer=True)
    page.locator('#campaign-new-'+phase).click()
    page.locator('#campaign-paths').fill('8')
    page.locator('#campaign-block').select_option('1')
    if phase == 'evaluation':
        page.locator('#campaign-chains').fill('8')
    else:
        page.locator('#campaign-horizon').fill('14')
        page.locator('#campaign-delay').fill('4')
    page.locator('.campaign-kind').select_option('optimization_id')
    page.locator('.campaign-source-search').fill(job_id)
    playwright.expect(page.locator('.campaign-source-status')).to_contain_text('1 of 1')
    page.locator('.campaign-reference').select_option(job_id)
    page.locator('.campaign-sizes').fill('3,10' if phase == 'evaluation' else '1,3')
    assert page.locator('#campaign-budget').count() == 0
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    playwright.expect(page.locator('#campaign-count')).to_contain_text('4 candidates selected')
    page.screenshot(path=str(tmp_path/'source-check.png'), full_page=True)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign', timeout=30000)
    id = page.url.rsplit('/', 1)[-1]
    prefix = portal['url']+'/api/research-campaigns/'+id
    result = page.request.get(prefix+'/exports/results.json').json()
    assert len(result['candidates']) == 4
    if phase == 'evaluation':
        assert sorted((r['metrics']['cost_per_funded'], r['metrics']['expected_calendar_days_to_funded'])
            for r in result['candidates']) == [(70,2),(70,4),(70,7),(70,15)]
    else:
        assert sorted(r['metrics']['expected_payouts'] for r in result['candidates']) == [0,0,0,1500]
    page.screenshot(path=str(tmp_path/'campaign-results.png'), full_page=True)
    campaign = page.request.get(prefix).json()
    for kind in ('campaign.json', 'results.json', 'results.csv', 'source_checks.json', 'analysis.zip'):
        response = page.request.get(prefix+'/exports/'+kind)
        assert response.ok
        (tmp_path/kind).write_bytes(response.body())
    posts = []
    page.on('request', lambda r: posts.append(r.url) if r.method == 'POST' else None)
    page.reload()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign')
    assert posts == []
    assert page.request.get(prefix+'/exports/results.json').json() == result
    (tmp_path/'grid.json').write_text(json.dumps(job, indent=2))
    (tmp_path/'workflow.json').write_text(json.dumps(dict(phase=phase, grid_id=job_id,
        campaign_id=id, analysis_id=campaign['analysis_id'], source_ids=[r['run_id'] for r in rows],
        reopen_posts=posts, synthetic=True, server='Stopped by portal fixture cleanup.'), indent=2))

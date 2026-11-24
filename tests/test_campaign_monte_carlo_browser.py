"""Normal OOS -> Monte Carlo -> history -> durable downloads portal journey."""
import csv
import json
import os
from pathlib import Path
import shutil
from hashlib import sha256

import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_campaign_oos import frozen_workflow, run_oos
from monte_carlo_fixtures import legacy_assessment


def test_final_sanity_check_runs_in_oos_and_reopens_from_job_history(page,portal,tmp_path,monkeypatch):
    with httpx.Client(base_url=portal['url'],timeout=60) as client:
        dataset,workflow=frozen_workflow(client)
        oos,_=run_oos(client,workflow)
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/oos?job={oos["id"]}')
    playwright.expect(page.locator('#monte-carlo-rules li')).to_have_count(2)
    playwright.expect(page.locator('#monte-carlo-run')).to_be_enabled()
    page.locator('#monte-carlo-run').click()
    # Leaving the launching page does not own or cancel the background task.
    page.get_by_role('link',name='Job history',exact=True).click()
    page.locator('#jobs-filter-kind').select_option('monte_carlo')
    playwright.expect(page.locator('#jobs-rows tr')).to_have_count(1,timeout=30000)
    page.locator('#jobs-rows td:last-child a').click()
    page.get_by_role('link',name='Open final Monte Carlo check',exact=True).click()
    playwright.expect(page.locator('#monte-carlo-status')).to_contain_text('COMPLETE · 4 / 4',timeout=30000)
    playwright.expect(page.locator('#monte-carlo-table tbody tr')).to_have_count(8)
    playwright.expect(page.locator('#monte-carlo-run')).to_be_disabled()
    playwright.expect(page.locator('#monte-carlo-panel')).to_contain_text('not another holdout')
    for column in ('mean_net','median_net','is_mtm_dd','oos_mtm_dd'):
        assert page.locator(f'#monte-carlo-table th[data-column="{column}"]').count()==1
    for column in ('median_dd','p95_dd','historical_dd','dd_multiple','dd_percentile'):
        assert page.locator(f'#monte-carlo-table th[data-column="{column}"]').count()==0
    playwright.expect(page.locator('#monte-carlo-drawdown-table')).to_be_hidden()
    page.locator('#monte-carlo-drawdown-details summary').click()
    playwright.expect(page.locator('#monte-carlo-drawdown-table')).to_be_visible()
    playwright.expect(page.locator('#monte-carlo-drawdown-table tbody tr')).to_have_count(8)
    playwright.expect(page.locator('#monte-carlo-drawdown-details')).to_contain_text('not the stitched every-bar MTM')
    for column in ('median_dd','dd_percentile'):
        assert page.locator(f'#monte-carlo-drawdown-table th[data-column="{column}"]').count()==1
    page.locator('#monte-carlo-drawdown-details summary').click()
    assert page.locator('#monte-carlo-table th').filter(has_text='DD limit').count()==0
    playwright.expect(page.locator('#monte-carlo-diagnostics')).to_contain_text('not pass/fail gates')
    # Existing v1 populations can be assessed under v2, with byte-identical paths.
    base=portal['url']+f'/api/campaign-workflows/{workflow["id"]}/oos/monte-carlo'
    old_id=page.request.get(base+'?job='+oos['id']).json()['job']['id']
    store=portal['app'].state.prop_analyses
    legacy=legacy_assessment(store,old_id)
    old_hashes={p.name:sha256(p.read_bytes()).hexdigest() for p in (store.root/old_id).iterdir() if p.is_file()}
    from alphaquest import campaign_monte_carlo as mc
    monkeypatch.setattr(mc,'assess',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Saved paths must not be resimulated')))
    page.reload()
    playwright.expect(page.locator('#monte-carlo-run')).to_have_text('Apply updated policy to saved paths')
    playwright.expect(page.locator('#monte-carlo-status')).to_contain_text('historical policy')
    page.locator('#monte-carlo-run').click()
    playwright.expect(page.locator('#monte-carlo-results')).to_contain_text('No new simulation was run.',timeout=30000)
    playwright.expect(page.locator('#monte-carlo-status')).to_contain_text('COMPLETE · 4 / 4')
    assert {p.name:sha256(p.read_bytes()).hexdigest() for p in (store.root/old_id).iterdir() if p.is_file()}==old_hashes
    assert page.request.get(base+'/jobs/'+old_id+'/download').json()==legacy
    for name,filename in [('Monte Carlo report JSON ↓','report.json'),('Full-period daily P&L CSV ↓','daily.csv'),('Simulated path outcomes CSV ↓','paths.csv'),('Monte Carlo evidence ZIP ↓','analysis.zip')]:
        with page.expect_download() as download:page.get_by_role('link',name=name,exact=True).click()
        download.value.save_as(tmp_path/filename)
    report=json.loads((tmp_path/'report.json').read_text())
    assert report['passed']==4 and report['total']==4
    assert report['policy']['version']=='campaign-full-period-monte-carlo-v2'
    assert report['reused_population']['analysis_id']==old_id
    assert report['files']['paths.csv']==legacy['files']['paths.csv']
    oos_results=page.request.get(portal['url']+f'/api/campaign-workflows/{workflow["id"]}/oos/results?job={oos["id"]}').json()
    first=oos_results['items'][0]
    playwright.expect(page.locator('#monte-carlo-table td[data-column="is_mtm_dd"]').first).to_have_text(f"{float(first['is_reference']['metrics']['is_mtm_max_drawdown']):,.2f}")
    playwright.expect(page.locator('#monte-carlo-table td[data-column="oos_mtm_dd"]').first).to_have_text(f"{float(first['metrics']['oos_mtm_max_drawdown']):,.2f}")
    for candidate in report['candidates']:
        assert all(s['max_drawdown_median']==0 and s['historical_drawdown_percentile_pct']==50 for s in candidate['scenarios'])
    daily=list(csv.DictReader((tmp_path/'daily.csv').open()))
    assert sum(float(r['net_pnl']) for r in daily if r['candidate']=='1')==14040
    assert any(float(r['net_pnl'])==0 for r in daily) # inactive observed dates survive
    assert len(list(csv.DictReader((tmp_path/'paths.csv').open())))==40000
    new_id=report['id'];page.reload()
    playwright.expect(page.locator('#monte-carlo-status')).to_contain_text('COMPLETE · 4 / 4')
    page.get_by_role('link',name='Monte Carlo job history / progress',exact=True).click()
    playwright.expect(page.locator('#job-progress')).to_contain_text('Final sanity check complete')
    page.get_by_role('link',name='Open final Monte Carlo check',exact=True).click()
    playwright.expect(page.locator('#monte-carlo-table tbody tr')).to_have_count(8)
    again=page.request.get(base+'?job='+oos['id']).json()
    assert again['report']==report and again['job']['id']==new_id
    (tmp_path/'SYNTHETIC-source.csv').write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset['id']+'/csv').body())
    (tmp_path/'original-v1-report.json').write_text(json.dumps(legacy,indent=2))
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,workflow_id=workflow['id'],oos_job_id=oos['id'],analysis_id=new_id,original_analysis_id=old_id,
        expected_full_period_net=[14040,14040,28080,28080],expected_closed_trades_per_candidate=1080,
        expected_paths_per_candidate=10000,expected_candidates_passed=4,expected_daily_close_drawdown=0,
        expected_historical_drawdown_percentile_pct=50,original_files_unchanged=True,monte_carlo_replayed_for_policy_update=False,
        source='120 IS + 60 OOS active dates, each 78 CU/day/contract after existing costs. Other observed dates retained with zero net.',
        limitations='Synthetic source and mechanics attestations; no measured MultiCharts parity or future-edge claim.',
        server='Temporary browser server stopped at teardown.'),indent=2))
    playwright.expect(page.locator('#monte-carlo-table td[data-column="mean_net"]').first).to_have_text(f"{report['candidates'][0]['scenarios'][0]['net_profit_mean']:,.2f}")
    playwright.expect(page.locator('#monte-carlo-drawdown-table')).to_be_hidden()
    page.locator('#monte-carlo-panel').scroll_into_view_if_needed()
    page.locator('#monte-carlo-panel').screenshot(path=str(tmp_path/'monte-carlo-portal.png'))
    page.locator('#monte-carlo-drawdown-details summary').click()
    playwright.expect(page.locator('#monte-carlo-drawdown-table td[data-column="historical_dd"]').first).to_have_text('0.00')
    playwright.expect(page.locator('#monte-carlo-drawdown-table td[data-column="dd_percentile"]').first).to_have_text('50.00')
    page.locator('#monte-carlo-drawdown-details').screenshot(path=str(tmp_path/'daily-close-diagnostics.png'))
    if destination:=os.environ.get('ALPHAQUEST_MC_EVIDENCE_DIR'):
        folder=Path(destination);folder.mkdir(parents=True,exist_ok=True)
        for name in ('report.json','original-v1-report.json','daily.csv','paths.csv','analysis.zip','SYNTHETIC-source.csv','journey.json','monte-carlo-portal.png','daily-close-diagnostics.png'):
            shutil.copyfile(tmp_path/name,folder/name)

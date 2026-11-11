"""Normal OOS -> Monte Carlo -> history -> durable downloads portal journey."""
import csv
import json
import os
from pathlib import Path
import shutil

import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_campaign_oos import frozen_workflow, run_oos


def test_final_sanity_check_runs_in_oos_and_reopens_from_job_history(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=60) as client:
        dataset,workflow=frozen_workflow(client)
        oos,_=run_oos(client,workflow)
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/oos?job={oos["id"]}')
    playwright.expect(page.locator('#monte-carlo-rules li')).to_have_count(3)
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
    for name,filename in [('Monte Carlo report JSON ↓','report.json'),('Full-period daily P&L CSV ↓','daily.csv'),('Simulated path outcomes CSV ↓','paths.csv'),('Monte Carlo evidence ZIP ↓','analysis.zip')]:
        with page.expect_download() as download:page.get_by_role('link',name=name,exact=True).click()
        download.value.save_as(tmp_path/filename)
    report=json.loads((tmp_path/'report.json').read_text())
    assert report['passed']==4 and report['total']==4
    daily=list(csv.DictReader((tmp_path/'daily.csv').open()))
    assert sum(float(r['net_pnl']) for r in daily if r['candidate']=='1')==14040
    assert any(float(r['net_pnl'])==0 for r in daily) # inactive observed dates survive
    assert len(list(csv.DictReader((tmp_path/'paths.csv').open())))==40000
    old_id=report['id'];page.reload()
    playwright.expect(page.locator('#monte-carlo-status')).to_contain_text('COMPLETE · 4 / 4')
    page.get_by_role('link',name='Monte Carlo job history / progress',exact=True).click()
    playwright.expect(page.locator('#job-progress')).to_contain_text('Final sanity check complete')
    page.get_by_role('link',name='Open final Monte Carlo check',exact=True).click()
    playwright.expect(page.locator('#monte-carlo-table tbody tr')).to_have_count(8)
    base=portal['url']+f'/api/campaign-workflows/{workflow["id"]}/oos/monte-carlo'
    again=page.request.get(base+'?job='+oos['id']).json()
    assert again['report']==report and again['job']['id']==old_id
    (tmp_path/'SYNTHETIC-source.csv').write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset['id']+'/csv').body())
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,workflow_id=workflow['id'],oos_job_id=oos['id'],analysis_id=old_id,
        expected_full_period_net=[14040,14040,28080,28080],expected_closed_trades_per_candidate=1080,
        expected_paths_per_candidate=10000,expected_candidates_passed=4,expected_daily_close_drawdown=0,
        source='120 IS + 60 OOS active dates, each 78 CU/day/contract after existing costs. Other observed dates retained with zero net.',
        limitations='Synthetic source and mechanics attestations; no measured MultiCharts parity or future-edge claim.',
        server='Temporary browser server stopped at teardown.'),indent=2))
    page.locator('#monte-carlo-panel').scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path/'monte-carlo-portal.png'),full_page=True)
    if destination:=os.environ.get('ALPHAQUEST_MC_EVIDENCE_DIR'):
        folder=Path(destination);folder.mkdir(parents=True,exist_ok=True)
        for name in ('report.json','daily.csv','paths.csv','analysis.zip','SYNTHETIC-source.csv','journey.json','monte-carlo-portal.png'):
            shutil.copyfile(tmp_path/name,folder/name)

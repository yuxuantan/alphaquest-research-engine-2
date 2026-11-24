"""The actual OOS portal, frozen candidates, comparisons and durable downloads."""
import json
import os
import shutil
from pathlib import Path

import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_campaign_oos import frozen_workflow


def test_oos_portal_runs_all_four_frozen_configs_and_reopens_results(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=60) as client:
        dataset,workflow=frozen_workflow(client)
    prefix=portal['url']+'/api/campaign-workflows/'+workflow['id']+'/oos'
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/oos')
    playwright.expect(page.locator('#oos-results tbody tr')).to_have_count(4)
    playwright.expect(page.locator('#oos-workers')).to_have_value('4')
    playwright.expect(page.locator('#workflow-stage-criteria [data-stage="oos"] li')).to_have_count(7)
    playwright.expect(page.locator('#oos-progress')).to_contain_text('Ready to assess')
    before=page.request.get(portal['url']+'/api/jobs').json()['total']
    assert page.request.get(prefix).json()['job'] is None
    page.locator('#oos-run').click()
    playwright.expect(page.locator('#oos-progress')).to_contain_text('COMPLETE · 4 / 4 configurations',timeout=90000)
    playwright.expect(page.locator('#oos-outcome')).to_contain_text('4 / 4 configurations passed OOS')
    playwright.expect(page.locator('#mechanic-phases [data-phase="oos"]')).to_contain_text('passed')
    assert page.request.get(portal['url']+'/api/jobs').json()['total']==before+1
    assert page.locator('#oos-results thead th.optimization-frozen-column').evaluate_all('items => items.map(x=>x.dataset.column)')==['candidate','param.hold_minutes','param.contracts']
    header_style=page.locator('#oos-results th[data-column="oos_annual"] button').evaluate('button => getComputedStyle(button).borderTopStyle')
    assert header_style=='none'
    row=page.locator('#oos-results tr[data-trial="1"]')
    playwright.expect(row.locator('td[data-column="net"]')).to_have_text('4680.00')
    row.locator('.broad-row-criteria summary').click()
    playwright.expect(row).to_contain_text('Passed · 7 / 7 checks passed')
    playwright.expect(row).to_contain_text('Annualized net profit retention')
    assert row.locator('td[data-column="eligibility"]').evaluate('td => getComputedStyle(td).whiteSpace')=='normal'
    playwright.expect(page.locator('#oos-access')).to_contain_text('no untouched-data certificate')
    with page.expect_download() as download:
        page.get_by_role('link',name='OOS assessment JSON ↓').click()
    download.value.save_as(tmp_path/'oos-assessment.json')
    package=json.loads((tmp_path/'oos-assessment.json').read_text());job=package['job']
    assert job['total_trials']==4 and package['results']['passed']==4
    assert job['research']['oos_policy']['version']=='campaign-oos-v1'
    with page.expect_download() as download:
        page.get_by_role('link',name='OOS results CSV ↓').click()
    download.value.save_as(tmp_path/'oos-results.csv')
    # Sort all four rows locally, retaining frozen parameter columns.
    page.locator('#oos-results th[data-column="net"] button').click()
    page.locator('#oos-results th[data-column="net"] button').click()
    playwright.expect(page.locator('#oos-results tbody td[data-column="net"]').first).to_have_text('9360.00')
    page.get_by_role('link',name='Job history / progress').click()
    playwright.expect(page.get_by_role('link',name='Open OOS',exact=True)).to_be_visible()
    page.get_by_role('link',name='Open OOS',exact=True).click()
    playwright.expect(page.locator('#oos-outcome')).to_contain_text('4 / 4 configurations passed OOS')
    page.reload()
    playwright.expect(page.locator('#oos-results tbody tr')).to_have_count(4)
    playwright.expect(page.locator('#mechanic-phases [data-phase="oos"]')).to_contain_text('passed')
    again=page.request.get(prefix+'/download?job='+job['id']).json()
    assert again==package
    (tmp_path/'SYNTHETIC-source.csv').write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset['id']+'/csv').body())
    (tmp_path/'journey.json').write_text(json.dumps(dict(workflow_id=workflow['id'],dataset_id=dataset['id'],oos_job_id=job['id'],
        expected_configurations=4,expected_is_net=[9360,9360,18720,18720],expected_oos_net=[4680,4680,9360,9360],
        expected_oos_stress_net=[2880,2880,5760,5760],all_frozen_candidates_assessed=True,cartesian_combinations_not_executed=4,
        synthetic=True,mc_parity='Synthetic attestation only; no measured MultiCharts comparison',server='Stopped by fixture teardown.'),indent=2))
    details=page.locator('#oos-results tr[data-trial="1"] .broad-row-criteria');details.locator('summary').click()
    page.screenshot(path=str(tmp_path/'oos-portal.png'),full_page=True)
    if destination:=os.environ.get('ALPHAQUEST_OOS_EVIDENCE_DIR'):
        folder=Path(destination);folder.mkdir(parents=True,exist_ok=True)
        for name in ('SYNTHETIC-source.csv','oos-assessment.json','oos-results.csv','journey.json','oos-portal.png'):
            shutil.copyfile(tmp_path/name,folder/name)

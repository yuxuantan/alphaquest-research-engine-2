"""Final product: qualified campaign -> check -> both phase engines -> saved results."""
import json
import os
from pathlib import Path
import shutil

import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_prop_sim import qualified_source


def test_prop_sim_qualified_single_configuration_real_results_and_downloads(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=120) as client:workflow,source=qualified_source(client)
    page.goto(portal['url']+'/#prop-sim')
    playwright.expect(page.locator('#prop-sim-source option')).to_have_count(5)
    assert page.locator('#prop-sim-source').get_attribute('multiple') is None
    page.locator('#prop-sim-source').select_option('0')
    page.get_by_role('link',name='Open IS source backtest',exact=True).click()
    playwright.expect(page.locator('#report-prop-setup')).to_have_attribute('href','#prop-sim?source='+source['source_backtest_id'])
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-sim-source')).to_have_value('0')
    page.locator('#prop-sim-maximum_micros').fill('3')
    page.locator('#prop-sim-simulations').fill('32')
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    page.locator('#prop-sim-check').click()
    playwright.expect(page.locator('#prop-sim-status')).to_contain_text('Source compatible',timeout=30000)
    with page.expect_response(lambda r:r.url.endswith('/api/prop-sim') and r.request.method=='POST') as response:
        page.locator('#prop-sim-run').click()
    record=response.value.json();assert response.value.status==202
    assert len(record['configuration']['selections'])==1
    page.get_by_role('navigation',name='Main navigation',exact=True).get_by_role('link',name='Dataset',exact=True).click()
    page.goto(portal['url']+'/#prop-sim?analysis='+record['id'])
    for phase in ('evaluation','funded'):
        playwright.expect(page.locator('#prop-sim-'+phase+'-progress')).to_contain_text('COMPLETE',timeout=90000)
        playwright.expect(page.locator('#prop-sim-'+phase+'-table tbody tr')).to_have_count(3)
        parent=page.locator('#prop-sim-'+phase+'-results')
        with page.expect_download() as download:parent.get_by_role('link',name='Saved report JSON ↓',exact=True).click()
        download.value.save_as(tmp_path/(phase+'-report.json'))
        with page.expect_download() as download:parent.get_by_role('link',name='Results CSV ↓',exact=True).click()
        download.value.save_as(tmp_path/(phase+'-results.csv'))
        with page.expect_download() as download:parent.get_by_role('link',name='Evidence ZIP ↓',exact=True).click()
        download.value.save_as(tmp_path/(phase+'-analysis.zip'))
        parent.screenshot(path=str(tmp_path/(phase+'-portal.png')))
    evaluation=json.loads((tmp_path/'evaluation-report.json').read_text())['calculations']
    funded=json.loads((tmp_path/'funded-report.json').read_text())['calculations']
    assert evaluation['frontier'] and funded['winner']
    for row in evaluation['candidates']:
        if row['metrics']['cost_per_funded'] is not None:
            assert abs(row['metrics']['cost_per_funded']-(49/row['metrics']['pass_probability']+129))<1e-8
    for row in funded['candidates']:
        assert row['metrics']['expected_funded_cash_payouts_within_horizon']==sum(p['cash_received'] for p in row['paths'])/len(row['paths'])
    page.locator('#prop-sim-funded-results').get_by_role('link',name='Job history / progress',exact=True).click()
    playwright.expect(page.get_by_role('link',name='Open Prop Sim',exact=True)).to_be_visible()
    page.get_by_role('link',name='Open Prop Sim',exact=True).click()
    playwright.expect(page.locator('#prop-sim-funded-table tbody tr')).to_have_count(3)
    page.reload()
    playwright.expect(page.locator('#prop-sim-funded-table tbody tr')).to_have_count(3)
    saved=page.request.get(portal['url']+'/api/prop-sim/'+record['id']).json()
    (tmp_path/'prop-sim.json').write_text(json.dumps(saved,indent=2))
    dataset=source['dataset']['id'];(tmp_path/'SYNTHETIC-source.csv').write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset+'/csv').body())
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,simulation_id=record['id'],workflow_id=workflow['id'],
        qualification=source['qualification'],source_backtest_id=source['source_backtest_id'],
        sizes=[1,2,3],paths_per_size_per_phase=32,
        expected_evaluation_cost_formula='49 / empirical_attempt_pass_probability + 129',
        expected_funded_receipts_formula='sum(path.cash_received for all starts) / 32',
        evaluation=[dict(micros=r['manifest']['configuration']['micros'],metrics=r['metrics'],pareto=r['pareto_member']) for r in evaluation['candidates']],
        funded=[dict(micros=r['manifest']['configuration']['micros'],metrics=r['metrics'],rank=r['rank']) for r in funded['candidates']],
        portfolio_optimization=False,provider_parity='Not claimed; local rule snapshot and held-OHLC bounds',server='Temporary server stopped by fixture teardown.'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_SIM_EVIDENCE_DIR'):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        for file in tmp_path.iterdir():
            if file.is_file() and file.suffix in ('.json','.csv','.zip','.png'):shutil.copyfile(file,target/file.name)

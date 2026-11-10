"""Real IS Broad grid, existing column controls, manual profitable selection and carry-forward."""
import json
from hashlib import sha256

import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_campaign_broad import passed_mechanics


def test_broad_search_columns_profit_filter_and_locked_selection(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=30) as client:
        dataset,body,workflow=passed_mechanics(client)
    prefix=portal['url']+'/api/campaign-workflows/'+workflow['id']
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/mechanic_validation')
    page.locator('#mechanic-phases [data-phase="is_broad"]').click()
    playwright.expect(page.locator('#broad-config')).to_be_visible()
    for name,end,step in [('green_bar_count','4','1'),('hold_minutes','60','20'),('contracts','3','1')]:
        page.get_by_label(name.replace('_',' ').capitalize()+' end',exact=True).fill(end)
        page.get_by_label(name.replace('_',' ').capitalize()+' step',exact=True).fill(step)
    page.locator('#broad-preview').click()
    playwright.expect(page.locator('#broad-count')).to_have_text('18 iterations · IS only')
    page.screenshot(path=str(tmp_path/'01-grid.png'),full_page=True)
    page.locator('#broad-run').click()
    playwright.expect(page.locator('#broad-progress')).to_contain_text('COMPLETE',timeout=30000)
    playwright.expect(page.locator('#broad-results tbody tr')).to_have_count(18)
    playwright.expect(page.locator('#broad-results tr.broad-ineligible')).to_have_count(15)
    playwright.expect(page.get_by_role('checkbox',name='Select trial 4',exact=True)).to_be_disabled()
    playwright.expect(page.get_by_role('checkbox',name='Select trial 10',exact=True)).to_be_disabled()
    before={p:sha256(p.read_bytes()).hexdigest() for p in portal['app'].state.runs.root.glob('*/*') if p.is_file()}
    page.locator('#broad-columns > summary').click()
    page.get_by_role('checkbox',name='Show Total gross pnl',exact=True).uncheck()
    page.get_by_role('checkbox',name='Freeze Contracts',exact=True).check()
    playwright.expect(page.locator('#broad-results th[data-column="total_gross_pnl"]')).to_be_hidden()
    playwright.expect(page.locator('#broad-results th[data-column="param.contracts"]')).to_have_class(__import__('re').compile('optimization-frozen-column'))
    page.locator('#broad-columns > summary').click()
    for trial in [1,2]:
        with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/broad/selection')) as saved:
            page.get_by_role('checkbox',name=f'Select trial {trial}',exact=True).check()
        assert saved.value.ok
    playwright.expect(page.get_by_role('checkbox',name='Select trial 3',exact=True)).to_be_disabled()
    with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/broad/selection')):
        page.get_by_role('checkbox',name='Select trial 1',exact=True).uncheck()
    playwright.expect(page.get_by_role('checkbox',name='Select trial 3',exact=True)).to_be_enabled()
    with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/broad/selection')):
        page.get_by_role('checkbox',name='Select trial 3',exact=True).check()
    playwright.expect(page.locator('#broad-selected')).to_contain_text('2 / 2')
    page.screenshot(path=str(tmp_path/'02-results-and-selection.png'),full_page=True)
    page.locator('#broad-confirm').click()
    playwright.expect(page.locator('#mechanic-phases [data-phase="is_narrow"]')).to_have_attribute('aria-current','step')
    playwright.expect(page.locator('#mechanic-content .workflow-input-card')).to_have_count(2)
    playwright.expect(page.locator('#mechanic-content')).to_contain_text('Trial 2 · IS net 156.00')
    playwright.expect(page.locator('#mechanic-content')).to_contain_text('Trial 3 · IS net 234.00')
    playwright.expect(page.locator('#mechanic-phases [data-phase="oos"]')).to_be_disabled()
    page.reload()
    playwright.expect(page.locator('#mechanic-content .workflow-input-card')).to_have_count(2)
    page.screenshot(path=str(tmp_path/'03-is-narrow-inputs.png'),full_page=True)
    page.locator('#mechanic-phases [data-phase="is_broad"]').click()
    playwright.expect(page.locator('#broad-confirm')).to_have_text('Configurations confirmed')
    playwright.expect(page.get_by_role('checkbox',name='Select trial 2',exact=True)).to_be_checked()
    playwright.expect(page.get_by_role('checkbox',name='Select trial 2',exact=True)).to_be_disabled()
    playwright.expect(page.locator('#broad-run')).to_be_disabled()
    playwright.expect(page.locator('#broad-results th[data-column="total_gross_pnl"]')).to_be_hidden()
    playwright.expect(page.locator('#broad-results th[data-column="param.contracts"]')).to_have_class(__import__('re').compile('optimization-frozen-column'))
    with page.expect_download() as download:
        page.get_by_role('link',name='Saved IS Broad package ↓',exact=True).click()
    download.value.save_as(tmp_path/'is-broad-package.json')
    package=json.loads((tmp_path/'is-broad-package.json').read_bytes())
    assert package['state']['selected_trials']==[2,3]
    assert [c['parameters']['contracts'] for c in package['state']['selection']]==[2,3]
    state=package['state']
    assert page.request.patch(prefix+'/broad/selection',data={'job_id':state['job_id'],'revision':state['revision'],'trials':[]}).status==409
    assert page.request.get(portal['url']+'/api/backtests').json()['total']==19
    assert page.request.get(portal['url']+'/api/jobs').json()['total']==2
    page.get_by_role('link',name='Job history',exact=True).click()
    page.locator(f'#jobs-rows tr[data-job-id="{state["job_id"]}"]').get_by_role('link',name='View results',exact=True).click()
    page.get_by_role('link',name='Open IS Broad',exact=True).click()
    playwright.expect(page.locator('#broad-confirm')).to_have_text('Configurations confirmed')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(tmp_path/'04-mobile.png'),full_page=True)
    for name,path in [('results.json',prefix+'/broad/results'),('results.csv',portal['url']+'/api/backtests/batches/'+state['job_id']+'/exports/results'),('SYNTHETIC-source.csv',portal['url']+'/api/datasets/'+dataset['id']+'/csv')]:
        response=page.request.get(path);assert response.ok
        (tmp_path/name).write_bytes(response.body())
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}
    (tmp_path/'journey.json').write_text(json.dumps({'workflow_id':workflow['id'],'broad_job_id':state['job_id'],'expected_trials':18,'expected_eligible':[1,2,3],'chosen_trials':[2,3],'chosen_net':[156,234],'expected_ineligible':15,'expected_backtests':19,'expected_jobs':2,'mc_parity':'Synthetic user-attestation exercise only; no automated or measured MC comparison','server':'Stopped by fixture teardown.'},indent=2))

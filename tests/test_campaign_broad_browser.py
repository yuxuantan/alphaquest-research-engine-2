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
    rules=page.locator('#workflow-stage-criteria')
    playwright.expect(rules.locator('[data-stage="is_broad"]')).to_contain_text('24 calendar months')
    playwright.expect(rules.locator('[data-stage="is_broad"]')).to_contain_text('one extra tick')
    rules.locator('[data-stage="is_narrow"] summary').click()
    playwright.expect(rules.locator('[data-stage="is_narrow"]')).to_contain_text('At least 70%')
    playwright.expect(rules.locator('[data-stage="is_narrow"]')).to_contain_text('95% lower confidence bound')
    playwright.expect(rules.locator('[data-stage="is_narrow"] summary')).to_contain_text('not implemented')
    rules.locator('[data-stage="is_narrow"] summary').click()
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
    first=page.locator('#broad-results tr[data-trial="1"]')
    first.locator('.broad-row-criteria summary').click()
    playwright.expect(first.locator('.broad-row-criteria li')).to_have_count(6)
    playwright.expect(first.locator('.broad-row-criteria')).to_contain_text('24 months; 144 closed trades')
    with page.expect_download() as measured:
        first.get_by_role('link',name='Screening measurements ↓',exact=True).click()
    measured.value.save_as(tmp_path/'screening-trial-1.json')
    screening=json.loads((tmp_path/'screening-trial-1.json').read_bytes())
    assert screening['qualifies'] and float(screening['metrics']['is_mtm_max_drawdown'])==40.5
    assert float(screening['metrics']['is_stress_net_profit'])==1152
    broad_url=page.url
    first.get_by_role('link',name='Cost-stress report',exact=True).click()
    playwright.expect(page.locator('#report-net')).to_have_text('1152.00')
    page.goto(broad_url)
    playwright.expect(page.locator('#broad-results tbody tr')).to_have_count(18)
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
    playwright.expect(page.locator('#mechanic-content')).to_contain_text('Trial 2 · IS net 3744.00')
    playwright.expect(page.locator('#mechanic-content')).to_contain_text('Trial 3 · IS net 5616.00')
    playwright.expect(page.locator('#mechanic-phases [data-phase="oos"]')).to_be_disabled()
    page.reload()
    playwright.expect(page.locator('#mechanic-content .workflow-input-card')).to_have_count(2)
    playwright.expect(page.locator('#workflow-stage-criteria [data-stage="is_narrow"]')).to_contain_text('Retain all six')
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
    assert page.request.get(portal['url']+'/api/backtests').json()['total']==37 # 18 base + 18 native stress + mechanics
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
    (tmp_path/'journey.json').write_text(json.dumps({'workflow_id':workflow['id'],'broad_job_id':state['job_id'],'expected_trials':18,'expected_eligible':[1,2,3],'chosen_trials':[2,3],'chosen_net':[3744,5616],'expected_ineligible':15,'expected_backtests':37,'expected_jobs':2,'mc_parity':'Synthetic user-attestation exercise only; no automated or measured MC comparison','server':'Stopped by fixture teardown.'},indent=2))


def test_insufficient_history_and_extra_cost_failure_are_explained_and_unselectable(page,portal,tmp_path):
    from test_campaign_mechanics import create_workflow,run_validation,checks
    from test_campaign_broad import create_broad_workflow
    for name,make,expected in [('short',create_workflow,'Insufficient evidence'),('cost-stress',lambda client:create_broad_workflow(client,fragile=True),'Not qualified · 5 / 6 passed')]:
        with httpx.Client(base_url=portal['url'],timeout=30) as client:
            dataset,_,workflow=make(client)
            result=run_validation(client,workflow);prefix=portal['url']+'/api/campaign-workflows/'+workflow['id']
            reviewed=client.patch(prefix+'/review',json=checks(result)).json()
            assert client.post(prefix+'/confirm',json={'revision':reviewed['review']['revision']}).status_code==200
        page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/is_broad')
        page.locator('#broad-preview').click()
        playwright.expect(page.locator('#broad-count')).to_have_text('1 iterations · IS only')
        page.locator('#broad-run').click()
        playwright.expect(page.locator('#broad-progress')).to_contain_text('COMPLETE',timeout=30000)
        row=page.locator('#broad-results tbody tr')
        playwright.expect(row.locator('.broad-row-criteria summary')).to_have_text(expected)
        row.locator('.broad-row-criteria summary').click()
        playwright.expect(page.get_by_role('checkbox',name='Select trial 1',exact=True)).to_be_disabled()
        playwright.expect(page.locator('#broad-confirm')).to_be_disabled()
        playwright.expect(page.locator('#mechanic-phases [data-phase="is_narrow"]')).to_be_disabled()
        if name=='cost-stress':
            playwright.expect(row.locator('.broad-row-criteria')).to_contain_text('FAIL · Extra-slippage native rerun: -48.00')
        page.screenshot(path=str(tmp_path/(name+'-rejection.png')),full_page=True)
        (tmp_path/(name+'-results.json')).write_bytes(page.request.get(prefix+'/broad/results').body())
        (tmp_path/(name+'-SYNTHETIC-source.csv')).write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset['id']+'/csv').body())

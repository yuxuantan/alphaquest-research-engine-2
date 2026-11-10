"""Real IS Broad grid, existing column controls, manual profitable selection and carry-forward."""
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256

import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_campaign_broad import passed_mechanics,start_grid,broad_grid


def test_broad_search_columns_profit_filter_and_locked_selection(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=30) as client:
        dataset,body,workflow=passed_mechanics(client)
        # A previous completed run must remain inspectable after a replacement.
        earlier,_=start_grid(client,'/api/campaign-workflows/'+workflow['id'],broad_grid(3,20,1))
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
    playwright.expect(page.locator('#broad-progress')).to_contain_text('COMPLETE · 18 / 18 trials',timeout=30000)
    playwright.expect(page.locator('#broad-results tbody tr')).to_have_count(18)
    playwright.expect(page.locator('#broad-results tr.broad-ineligible')).to_have_count(15)
    varied=['param.green_bar_count','param.hold_minutes','param.contracts']
    frozen=page.locator('#broad-results thead th.optimization-frozen-column')
    playwright.expect(frozen).to_have_count(5)
    assert frozen.evaluate_all('cells => cells.map(cell => cell.dataset.column)')==['select','trial',*varied]
    for key in varied:
        playwright.expect(page.locator(f'#broad-results th[data-column="{key}"]')).to_be_visible()
    scroll=page.locator('#broad-results-scroll')
    before=frozen.evaluate_all('cells => cells.map(cell => cell.getBoundingClientRect().x)')
    assert scroll.evaluate('el => el.scrollWidth > el.clientWidth')
    scroll.evaluate('el => {el.scrollLeft = 400}')
    page.wait_for_function("() => document.querySelector('#broad-results-scroll').scrollLeft > 0")
    after=frozen.evaluate_all('cells => cells.map(cell => cell.getBoundingClientRect().x)')
    assert all(abs(left-right)<1 for left,right in zip(before,after))
    scroll.evaluate('el => {el.scrollLeft = 0}')
    playwright.expect(page.get_by_role('checkbox',name='Select trial 4',exact=True)).to_be_disabled()
    playwright.expect(page.get_by_role('checkbox',name='Select trial 10',exact=True)).to_be_disabled()
    first=page.locator('#broad-results tr[data-trial="1"]')
    metrics=page.request.get(prefix+'/broad').json()['job']['metric_columns']
    for key in metrics:
        displayed=first.locator(f'td[data-column="{key}"]').inner_text()
        assert displayed=='N/A' or re.fullmatch(r'-?\d+\.\d{2}',displayed),(key,displayed)
    playwright.expect(first.locator('td[data-column="total_net_pnl"]')).to_have_text('1872.00')
    playwright.expect(first.locator('td[data-column="trades_taken"]')).to_have_text('144.00')
    results=page.request.get(prefix+'/broad/results').json()['items']
    assert str(results[0]['metrics']['trades_taken'])=='144'
    longest=max(results,key=lambda row: Decimal(str(row['metrics']['max_drawdown_duration_seconds'])))
    seconds=Decimal(str(longest['metrics']['max_drawdown_duration_seconds']))
    assert seconds>86400
    duration=seconds/Decimal(86400)
    expected=duration.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    playwright.expect(page.locator('#broad-results th[data-column="max_drawdown_duration_seconds"]')).to_contain_text('calendar days')
    playwright.expect(page.locator(f'#broad-results tr[data-trial="{longest["trial"]}"] td[data-column="max_drawdown_duration_seconds"]')).to_have_text(f'{expected:.2f}')
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
    page.get_by_role('checkbox',name='Freeze Green bar count',exact=True).uncheck()
    playwright.expect(page.locator('#broad-columns .optimization-freeze-count')).to_have_text('4 frozen')
    page.reload()
    playwright.expect(page.locator('#broad-results tbody tr')).to_have_count(18)
    page.locator('#broad-columns > summary').click()
    playwright.expect(page.get_by_role('checkbox',name='Freeze Green bar count',exact=True)).not_to_be_checked()
    page.get_by_role('button',name='Reset layout',exact=True).click()
    playwright.expect(page.get_by_role('checkbox',name='Freeze Green bar count',exact=True)).to_be_checked()
    playwright.expect(page.locator('#broad-columns .optimization-freeze-count')).to_have_text('5 frozen')
    page.get_by_role('checkbox',name='Show Total gross pnl',exact=True).uncheck()
    playwright.expect(page.get_by_role('checkbox',name='Freeze Contracts',exact=True)).to_be_checked()
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
    assert page.request.get(portal['url']+'/api/jobs').json()['total']==3
    page.get_by_role('link',name='Job history',exact=True).click()
    page.locator(f'#jobs-rows tr[data-job-id="{state["job_id"]}"]').get_by_role('link',name='View results',exact=True).click()
    playwright.expect(page.get_by_role('link',name='Open IS Broad',exact=True)).to_be_visible()
    playwright.expect(page.get_by_role('link',name='Open batch progress / results',exact=True)).to_have_count(0)
    page.screenshot(path=str(tmp_path/'05-single-job-destination.png'),full_page=True)
    page.get_by_role('link',name='Open IS Broad',exact=True).click()
    playwright.expect(page.locator('#broad-confirm')).to_have_text('Configurations confirmed')
    playwright.expect(page.locator('#broad-progress')).to_contain_text('elapsed')
    playwright.expect(page.locator('#broad-run-settings')).to_contain_text(state['job_id'])
    page.goto(portal['url']+'/#backtests/batches/'+state['job_id'])
    playwright.expect(page).to_have_url(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/is_broad?job='+state['job_id'])
    playwright.expect(page.locator('#broad-results tbody tr')).to_have_count(18)
    page.goto(portal['url']+'/#optimizations/'+state['job_id'])
    playwright.expect(page.locator('#broad-confirm')).to_have_text('Configurations confirmed')
    page.goto(portal['url']+'/#backtests/batches/'+earlier['id'])
    playwright.expect(page.locator('#broad-archived')).to_be_visible()
    playwright.expect(page.locator('#broad-results tbody tr')).to_have_count(1)
    playwright.expect(page.locator('#broad-columns .optimization-freeze-count')).to_have_text('2 frozen')
    for key in varied:
        playwright.expect(page.locator(f'#broad-results th[data-column="{key}"]')).to_be_hidden()
    playwright.expect(page.locator('#broad-results td[data-column="total_net_pnl"]')).to_have_text('1872.00')
    playwright.expect(page.get_by_role('checkbox',name='Select trial 1',exact=True)).to_be_disabled()
    playwright.expect(page.locator('#broad-confirm')).to_be_disabled()
    playwright.expect(page.locator('#broad-run')).to_be_disabled()
    with page.expect_download() as archived_download:
        page.get_by_role('link',name='Saved IS Broad package ↓',exact=True).click()
    archived_download.value.save_as(tmp_path/'earlier-is-broad-package.json')
    archived=json.loads((tmp_path/'earlier-is-broad-package.json').read_bytes())
    assert archived['job']['id']==earlier['id'] and archived['state']['archived']
    page.screenshot(path=str(tmp_path/'06-earlier-run.png'),full_page=True)
    page.get_by_role('link',name='Open current IS Broad →',exact=True).click()
    playwright.expect(page.locator('#broad-results tbody tr')).to_have_count(18)
    playwright.expect(page.locator('#broad-confirm')).to_have_text('Configurations confirmed')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(tmp_path/'04-mobile.png'),full_page=True)
    for name,path in [('results.json',prefix+'/broad/results'),('results.csv',portal['url']+'/api/backtests/batches/'+state['job_id']+'/exports/results'),('SYNTHETIC-source.csv',portal['url']+'/api/datasets/'+dataset['id']+'/csv')]:
        response=page.request.get(path);assert response.ok
        (tmp_path/name).write_bytes(response.body())
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in before}
    (tmp_path/'journey.json').write_text(json.dumps({'workflow_id':workflow['id'],'broad_job_id':state['job_id'],'earlier_job_id':earlier['id'],'expected_trials':18,'expected_eligible':[1,2,3],'chosen_trials':[2,3],'chosen_net':[3744,5616],'expected_ineligible':15,'expected_backtests':37,'expected_jobs':3,'single_job_destination':True,'old_batch_urls_redirect':True,'earlier_results_read_only':True,'mc_parity':'Synthetic user-attestation exercise only; no automated or measured MC comparison','server':'Stopped by fixture teardown.'},indent=2))


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


def test_queued_cancel_and_failed_run_resume_live_on_is_broad(page,portal,tmp_path,monkeypatch):
    from threading import Event
    from test_campaign_broad import preview_body
    optimizer=portal['app'].state.optimizations
    with httpx.Client(base_url=portal['url'],timeout=30) as client:
        _,_,workflow=passed_mechanics(client)
        prefix='/api/campaign-workflows/'+workflow['id']
        release=Event();barrier=optimizer.executor.submit(release.wait)
        try:
            body=preview_body(client,prefix,broad_grid(3,20,1))
            response=client.post(prefix+'/broad/run',json=body);assert response.status_code==202,response.text
            queued=response.json()['id']
            page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/is_broad?job='+queued)
            playwright.expect(page.locator('#broad-cancel')).to_be_visible()
            page.locator('#broad-cancel').click()
            playwright.expect(page.locator('#broad-progress')).to_contain_text('CANCELLED')
            assert client.get('/api/backtests').json()['total']==1 # the queued grid did not execute
        finally:
            release.set();barrier.result(timeout=5)
        publish=optimizer.publish
        def fail_second(*args,**kwargs):
            if args[1]==2:raise ValueError('SYNTHETIC publication failure; first trial retained')
            return publish(*args,**kwargs)
        monkeypatch.setattr(optimizer,'publish',fail_second)
        page.get_by_label('Contracts end',exact=True).fill('2')
        page.locator('#broad-preview').click()
        playwright.expect(page.locator('#broad-count')).to_have_text('2 iterations · IS only')
        page.locator('#broad-run').click()
        playwright.expect(page.locator('#broad-progress')).to_contain_text('FAILED',timeout=30000)
        failed=client.get(prefix+'/broad').json()['job']['id']
        assert failed!=queued and 'job='+failed in page.url
        playwright.expect(page.locator('#broad-resume')).to_have_text('Resume remaining 1 trials')
        playwright.expect(page.locator('#broad-results tbody tr')).to_have_count(1)
        row=client.get(prefix+'/broad/results').json()['items'][0]
        preserved={p:sha256(p.read_bytes()).hexdigest() for p in (optimizer.runs.root/row['run_id']).iterdir() if p.is_file()}
        page.screenshot(path=str(tmp_path/'failed-with-resume.png'),full_page=True)
        monkeypatch.setattr(optimizer,'publish',publish)
        page.locator('#broad-resume').click()
        playwright.expect(page.locator('#broad-progress')).to_contain_text('COMPLETE',timeout=30000)
        playwright.expect(page.locator('#broad-results tbody tr')).to_have_count(2)
        assert page.locator('#broad-results thead th.optimization-frozen-column').evaluate_all(
            'cells => cells.map(cell => cell.dataset.column)')==['select','trial','param.contracts']
        for key in ['param.green_bar_count','param.hold_minutes']:
            playwright.expect(page.locator(f'#broad-results th[data-column="{key}"]')).to_be_hidden()
        page.locator('#broad-columns > summary').click()
        page.get_by_role('checkbox',name='Show Green bar count',exact=True).check()
        playwright.expect(page.locator('#broad-results th[data-column="param.green_bar_count"]')).to_be_visible()
        page.get_by_role('button',name='Reset layout',exact=True).click()
        playwright.expect(page.locator('#broad-results th[data-column="param.green_bar_count"]')).to_be_hidden()
        playwright.expect(page.locator('#broad-resume')).to_be_hidden()
        playwright.expect(page.get_by_role('checkbox',name='Select trial 2',exact=True)).to_be_enabled()
        assert client.get(prefix+'/broad').json()['job']['id']==failed
        assert preserved=={p:sha256(p.read_bytes()).hexdigest() for p in preserved}
        page.screenshot(path=str(tmp_path/'resumed-on-is-broad.png'),full_page=True)
        (tmp_path/'controls-journey.json').write_text(json.dumps(dict(queued_job=queued,resumed_job=failed,
            queued_cancel_executed_no_trials=True,resumed_same_job=True,retained_first_report_unchanged=True,
            expected_net=[1872,3744],results=client.get(prefix+'/broad/results').json()),indent=2))

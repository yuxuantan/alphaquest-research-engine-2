"""Normal portal journey through both measured Narrow branches and frozen OOS handoff."""
import json
import os
import shutil
from pathlib import Path

import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_campaign_narrow import narrow_workflow,narrow_start,narrow_grid
from test_campaign_broad import wait_job


def test_running_narrow_progress_polls_job_without_reloading_results(page,portal):
    with httpx.Client(base_url=portal['url'],timeout=40) as client:
        _,workflow,_=narrow_workflow(client)
        completed=narrow_start(client,'/api/campaign-workflows/'+workflow['id'],1)
        saved_detail=client.get('/api/campaign-workflows/'+workflow['id']+'/narrow',params={'broad_trial':1}).json()
    job_id=completed['id']
    active=dict(trial=1,stage='cost_stress: replaying',bars_processed=0,total_bars=2400)
    progress_calls=[];result_calls=[];simulated_status={'value':'running'}
    def narrow_detail(route):
        body=json.loads(json.dumps(saved_detail))
        body['job'].update(status=simulated_status['value'],stage='running_trials',completed_trials=0,active_trials=[active])
        route.fulfill(status=200,content_type='application/json',body=json.dumps(body))
    def job_progress(route):
        progress_calls.append(1)
        job=dict(completed,status='running',stage='running_trials',completed_trials=0,
                 active_trials=[dict(active,bars_processed=1200 if len(progress_calls)==1 else 2000)])
        route.fulfill(status=200,content_type='application/json',body=json.dumps(job))
    page.route('**/api/campaign-workflows/'+workflow['id']+'/narrow?*',narrow_detail)
    page.route('**/api/optimizations/'+job_id,job_progress)
    page.on('request',lambda request: result_calls.append(request.url) if '/narrow/results?' in request.url else None)
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/is_narrow?broad_trial=1')
    locked = page.locator('#narrow-config tr[data-parameter="contracts"]')
    playwright.expect(locked.locator('.parameter-help')).to_contain_text('Fixed contract quantity')
    playwright.expect(locked.locator('th')).to_contain_text('Selected Broad value: 1')
    playwright.expect(locked.locator('input').first).to_be_disabled()
    assert locked.locator('input').first.get_attribute('aria-describedby') == 'narrow-parameter-help-contracts'
    playwright.expect(page.locator('#narrow-active-trials')).to_contain_text('2,000 / 2,400 bars',timeout=10000)
    assert len(progress_calls)>=2
    assert len(result_calls)==1
    simulated_status['value']='interrupted'
    page.route('**/api/backtests/batches/'+job_id+'/resume',lambda route:route.fulfill(
        status=422,content_type='application/json',body=json.dumps({
            'detail':'Engine code has changed since this optimization. Start a new job to keep results consistent.'})))
    page.reload()
    playwright.expect(page.locator('#narrow-active-trials')).to_be_hidden()
    page.locator('#narrow-results').scroll_into_view_if_needed()
    page.get_by_role('button',name='Resume remaining 4 trials').click()
    playwright.expect(page.locator('#narrow-job-status')).to_contain_text('Could not resume: Engine code has changed')


def test_narrow_portal_two_broad_branches_columns_and_oos_handoff(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=40) as client:
        dataset,workflow,broad=narrow_workflow(client)
    prefix=portal['url']+'/api/campaign-workflows/'+workflow['id']
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/is_narrow')
    playwright.expect(page.locator('#narrow-chooser')).to_be_visible()
    playwright.expect(page.locator('#narrow-broad-trial option')).to_have_count(2)
    for item in page.locator('#narrow-config tr[data-parameter="contracts"] input').all():
        playwright.expect(item).to_be_disabled()
    playwright.expect(page.locator('#narrow-config tr[data-parameter="contracts"] input').first).to_have_value('1')
    page.get_by_label('Hold minutes start',exact=True).fill('14')
    page.get_by_label('Hold minutes end',exact=True).fill('20')
    page.get_by_label('Hold minutes step',exact=True).fill('2')
    playwright.expect(page.get_by_label('Hold minutes local plateau step',exact=True)).to_have_count(0)
    page.locator('#narrow-preview').click()
    playwright.expect(page.locator('#narrow-count')).to_have_text('4 iterations · IS only')
    page.locator('#narrow-run').click()
    playwright.expect(page.locator('#narrow-progress')).to_contain_text('COMPLETE · 4 / 4 trials',timeout=30000)
    playwright.expect(page.locator('#narrow-results tbody tr')).to_have_count(4)
    playwright.expect(page.locator('#narrow-selected')).to_contain_text('0 / 2')
    playwright.expect(page.locator('#narrow-policy-notice')).to_contain_text('Plateau policy is-narrow-v4')
    assert page.request.get(prefix+'/narrow/results?broad_trial=1').json()['all_branches_complete'] is False
    playwright.expect(page.locator('#narrow-results tr[data-trial="2"] .broad-row-criteria')).to_contain_text('Qualified · 7 / 7 checks passed')
    center=page.locator('#narrow-results tr[data-trial="2"] .broad-row-criteria')
    center.locator('summary').click()
    playwright.expect(center).to_contain_text('Tested-grid parameter plateau')
    playwright.expect(center).to_contain_text('retains 100.00%')
    playwright.expect(center).to_contain_text('extra-slippage net')
    center.locator('summary').click()
    boundary=page.locator('#narrow-results tr[data-trial="1"] .broad-row-criteria')
    boundary.locator('summary').click()
    playwright.expect(boundary).to_contain_text('Insufficient evidence: 1 tested neighbors')
    playwright.expect(boundary).to_contain_text('One-sided boundary assessment: Hold minutes')
    boundary.locator('summary').click()
    for trial in (2,3):
        with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/narrow/selection')):
            page.get_by_role('checkbox',name=f'Select Narrow trial {trial}').check()
    with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/narrow/selection')):
        page.locator('#narrow-clear-selection').click()
    playwright.expect(page.locator('#narrow-selected')).to_contain_text('0 / 2')
    for trial in (2,3):
        with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/narrow/selection')):
            page.get_by_role('checkbox',name=f'Select Narrow trial {trial}').check()
    page.locator('#narrow-confirm').click()
    playwright.expect(page.locator('#narrow-confirm')).to_have_text('Narrow choices confirmed')
    playwright.expect(page.locator('#narrow-clear-selection')).to_be_disabled()
    playwright.expect(page.locator('#mechanic-phases [data-phase="oos"]')).to_be_disabled()
    with httpx.Client(base_url=portal['url'],timeout=40) as client:
        second=narrow_start(client,'/api/campaign-workflows/'+workflow['id'],2)
    page.reload()
    playwright.expect(page.locator('#narrow-results tbody tr')).to_have_count(4)
    header_style=page.locator('#narrow-results th[data-column="param.hold_minutes"] button').evaluate(
        'button => ({border:getComputedStyle(button).borderTopStyle,background:getComputedStyle(button).backgroundColor,padding:getComputedStyle(button).paddingTop})')
    assert header_style=={'border':'none','background':'rgba(0, 0, 0, 0)','padding':'8px'}
    assert page.locator('#narrow-results th[data-column="param.hold_minutes"]').evaluate(
        'cell => getComputedStyle(cell).position')=='sticky'
    screened=[]
    page.on('request',lambda request: screened.append(request.url) if '/narrow/results?' in request.url else None)
    first_job=page.request.get(prefix+'/narrow?broad_trial=1').json()['job']['id']
    with page.expect_response(lambda response: f'/api/backtests/batches/{first_job}/results?' in response.url and 'direction=asc' in response.url):
        page.locator('#narrow-results th[data-column="param.hold_minutes"] button').click()
    assert page.locator('#narrow-results tbody tr').evaluate_all('rows => rows.map(row => Number(row.dataset.trial))')==[1,2,3,4]
    with page.expect_response(lambda response: f'/api/backtests/batches/{first_job}/results?' in response.url and 'direction=desc' in response.url):
        page.locator('#narrow-results th[data-column="param.hold_minutes"] button').click()
    playwright.expect(page.locator('#narrow-sort-status')).to_contain_text('Sorted by Hold minutes descending.')
    assert page.locator('#narrow-results tbody tr').evaluate_all('rows => rows.map(row => Number(row.dataset.trial))')==[4,3,2,1]
    assert screened==[]
    playwright.expect(page.locator('#narrow-results thead th.optimization-frozen-column').first).to_be_visible()
    assert page.locator('#narrow-results thead th.optimization-frozen-column').evaluate_all('items => items.map(el=>el.dataset.column)')==['select','trial','param.hold_minutes']
    playwright.expect(page.locator('#narrow-results th[data-column="param.contracts"]')).to_be_hidden()
    playwright.expect(page.locator('#narrow-results td[data-column="total_net_pnl"]').first).to_have_text('9360.00')
    row=page.locator('#narrow-results tbody tr').first
    row.locator('.broad-row-criteria summary').click()
    playwright.expect(row.locator('.broad-row-criteria')).to_contain_text('Search-adjusted daily net lower bound')
    playwright.expect(row.locator('.broad-row-criteria')).to_contain_text('Bonferroni family of 6 attempted trials')
    playwright.expect(page.get_by_role('checkbox',name='Select Narrow trial 1')).to_be_disabled()
    assert page.request.get(prefix+'/narrow/results?broad_trial=1').json()['family_size']==6
    page.locator('#narrow-broad-trial').select_option('2')
    playwright.expect(page.locator('#narrow-results tbody tr')).to_have_count(4)
    for trial in (2,3):
        with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/narrow/selection')):
            page.get_by_role('checkbox',name=f'Select Narrow trial {trial}').check()
    page.locator('#narrow-confirm').click()
    playwright.expect(page.locator('#narrow-confirm')).to_have_text('Narrow choices confirmed')
    page.reload()
    playwright.expect(page.locator('#mechanic-phases [data-phase="oos"]')).to_be_enabled()
    with page.expect_download() as download:
        page.get_by_role('link',name='Saved IS Narrow package ↓').click()
    download.value.save_as(tmp_path/'is-narrow-package.json')
    package=json.loads((tmp_path/'is-narrow-package.json').read_text())
    assert package['state']['broad_trial']==2 and package['state']['selected_trials']==[2,3]
    assert len(package['state']['selection'])==2 and package['state']['selection'][0]['admission']['family_size']==10
    assert package['policy']['version']=='is-narrow-v4'
    assert package['state']['selection'][0]['admission']['plateau']['passed']
    assert page.request.get(portal['url']+'/api/jobs/backtest_batch/'+second['id']).json()['links'][0]['label']=='Open IS Narrow'
    (tmp_path/'SYNTHETIC-source.csv').write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset['id']+'/csv').body())
    (tmp_path/'narrow-results.json').write_text(json.dumps(page.request.get(prefix+'/narrow/results?broad_trial=2').json(),indent=2))
    (tmp_path/'journey.json').write_text(json.dumps({'workflow_id':workflow['id'],'dataset_id':dataset['id'],
        'broad_trials':[1,2],'narrow_trials_per_branch':4,'attempted_family_size':10,
        'chosen_narrow_trials':{'1':[2,3],'2':[2,3]},'first_branch_confirmed_before_second_grid':True,
        'first_branch_frozen_family_size':6,'expected_oos_navigation':'ready',
        'plateau_policy':'is-narrow-v4','tested_hold_step':2,'expected_neighbor_retention_pct':100,
        'expected_disabled_boundary_trials':[1,4],
        'synthetic':True,'mc_parity':'Manual attestation in synthetic fixture; no external MultiCharts comparison',
        'server':'Stopped by fixture teardown.'},indent=2))
    page.locator('#narrow-results tr[data-trial="2"] .broad-row-criteria summary').click()
    page.screenshot(path=str(tmp_path/'is-narrow-portal.png'),full_page=True)
    if destination:=os.environ.get('ALPHAQUEST_NARROW_EVIDENCE_DIR'):
        folder=Path(destination);folder.mkdir(parents=True,exist_ok=True)
        for name in ('SYNTHETIC-source.csv','narrow-results.json','is-narrow-package.json','journey.json','is-narrow-portal.png'):
            shutil.copyfile(tmp_path/name,folder/name)


def test_narrow_portal_explicit_local_refinement_and_saved_result(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=40) as client:
        dataset,workflow,broad=narrow_workflow(client,refinement=True)
    prefix=portal['url']+'/api/campaign-workflows/'+workflow['id']
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/is_narrow')
    playwright.expect(page.locator('#narrow-chooser')).to_be_visible()
    refine=page.get_by_role('checkbox',name='Refine Hold minutes in Narrow')
    playwright.expect(refine).not_to_be_checked()
    playwright.expect(page.get_by_label('Hold minutes start',exact=True)).to_be_disabled()
    refine.check()
    page.get_by_label('Hold minutes start',exact=True).fill('18')
    page.get_by_label('Hold minutes end',exact=True).fill('21')
    page.get_by_label('Hold minutes step',exact=True).fill('1')
    page.locator('#narrow-preview').click()
    playwright.expect(page.locator('#narrow-count')).to_have_text('4 iterations · IS only')
    page.locator('#narrow-run').click()
    playwright.expect(page.locator('#narrow-progress')).to_contain_text('COMPLETE · 4 / 4 trials',timeout=30000)
    playwright.expect(page.locator('#narrow-results tbody tr')).to_have_count(4)
    assert page.locator('#narrow-results thead th.optimization-frozen-column').evaluate_all('items => items.map(el=>el.dataset.column)')==['select','trial','param.hold_minutes']
    playwright.expect(page.locator('#narrow-results th[data-column="param.contracts"]')).to_be_hidden()
    page.reload()
    playwright.expect(refine).to_be_checked()
    playwright.expect(page.get_by_label('Hold minutes start',exact=True)).to_have_value('18')
    playwright.expect(page.get_by_label('Hold minutes end',exact=True)).to_have_value('21')
    results=page.request.get(prefix+'/narrow/results?broad_trial=1').json()
    eligible=next(row['trial'] for row in results['items'] if row['qualifies'])
    with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/narrow/selection')):
        page.get_by_role('checkbox',name=f'Select Narrow trial {eligible}').check()
    playwright.expect(page.locator('#narrow-confirm')).to_be_enabled()
    page.locator('#narrow-confirm').click()
    playwright.expect(page.locator('#narrow-confirm')).to_have_text('Narrow choices confirmed')
    page.reload()
    playwright.expect(page.locator('#mechanic-phases [data-phase="oos"]')).to_be_enabled()
    with page.expect_download() as download:
        page.get_by_role('link',name='Saved IS Narrow package ↓').click()
    download.value.save_as(tmp_path/'refined-narrow-package.json')
    package=json.loads((tmp_path/'refined-narrow-package.json').read_text())
    assert package['job']['research']['refined_broad_parameters']==['hold_minutes']
    assert package['state']['selected_trials']==[eligible]
    (tmp_path/'SYNTHETIC-source.csv').write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset['id']+'/csv').body())
    (tmp_path/'refined-narrow-results.json').write_text(json.dumps(results,indent=2))
    (tmp_path/'journey.json').write_text(json.dumps({'workflow_id':workflow['id'],'dataset_id':dataset['id'],
        'broad_job_id':broad['id'],'narrow_job_id':package['job']['id'],
        'selected_broad_hold_minutes':20,'refined_narrow_hold_minutes':[18,19,20,21],
        'chosen_narrow_trial':eligible,'expected_oos_navigation':'ready',
        'synthetic':True,'mc_parity':'Manual attestation in synthetic fixture; no external MultiCharts comparison',
        'server':'Stopped by fixture teardown.'},indent=2))
    page.screenshot(path=str(tmp_path/'refined-narrow-portal.png'),full_page=True)
    if destination:=os.environ.get('ALPHAQUEST_REFINEMENT_EVIDENCE_DIR'):
        folder=Path(destination);folder.mkdir(parents=True,exist_ok=True)
        for name in ('SYNTHETIC-source.csv','refined-narrow-results.json','refined-narrow-package.json','journey.json','refined-narrow-portal.png'):
            shutil.copyfile(tmp_path/name,folder/name)


def test_tested_grid_corner_qualifies_without_additional_backtests(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=40) as client:
        dataset,workflow,_=narrow_workflow(client)
        prefix='/api/campaign-workflows/'+workflow['id']
        body=narrow_grid(1)
        body['parameter_ranges']['green_bar_count']=dict(start=2,end=3,step=1)
        preview=client.post(prefix+'/narrow/preview',json=body).json()
        assert preview['total_trials']==8
        response=client.post(prefix+'/narrow/run',json=dict(body,revision=preview['revision'],preview_token=preview['preview_token']))
        assert response.status_code==202,response.text
        job=wait_job(client,response.json()['id'])
        before=client.get('/api/jobs').json()['total']
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/is_narrow?broad_trial=1')
    playwright.expect(page.locator('#narrow-results tbody tr')).to_have_count(8)
    # Green=3 / hold=14 has two available neighbors: green=2 / hold=14
    # and green=3 / hold=16. Both numeric axes are at a boundary.
    corner=page.locator('#narrow-results tr[data-trial="5"] .broad-row-criteria')
    playwright.expect(corner).to_contain_text('Qualified · 7 / 7 checks passed')
    corner.locator('summary').click()
    playwright.expect(corner).to_contain_text('One-sided boundary assessment: Green bar count, Hold minutes')
    playwright.expect(corner).to_contain_text('Tested spacing: Green bar count 1, Hold minutes 2')
    playwright.expect(corner).to_contain_text('net 16560.00 CU')
    playwright.expect(corner).to_contain_text('retains 176.92%')
    playwright.expect(page.get_by_role('checkbox',name='Select Narrow trial 5')).to_be_enabled()
    with httpx.Client(base_url=portal['url'],timeout=40) as client:
        results=client.get(prefix+'/narrow/results',params={'broad_trial':1}).json()
        assert client.get('/api/jobs').json()['total']==before
        assert results['items'][4]['metrics']['total_net_pnl']=='9360.00'
        assert results['items'][0]['metrics']['total_net_pnl']=='16560.00'
        assert results['items'][0]['admission']['plateau']['status']=='failed'
    if destination:=os.environ.get('ALPHAQUEST_NARROW_EVIDENCE_DIR'):
        folder=Path(destination)/'boundary';folder.mkdir(parents=True,exist_ok=True)
        (folder/'results.json').write_text(json.dumps(results,indent=2))
        (folder/'journey.json').write_text(json.dumps(dict(workflow_id=workflow['id'],dataset_id=dataset['id'],
            job_id=job['id'],native_trials=8,job_count_before=before,job_count_after=before,
            passing_corner_trial=5,expected_corner_net=9360,expected_green_2_neighbor_net=16560,
            one_sided_parameters=['green_bar_count','hold_minutes'],synthetic=True,
            server='Stopped by fixture teardown.'),indent=2))
        boundary_note=corner.get_by_text('One-sided boundary assessment: Green bar count, Hold minutes. Only available tested sides are used.',exact=True)
        boundary_note.scroll_into_view_if_needed()
        playwright.expect(boundary_note).to_be_in_viewport()
        page.screenshot(path=str(folder/'portal.png'),full_page=True)

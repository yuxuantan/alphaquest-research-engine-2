"""Actual background validation → leave page/reload → history → saved results."""
import json
import time
from threading import Event

import httpx
from test_backtests_browser import browser, page, portal, playwright
from test_campaign_mechanics import create_workflow


def test_running_job_survives_navigation_and_history_links_to_results(page,portal,tmp_path,monkeypatch):
    from alphaquest import backtest_api
    original=backtest_api.run_backtest
    entered,release=Event(),Event()
    def gated(*args,**kwargs):
        entered.set()
        assert release.wait(15),'Test did not release its paused real backtest'
        return original(*args,**kwargs)
    monkeypatch.setattr(backtest_api,'run_backtest',gated)
    with httpx.Client(base_url=portal['url'],timeout=30) as client:
        dataset,body,workflow=create_workflow(client)
    page.goto(portal['url']+'/#jobs')
    playwright.expect(page.locator('#jobs-list-status')).to_contain_text('No jobs match')
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/mechanic_validation')
    try:
        with page.expect_response(lambda r:'/run?background=true' in r.url) as submitted:
            page.locator('#mechanic-run').click()
        assert submitted.value.status==202
        assert entered.wait(5)
        # This job owns server work after the launch request has already returned.
        page.get_by_role('link',name='Job history',exact=True).click()
        playwright.expect(page.locator('#jobs-rows tr')).to_have_count(1)
        playwright.expect(page.locator('#jobs-rows')).to_contain_text('running')
        running=page.request.get(portal['url']+'/api/jobs?status=active').json()
        assert running['total']==1
        job_id=running['items'][0]['id']
        assert running['items'][0]['progress']['stage']=='preparing'
        (tmp_path/'running-jobs.json').write_text(json.dumps(running,indent=2))
        page.evaluate('scrollTo(0,0)');page.screenshot(path=str(tmp_path/'01-running-history.png'),full_page=True)
        page.get_by_role('link',name='View progress / details',exact=True).click()
        playwright.expect(page.locator('#job-progress')).to_contain_text('preparing')
        page.reload()
        playwright.expect(page.locator('#jobs-detail-content')).to_contain_text('running')
        page.screenshot(path=str(tmp_path/'02-running-detail.png'),full_page=True)
    finally:
        release.set()
    playwright.expect(page.locator('#jobs-detail-content')).to_contain_text('Completed',timeout=15000)
    playwright.expect(page.locator('#job-progress')).to_contain_text('24 / 24 bars')
    completed=page.request.get(portal['url']+'/api/jobs/mechanic_validation/'+job_id).json()
    assert completed['review_status']=='review_required'
    (tmp_path/'completed-job.json').write_text(json.dumps(completed,indent=2))
    page.screenshot(path=str(tmp_path/'03-completed-detail.png'),full_page=True)
    page.get_by_role('link',name='Open mechanic validation',exact=True).click()
    playwright.expect(page.locator('#mechanic-trades tbody tr')).to_have_count(5)
    playwright.expect(page.locator('#mechanic-confirm')).to_be_disabled()
    result=page.request.get(portal['url']+'/api/campaign-workflows/'+workflow['id']).json()
    assert float(result['report']['summary']['total_net_pnl'])==78
    assert page.request.get(portal['url']+'/api/backtests').json()['total']==1
    # Native batch jobs join the same history without listing every trial twice.
    batch_body=dict(body,method='exhaustive',workers=1,automatic_prop=False,parameter_ranges={
        'green_bar_count':dict(start=3,end=3,step=0),'hold_minutes':dict(start=20,end=20,step=0),'contracts':dict(start=1,end=2,step=1)})
    response=page.request.post(portal['url']+'/api/backtests',data=batch_body)
    assert response.status==202,response.text()
    batch_id=response.json()['id'];deadline=time.monotonic()+15
    while True:
        batch=page.request.get(portal['url']+'/api/backtests/batches/'+batch_id).json()
        if batch['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert batch['status']=='complete',batch
    page.get_by_role('link',name='Job history',exact=True).click()
    playwright.expect(page.locator('#jobs-rows tr')).to_have_count(2)
    page.locator('#jobs-filter-status').select_option('completed')
    playwright.expect(page.locator('#jobs-rows tr')).to_have_count(2)
    page.locator('#jobs-filter-kind').select_option('mechanic_validation')
    playwright.expect(page.locator('#jobs-rows tr')).to_have_count(1)
    page.locator('#jobs-search').fill('no-such-job');page.get_by_role('button',name='Search',exact=True).click()
    playwright.expect(page.locator('#jobs-list-status')).to_contain_text('No jobs match')
    page.locator('#jobs-search').fill('');page.get_by_role('button',name='Search',exact=True).click()
    playwright.expect(page.locator('#jobs-rows tr')).to_have_count(1)
    page.locator('#jobs-filter-kind').select_option('all')
    playwright.expect(page.locator('#jobs-rows tr')).to_have_count(2)
    page.screenshot(path=str(tmp_path/'04-completed-history.png'),full_page=True)
    jobs=page.request.get(portal['url']+'/api/jobs?status=completed').json()
    assert jobs['total']==2
    (tmp_path/'completed-jobs.json').write_text(json.dumps(jobs,indent=2))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(tmp_path/'05-mobile.png'),full_page=True)
    page.locator(f'#jobs-rows tr[data-job-id="{batch_id}"]').get_by_role('link',name='View results',exact=True).click()
    page.get_by_role('link',name='Open batch progress / results',exact=True).click()
    playwright.expect(page.locator('#optimization-status')).to_contain_text('COMPLETE')
    assert page.request.get(portal['url']+'/api/backtests').json()['total']==3
    (tmp_path/'workflow.json').write_text(json.dumps(result,indent=2))
    (tmp_path/'SYNTHETIC-source.csv').write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset['id']+'/csv').body())
    (tmp_path/'journey.json').write_text(json.dumps({'synthetic':True,'validation_job_id':job_id,'workflow_id':workflow['id'],'batch_id':batch_id,'expected_native_net':78,'expected_validation_bars':24,'expected_history_jobs':2,'expected_saved_backtests':3,'background_submission_status':202,'navigation_and_reload_during_run':True,'gate_was_held_before_real_replay':'Test synchronization only; no fabricated measured progress or outcomes.','server':'Stopped by fixture teardown.'},indent=2))

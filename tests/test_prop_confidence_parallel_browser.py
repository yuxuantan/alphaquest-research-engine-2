"""Normal one-Run product journey: live multicore progress in both real pages."""
import json
import os
from pathlib import Path
import shutil
import time
from zipfile import ZipFile

import httpx
from test_backtests_browser import browser,page,playwright
from test_prop_oos_qualification_browser import qualification_portal


def test_parallel_confidence_progress_and_durable_reports(page,qualification_portal,tmp_path):
    portal=qualification_portal;base=portal['url'];source=portal['source']
    page.goto(base+'/#backtests/report/'+source['source_backtest_id'])
    playwright.expect(page.locator('#report-prop-setup')).to_be_visible(timeout=30000)
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-sim-source')).to_have_value('0',timeout=30000)
    page.locator('#prop-sim-profile').select_option('lucidflex-50k')
    for phase in ('evaluation','funded'):
        page.locator(f'#prop-sim-{phase}_minimum_micros').fill('9')
        page.locator(f'#prop-sim-{phase}_maximum_micros').fill('10')
    page.locator('#prop-sim-simulations').fill('8')
    page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'configuration.png'))
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/prop-sim')) as reply:
        page.locator('#prop-sim-run').click()
    saved=reply.value.json();assert reply.value.status==202
    current=page.locator('#prop-sim-evaluation-validation .prop-confidence-progress')
    playwright.expect(current).to_contain_text('4 workers',timeout=90000)
    playwright.expect(current.get_by_role('progressbar')).to_be_visible()
    playwright.expect(current).to_contain_text('remaining for this size')
    current.screenshot(path=str(tmp_path/'prop-sim-progress.png'))
    with httpx.Client(base_url=base,timeout=180) as client:
        saved=client.get('/api/prop-sim/'+saved['id']).json()
        aid=saved['automation']['phases']['evaluation']['oos_analysis_id']
        first=client.get('/api/jobs/prop_analysis/'+aid).json()
        page.goto(base+'/#jobs/prop_analysis/'+aid)
        confidence=page.locator('#jobs-detail-content .prop-confidence-progress')
        playwright.expect(confidence).to_contain_text('4 workers',timeout=30000)
        playwright.expect(confidence.get_by_role('progressbar')).to_be_visible()
        confidence.screenshot(path=str(tmp_path/'job-history-progress.png'))
        deadline=time.monotonic()+180;observed=[first]
        while True:
            saved=client.get('/api/prop-sim/'+saved['id']).json()
            job=client.get('/api/jobs/prop_analysis/'+aid).json();observed.append(job)
            if all(s['stage'] in ('complete','error','no_eligible_candidates') for s in saved['automation']['phases'].values()):break
            assert time.monotonic()<deadline,saved
            time.sleep(.25)
        assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
        assert len({j['progress'].get('completed') for j in observed})>1
        (tmp_path/'observed-job-progress.json').write_text(json.dumps(observed,indent=2))
    page.goto(base+'/#prop-sim?analysis='+saved['id'])
    reports={}
    for phase in ('evaluation','funded'):
        panel=page.locator('#prop-sim-'+phase+'-validation')
        playwright.expect(panel.locator('.prop-sim-auto-status')).to_contain_text('Workflow: complete',timeout=30000)
        assert panel.locator('.prop-confidence-progress').inner_text()==''
        with page.expect_download() as download:
            panel.locator('.prop-sim-current-assessment').get_by_role('link',name='Assessment evidence ZIP ↓',exact=True).click()
        path=tmp_path/(phase+'-oos.zip');download.value.save_as(path)
        with ZipFile(path) as z:report=json.loads(z.read('report.json'))
        data,=report['calculations']['qualification_bootstrap'];row,=report['calculations']['candidates']
        assert data['execution']['workers_used']==4 and len(data['execution']['worker_pids'])>=2
        assert data['unique_histories_evaluated']==[1,1]
        assert len(data['replicates'])==10000 and row['configuration']['micros']==9
        assert all(c['lower']==c['upper']==1. for c in row['prop_qualification']['checks'])
        assert row['prop_qualification']['status']=='GO' and row['prop_qualification']['forward_execution']['status']=='PENDING'
        assert row['metrics']['cost_per_funded']==80.5 if phase=='evaluation' else row['metrics']['expected_funded_cash_payouts_within_horizon']==9000
        panel.screenshot(path=str(tmp_path/(phase+'-complete.png')))
        reports[phase]=dict(id=report['id'],execution=data['execution'],distinct_histories=data['unique_histories_evaluated'])
    page.reload();playwright.expect(page.locator('#prop-sim-funded-validation .prop-sim-auto-status')).to_contain_text('Workflow: complete',timeout=30000)
    page.set_viewport_size(dict(width=390,height=844));page.locator('#prop-sim-funded-validation').screenshot(path=str(tmp_path/'mobile.png'))
    assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,profile='lucidflex-50k',simulation=saved,
        source=source,reports=reports,initial_run_clicks=1,followup_confirmation_clicks=0,
        server='Temporary test server stopped by fixture teardown',interpretation='Local arithmetic and integration only; no provider or future performance claim.'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_PARALLEL_EVIDENCE_DIR'):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        for p in tmp_path.iterdir():
            if p.is_file() and p.suffix in ('.json','.png','.zip'):shutil.copyfile(p,target/p.name)


def test_stop_retry_restores_completed_refits_in_both_progress_pages(page,qualification_portal,tmp_path,request):
    """Normal stop/retry controls, complete 10k report, no checkpoint-only UI."""
    portal=qualification_portal;base=portal['url'];source=portal['source']
    page.goto(base+'/#backtests/report/'+source['source_backtest_id'])
    playwright.expect(page.locator('#report-prop-setup')).to_be_visible(timeout=30000)
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-sim-source')).to_have_value('0',timeout=30000)
    page.locator('#prop-sim-profile').select_option('lucidflex-50k')
    for phase in ('evaluation','funded'):
        for bound in ('minimum','maximum'):page.locator(f'#prop-sim-{phase}_{bound}_micros').fill('10')
    page.locator('#prop-sim-simulations').fill('8')
    page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/prop-sim')) as reply:page.locator('#prop-sim-run').click()
    saved=reply.value.json();assert reply.value.status==202
    def cleanup_active():
        with httpx.Client(base_url=base,timeout=30) as client:
            current_saved=client.get('/api/prop-sim/'+saved['id']).json()
            if any(s['stage'] in ('is_running','oos_running') for s in current_saved['automation']['phases'].values()):
                client.post('/api/prop-sim/'+saved['id']+'/cancel')
    request.addfinalizer(cleanup_active)
    current=page.locator('#prop-sim-evaluation-validation .prop-confidence-progress').first
    playwright.expect(current.get_by_role('progressbar')).to_be_visible(timeout=90000)
    with httpx.Client(base_url=base,timeout=180) as client:
        saved=client.get('/api/prop-sim/'+saved['id']).json();old=saved['automation']['phases']['evaluation']['oos_analysis_id']
        deadline=time.monotonic()+40
        while True:
            with portal['app'].state.prop_analyses.connect() as db:
                count=db.execute('SELECT count(*) FROM historical_refit_checkpoints WHERE analysis_id=?',(old,)).fetchone()[0]
            if count:break
            assert time.monotonic()<deadline
            time.sleep(.05)
        page.locator('#prop-sim-stop').click()
        while True:
            job=client.get('/api/jobs/prop_analysis/'+old).json()
            if job['status']=='cancelled':break
            assert time.monotonic()<deadline,job
            time.sleep(.05)
        playwright.expect(page.get_by_role('button',name='Retry incomplete phases',exact=True)).to_be_visible(timeout=30000)
        page.get_by_role('button',name='Retry incomplete phases',exact=True).click()
        playwright.expect(current).to_contain_text('restored from a verified checkpoint',timeout=90000)
        current.screenshot(path=str(tmp_path/'prop-sim-restored.png'))
        saved=client.get('/api/prop-sim/'+saved['id']).json();aid=saved['automation']['phases']['evaluation']['oos_analysis_id'];assert aid!=old
        page.goto(base+'/#jobs/prop_analysis/'+aid)
        progress=page.locator('#jobs-detail-content .prop-confidence-progress')
        playwright.expect(progress).to_contain_text('restored from a verified checkpoint',timeout=30000)
        progress.screenshot(path=str(tmp_path/'job-history-restored.png'))
        deadline=time.monotonic()+180
        while True:
            saved=client.get('/api/prop-sim/'+saved['id']).json()
            if all(s['stage'] in ('complete','error','cancelled','no_eligible_candidates') for s in saved['automation']['phases'].values()):break
            assert time.monotonic()<deadline,saved
            time.sleep(.15)
        assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
        state=saved['automation']['phases']['evaluation']
        report=client.get(base+f"/api/prop-sim/{saved['id']}/validation/evaluation/{state['oos_request_id']}").json()
        data,=report['calculations']['qualification_bootstrap'];row,=report['calculations']['candidates']
        assert data['execution']['reused_resamples']>0 and len(data['replicates'])==10000
        assert [r['replicate'] for r in data['replicates']]==list(range(10000))
        assert row['prop_qualification']['status']=='GO'
        assert row['metrics']['cost_per_funded']==80.5
        with portal['app'].state.prop_analyses.connect() as db:assert db.execute('SELECT count(*) FROM historical_refit_checkpoints WHERE analysis_id=?',(aid,)).fetchone()[0]==0
        response=client.get(base+f'/api/prop-analyses/{aid}/downloads/analysis.zip');assert response.status_code==200
        (tmp_path/'evaluation-resumed.zip').write_bytes(response.content)
        (tmp_path/'resume-journey.json').write_text(json.dumps(dict(synthetic=True,simulation=saved['id'],stopped_job=old,resumed_job=aid,checkpoint_count_before_stop=count,execution=data['execution'],historical_replicates=10000,qualification=row['prop_qualification'],server='Temporary server stopped by fixture teardown'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_PARALLEL_EVIDENCE_DIR'):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        for p in tmp_path.iterdir():
            if p.is_file() and p.suffix in ('.json','.png','.zip'):shutil.copyfile(p,target/p.name)

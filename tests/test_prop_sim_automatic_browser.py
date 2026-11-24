"""One initial Run -> both IS searches -> automatic freeze -> both OOS reports."""
import json
from copy import deepcopy
import os
from pathlib import Path
import shutil
import time
from zipfile import ZipFile

import httpx
import pytest
from test_backtests_browser import browser,page,playwright
from test_prop_oos_qualification_browser import qualification_portal


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_one_run_finishes_all_four_simulations_after_navigation(page,qualification_portal,tmp_path,profile):
    base=qualification_portal['url'];source=qualification_portal['source']
    page.goto(base+'/#backtests/report/'+source['source_backtest_id'])
    playwright.expect(page.locator('#report-prop-setup')).to_be_visible(timeout=30000)
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-sim-source')).to_have_value('0',timeout=30000)
    page.locator('#prop-sim-profile').select_option(profile)
    for phase in ('evaluation','funded'):
        page.locator(f'#prop-sim-{phase}_minimum_micros').fill('9')
        page.locator(f'#prop-sim-{phase}_maximum_micros').fill('10')
    page.locator('#prop-sim-simulations').fill('8')
    page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    source_checks=[];page.on('request',lambda r:source_checks.append(r.url) if r.method=='POST' and r.url.endswith('/api/prop-sim/check') else None)
    playwright.expect(page.locator('#prop-sim-run')).to_be_enabled()
    page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'configuration.png'))
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/prop-sim')) as response:page.locator('#prop-sim-run').click()
    saved=response.value.json();assert response.value.status==202
    assert saved['configuration']['automatic'] is True
    assert saved['automation']['selection_identity']['policy']['evaluation_maximum']==3
    assert source_checks==[] # Checking is integrated into Run, not a required extra click.
    page.get_by_role('navigation',name='Main navigation',exact=True).get_by_role('link',name='Dataset',exact=True).click()
    with httpx.Client(base_url=base,timeout=180) as client:
        deadline=time.monotonic()+180
        while True:
            saved=client.get('/api/prop-sim/'+saved['id']).json()
            states=saved['automation']['phases']
            if all(s['stage'] in ('complete','error','no_eligible_candidates') for s in states.values()):break
            assert time.monotonic()<deadline,saved
            time.sleep(.15)
        assert all(s['stage']=='complete' for s in states.values()),saved
    page.goto(base+'/#prop-sim?analysis='+saved['id'])
    reports={}
    for phase in ('evaluation','funded'):
        panel=page.locator('#prop-sim-'+phase+'-validation')
        playwright.expect(panel.locator('.prop-sim-auto-status')).to_contain_text('Workflow: complete',timeout=60000)
        assert panel.get_by_role('button',name='Freeze selected sizes',exact=True).is_hidden()
        assert panel.get_by_role('button',name='Run OOS qualification',exact=True).count()==0
        assert page.locator('#prop-sim-'+phase+'-table input[type=checkbox]').count()==0
        is_report=page.request.get(base+f"/api/prop-sim/{saved['id']}/results/{phase}").json()
        (tmp_path/(phase+'-is.json')).write_text(json.dumps(is_report,indent=2))
        state=states[phase]
        assert [c['micros'] for c in state['selection']['candidates']]==[9]
        assert len(state['selection']['candidates'][0]['roles'])==(3 if phase=='evaluation' else 2)
        playwright.expect(panel.locator('.prop-sim-current-assessment table')).to_have_count(1)
        assert panel.locator('.prop-sim-auto-status').inner_text().count('9 MNQ')==1
        panel.screenshot(path=str(tmp_path/(phase+'-complete.png')))
        current=panel.locator('.prop-sim-current-assessment')
        conclusion=page.locator('#prop-sim-'+phase+'-conclusion')
        playwright.expect(conclusion).to_contain_text('Historical checks passed · paper review next')
        playwright.expect(conclusion).to_contain_text('Campaign checks passed at assessment time')
        playwright.expect(current.get_by_role('columnheader',name='Next step',exact=True)).to_be_visible()
        playwright.expect(current.get_by_role('cell',name='Paper execution review',exact=True)).to_be_visible()
        with page.expect_download() as download:current.get_by_role('link',name='Assessment evidence ZIP ↓',exact=True).click()
        filename=tmp_path/(phase+'-oos.zip');download.value.save_as(filename)
        with ZipFile(filename) as z:report=json.loads(z.read('report.json'))
        row,=report['calculations']['candidates'];assert row['configuration']['micros']==9
        assert report['assessment']['prop_sim_review']['automatic_selection']==state['selection']
        assert row['prop_qualification']['status']=='GO'
        assert row['prop_qualification']['forward_execution']['status']=='PENDING'
        assert all(c['lower']==c['upper']==1. for c in row['prop_qualification']['checks'])
        if phase=='funded':
            assert row['metrics']['expected_funded_cash_payouts_within_horizon']==sum(p['cash_received'] for p in row['paths'])/8
            data,=report['calculations']['qualification_bootstrap']
            preparation=data['execution']['funded_preparation']
            assert preparation['version']=='dated-funded-preparation-v1'
            assert 0<preparation['maximum_accounted_bytes']<=preparation['budget_bytes_per_worker']==32*1024*1024
            assert len(data['replicates'])==10000
            # Independent constant-day cash oracle: every account reaches all
            # payout caps in the 90-day horizon, including the receipt lag.
            assert row['metrics']['expected_funded_cash_payouts_within_horizon']==(13000 if profile=='apex-50k-eod' else 9000)
        assert len(page.request.get(base+f"/api/prop-sim/{saved['id']}/validation/{phase}").json()['assessments'])==1
        summary=page.request.get(base+f"/api/prop-sim/{saved['id']}/validation/{phase}/{state['oos_request_id']}?summary=true").json()
        (tmp_path/(phase+'-summary.json')).write_text(json.dumps(summary,indent=2))
        reports[phase]=dict(analysis_id=report['id'],selection=state['selection'],metrics=row['metrics'])
    page.reload()
    playwright.expect(page.locator('#prop-sim-funded-validation .prop-sim-auto-status')).to_contain_text('Workflow: complete',timeout=60000)
    page.locator('#prop-sim-funded-conclusion').get_by_role('button',name='Open paper execution review',exact=True).click()
    playwright.expect(page.locator('#prop-sim-funded-validation').get_by_role('button',name='Configure paper observation',exact=True)).to_be_visible(timeout=30000)
    page.set_viewport_size(dict(width=390,height=844))
    page.locator('#prop-sim-funded-validation').screenshot(path=str(tmp_path/'mobile.png'))
    assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
    (tmp_path/'simulation.json').write_text(json.dumps(saved,indent=2))
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,profile=profile,source=source,
        initial_clicks=['Run IS and OOS'],required_followup_actions=0,source_checked_inside_run=True,
        navigated_away_during_work=True,automatic_candidate_micros=[9],reports=reports,
        interpretation='Local arithmetic/integration demonstration only; no real paper execution, live readiness or future performance claim.',
        server='Temporary server stopped by fixture teardown.'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_AUTOMATIC_EVIDENCE_DIR'):
        target=Path(destination)/profile;target.mkdir(parents=True,exist_ok=True)
        for p in tmp_path.iterdir():
            if p.is_file() and p.suffix in ('.json','.png','.zip'):shutil.copyfile(p,target/p.name)
        if library:=os.environ.get('ALPHAQUEST_PROP_PREPARATION_SAVE_LIBRARY'):
            shutil.copytree(qualification_portal['root'],Path(library)/profile,dirs_exist_ok=True)


def test_saved_conclusions_distinguish_inconclusive_failure_forward_and_history(page,qualification_portal,tmp_path):
    """Normal sealed run, then display-only boundary fixtures; no verdict rewrite."""
    from test_prop_sim import body
    from test_prop_sim_automatic import wait_automatic
    portal=qualification_portal;base=portal['url']
    with httpx.Client(base_url=base,timeout=180) as client:
        config=dict(body(portal['source']),automatic=True,simulations=8,
            evaluation_minimum_micros=10,evaluation_maximum_micros=10,
            funded_minimum_micros=10,funded_maximum_micros=10,maximum_funded_breach_probability=None)
        reply=client.post('/api/prop-sim',json=config);assert reply.status_code==202,reply.text
        saved=wait_automatic(client,reply.json()['id'])
        assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
        prefix=f"/api/prop-sim/{saved['id']}/validation/funded"
        metadata=client.get(prefix).json();attempt=metadata['assessments'][0]
        original=client.get(prefix+'/'+attempt['request_id']+'?summary=true').json()
    seal_before=portal['app'].state.prop_analyses.fingerprint(attempt['analysis_id'])
    display={'name':'inconclusive','summary':None};posts=[]
    def summary(route):
        if '?summary=true' in route.request.url:route.fulfill(json=display['summary'])
        else:route.fallback()
    def meta(route):
        if route.request.method!='GET':route.fallback();return
        value=deepcopy(metadata)
        if display['name']=='historical':value.update(current_assessments={},numerical_implementation_compatible=False)
        if display['name']=='running':
            for a in value['assessments']:
                if a['request_id']==attempt['request_id']:a.update(status='running',analysis=dict(a.get('analysis') or {},status='running',progress='SYNTHETIC display-only progress'))
        route.fulfill(json=value)
    page.route('**'+prefix+'/*?summary=true',summary);page.route('**'+prefix,meta)
    page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    observations=[]
    for case in ['inconclusive','precision','evidence','failed','mixed','forward_failed','forward_passed','historical','running','unassessed']:
        display['name']=case;study=deepcopy(original);row=study['calculations']['candidates'][0];q=row['prop_qualification']
        if case in ('inconclusive','precision','evidence'):
            q['status']='INSUFFICIENT_EVIDENCE';q['inner_precision_ok']=case=='evidence'
            if case=='inconclusive':q['checks'][0].update(status='INSUFFICIENT_EVIDENCE',point_ratio=.8,lower=.13,upper=3.64)
            if case=='evidence':q['evidence'][0].update(actual=4,passed=False)
        elif case=='failed':
            q['status']='NO_GO';q['checks'][0].update(status='FAIL',point_ratio=.4,lower=.1,upper=.6)
        elif case=='mixed':
            other=deepcopy(row);other['configuration']['micros']=11;other['prop_qualification']['status']='INSUFFICIENT_EVIDENCE'
            other['prop_qualification']['checks'][0].update(status='INSUFFICIENT_EVIDENCE',lower=.4,upper=1.2)
            study['calculations']['candidates'].append(other)
        elif case.startswith('forward_'):
            q['forward_execution'].update(status='NO_GO' if case=='forward_failed' else 'GO',
                checks=[dict(label='Unexplained execution discrepancies',actual=1 if case=='forward_failed' else 0,required=0,passed=case!='forward_failed')])
        elif case=='unassessed':row.pop('prop_qualification')
        display['summary']=study
        page.goto(base+'/#prop-sim?analysis='+saved['id']);page.reload()
        conclusion=page.locator('#prop-sim-funded-conclusion')
        expected=('Hold live deployment · qualification inconclusive' if case in ('inconclusive','precision','evidence') else
            'Do not deploy these sizes · assessment failed' if case=='failed' else
            'Hold live deployment · resolve execution issues' if case=='forward_failed' else
            'Paper checks passed · deployment review next' if case=='forward_passed' else
            'Hold live deployment · historical assessment only' if case=='historical' else
            'Assessment running · hold live deployment' if case=='running' else
            'Qualification pending · hold live deployment' if case=='unassessed' else
            'Historical checks passed · paper review next')
        playwright.expect(conclusion.get_by_role('heading',name=expected,exact=True)).to_be_visible(timeout=60000)
        if case not in ('running','unassessed'):playwright.expect(conclusion).to_contain_text('Campaign checks passed at assessment time')
        if case in ('inconclusive','precision'):
            playwright.expect(conclusion).to_contain_text('Account-simulation precision is insufficient')
            playwright.expect(conclusion).to_contain_text('does not automatically update this saved OOS verdict')
        if case=='inconclusive':
            playwright.expect(conclusion).to_contain_text('historical interval [0.13, 3.64]')
            playwright.expect(conclusion).to_contain_text('inconclusive, not a demonstrated failure')
        if case=='evidence':playwright.expect(conclusion).to_contain_text('Complete OOS calendar months: 4; required 12')
        if case=='mixed':
            playwright.expect(conclusion).to_contain_text('Other frozen sizes remain on hold or rejected')
            playwright.expect(conclusion).to_contain_text('1 historical GO · 1 inconclusive')
        if case in ('inconclusive','failed','mixed','historical'):conclusion.screenshot(path=str(tmp_path/(case+'.png')))
        if case=='inconclusive':
            page.set_viewport_size(dict(width=390,height=844));conclusion.screenshot(path=str(tmp_path/'mobile.png'))
            assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
            page.set_viewport_size(dict(width=1440,height=1100))
        assert conclusion.get_by_role('button',name='Open paper execution review',exact=True).count()==(1 if case in ('mixed','forward_failed','forward_passed') else 0)
        observations.append(dict(display_only_fixture=case,title=expected,text=conclusion.inner_text()))
    assert posts==[],posts
    assert portal['app'].state.prop_analyses.fingerprint(attempt['analysis_id'])==seal_before
    with httpx.Client(base_url=base,timeout=180) as client:
        assert client.get(prefix+'/'+attempt['request_id']+'?summary=true').json()==original
        assert len(client.get(prefix).json()['assessments'])==len(metadata['assessments'])
    (tmp_path/'conclusion-boundaries.json').write_text(json.dumps(dict(synthetic=True,display_only_fixtures=True,
        saved_report_unchanged=True,new_jobs_from_display=0,cases=observations),indent=2))

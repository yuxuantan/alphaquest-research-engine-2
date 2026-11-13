"""One initial Run -> both IS searches -> automatic freeze -> both OOS reports."""
import json
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
        with page.expect_download() as download:current.get_by_role('link',name='Assessment evidence ZIP ↓',exact=True).click()
        filename=tmp_path/(phase+'-oos.zip');download.value.save_as(filename)
        with ZipFile(filename) as z:report=json.loads(z.read('report.json'))
        row,=report['calculations']['candidates'];assert row['configuration']['micros']==9
        assert report['assessment']['prop_sim_review']['automatic_selection']==state['selection']
        assert row['prop_qualification']['status']=='GO'
        assert row['prop_qualification']['forward_execution']['status']=='PENDING'
        assert all(c['lower']==c['upper']==1. for c in row['prop_qualification']['checks'])
        if phase=='funded':assert row['metrics']['expected_funded_cash_payouts_within_horizon']==sum(p['cash_received'] for p in row['paths'])/8
        assert len(page.request.get(base+f"/api/prop-sim/{saved['id']}/validation/{phase}").json()['assessments'])==1
        summary=page.request.get(base+f"/api/prop-sim/{saved['id']}/validation/{phase}/{state['oos_request_id']}?summary=true").json()
        (tmp_path/(phase+'-summary.json')).write_text(json.dumps(summary,indent=2))
        reports[phase]=dict(analysis_id=report['id'],selection=state['selection'],metrics=row['metrics'])
    page.reload()
    playwright.expect(page.locator('#prop-sim-funded-validation .prop-sim-auto-status')).to_contain_text('Workflow: complete',timeout=60000)
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

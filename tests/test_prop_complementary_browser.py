"""One-click final-product demonstration with saved evidence and no refit jobs."""
import json
import os
from pathlib import Path
import shutil
import time

import httpx
import pytest
from test_backtests_browser import browser,page,playwright
from test_prop_oos_qualification_browser import qualification_portal


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_one_click_complementary_results_are_actionable_and_reopen(page,qualification_portal,tmp_path,profile):
    portal=qualification_portal;base=portal['url'];source=portal['source']
    page.goto(base+'/#backtests/report/'+source['source_backtest_id'])
    playwright.expect(page.locator('#report-prop-setup')).to_be_visible(timeout=30000)
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-sim-source')).to_have_value('0',timeout=30000)
    page.locator('#prop-sim-profile').select_option(profile)
    for phase in ('evaluation','funded'):
        page.locator(f'#prop-sim-{phase}_minimum_micros').fill('10')
        page.locator(f'#prop-sim-{phase}_maximum_micros').fill('10')
    page.locator('#prop-sim-simulations').fill('8')
    page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'configuration.png'))
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/prop-sim')) as response:
        page.locator('#prop-sim-run').click()
    saved=response.value.json();assert response.value.status==202
    page.get_by_role('navigation',name='Main navigation',exact=True).get_by_role('link',name='Dataset',exact=True).click()
    with httpx.Client(base_url=base,timeout=180) as client:
        deadline=time.monotonic()+240
        while True:
            saved=client.get('/api/prop-sim/'+saved['id']).json()
            states=saved['automation']['phases']
            if all(s['stage'] in ('complete','error','no_eligible_candidates') for s in states.values()):break
            assert time.monotonic()<deadline,saved
            time.sleep(.2)
        assert all(s['stage']=='complete' for s in states.values()),saved
    page.goto(base+'/#prop-sim?analysis='+saved['id']);outputs={}
    for phase in ('evaluation','funded'):
        panel=page.locator('#prop-sim-'+phase+'-validation')
        playwright.expect(panel.locator('.prop-evidence-findings')).to_be_visible(timeout=60000)
        playwright.expect(panel.locator('.prop-evidence-finding')).to_have_count(6)
        playwright.expect(panel).to_contain_text('IS / OOS account comparison')
        playwright.expect(panel).to_contain_text('5,000 paths per history and deadline')
        playwright.expect(panel).to_contain_text('not historical uncertainty or future-market confidence')
        conclusion=page.locator('#prop-sim-'+phase+'-conclusion')
        playwright.expect(conclusion).to_contain_text('paper execution review next')
        assert not panel.get_by_role('button',name='Freeze selected sizes',exact=True).is_visible()
        assert panel.get_by_role('button',name='Run OOS qualification',exact=True).count()==0
        panel.get_by_text('Stress scenarios · 5 predefined checks',exact=True).click()
        playwright.expect(panel).to_contain_text('OOS additional execution cost')
        panel.get_by_text('Chronological account starts · 24 observed windows',exact=True).click()
        playwright.expect(panel).to_contain_text('Overlapping windows are dependent scenarios')
        panel.screenshot(path=str(tmp_path/(phase+'-evidence.png')))
        state=saved['automation']['phases'][phase]
        url=f"/api/prop-sim/{saved['id']}/validation/{phase}"
        report=page.request.get(base+url+'/'+state['oos_request_id']).json()
        q=report['calculations']['candidates'][0]['prop_qualification']
        assert q['historical_replicates']==0 and q['version']=='prop-complementary-evidence-v2'
        assert q['status']=='GO' and q['forward_execution']['status']=='PENDING'
        assert len(report['calculations']['qualification_complementary'])==1
        assert len(page.request.get(base+url).json()['assessments'])==1
        (tmp_path/(phase+'-report.json')).write_text(json.dumps(report,indent=2))
        current=panel.locator('.prop-sim-current-assessment')
        with page.expect_download() as download:current.get_by_role('link',name='Assessment evidence ZIP ↓',exact=True).click()
        download.value.save_as(tmp_path/(phase+'-evidence.zip'))
        outputs[phase]=dict(analysis_id=report['id'],status=q['status'],findings=q['findings'])
    page.reload()
    playwright.expect(page.locator('#prop-sim-funded-validation .prop-evidence-findings')).to_be_visible(timeout=30000)
    page.set_viewport_size(dict(width=390,height=844))
    page.locator('#prop-sim-funded-validation').screenshot(path=str(tmp_path/'mobile.png'))
    assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,profile=profile,source=source,simulation=saved['id'],
        outputs=outputs,required_followup_actions=0,navigated_away_during_work=True,server='Temporary server stopped by fixture teardown.',
        interpretation='Actual existing product workflow and local calculation; synthetic market source, no forward evidence or future-confidence claim.'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_COMPLEMENTARY_BROWSER_EVIDENCE_DIR'):
        target=Path(destination)/profile;target.mkdir(parents=True,exist_ok=True)
        for p in tmp_path.iterdir():
            if p.is_file():shutil.copyfile(p,target/p.name)


def test_saved_evidence_reopen_and_actionable_display_boundaries(page,qualification_portal,tmp_path):
    """Reopen sealed evidence; boundary changes exist only in DOM test inputs."""
    portal=qualification_portal;base=portal['url']
    items=page.request.get(base+'/api/prop-sim').json()['items'];selected=None
    for item in items:
        prefix=f"/api/prop-sim/{item['id']}/validation/funded"
        data=page.request.get(base+prefix).json()
        rid=data.get('current_assessments',{}).get('qualification')
        if not rid:continue
        study=page.request.get(base+prefix+'/'+rid+'?summary=true').json()
        if study['calculations']['candidates'][0].get('prop_qualification',{}).get('version')=='prop-complementary-evidence-v2':
            selected=item;break
    if selected is None:pytest.skip('Requires a saved complementary evidence library from the API journey.')
    page.goto(base+'/#prop-sim?analysis='+selected['id'])
    panel=page.locator('#prop-sim-funded-validation')
    playwright.expect(panel.locator('.prop-evidence-findings')).to_be_visible(timeout=30000)
    playwright.expect(panel).to_contain_text('OOS evidence review')
    assert panel.get_by_text('10 MNQ · Paper execution review',exact=True).count()==1
    panel.get_by_text('Stress scenarios · 5 predefined checks',exact=True).click()
    playwright.expect(panel).to_contain_text('Baseline outcome retained')
    panel.screenshot(path=str(tmp_path/'final-funded.png'))
    row=study['calculations']['candidates'][0]
    # UI-only fixtures. The immutable saved server verdict is never rewritten.
    for status,expected in [('REVIEW_REQUIRED','investigate sensitivity'),('INSUFFICIENT_EVIDENCE','resolve evidence gaps'),('NO_GO','account fit not supported')]:
        view=json.loads(json.dumps(row));q=view['prop_qualification'];q['status']=status
        q['findings'][2].update(state='INSUFFICIENT' if status=='INSUFFICIENT_EVIDENCE' else 'WATCH',summary='SYNTHETIC display boundary',next_step='Inspect this specific finding.')
        model=page.evaluate('(r)=>window.propSimConclusion.describe([r],{current:true})',view)
        assert expected in model['title']
        assert not model['forwardEligible']
        assert any('Inspect this specific finding' in r for r in model['candidates'][0]['reasons'])
    view=json.loads(json.dumps(row));view['prop_qualification']['forward_execution']=dict(status='NO_GO',checks=[dict(label='Sizing parity',actual='Mismatch',required='Match',passed=False)])
    model=page.evaluate('(r)=>window.propSimConclusion.describe([r],{current:true})',view)
    assert model['title']=='Hold deployment · resolve execution issues'
    page.set_viewport_size(dict(width=390,height=844));panel.screenshot(path=str(tmp_path/'final-mobile.png'))
    assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
    if destination:=os.environ.get('ALPHAQUEST_COMPLEMENTARY_BROWSER_EVIDENCE_DIR'):
        target=Path(destination)/'final-reopen';target.mkdir(parents=True,exist_ok=True)
        for p in tmp_path.glob('*.png'):shutil.copyfile(p,target/p.name)

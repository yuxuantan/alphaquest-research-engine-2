"""Normal product: one OOS table, duplicate reuse and lazy historical versions."""
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import httpx
from test_backtests_browser import browser,page,playwright
from test_prop_oos_qualification_browser import qualification_portal
from test_prop_evaluation_validation import wait_assessment


def test_current_result_reopens_without_jobs_and_history_loads_on_demand(page,qualification_portal,tmp_path):
    portal=qualification_portal;base=portal['url'];source=portal['source']
    page.goto(base+'/#backtests/report/'+source['source_backtest_id'])
    playwright.expect(page.locator('#report-prop-setup')).to_be_visible(timeout=30000)
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-sim-source')).to_have_value('0',timeout=30000)
    for phase in ('evaluation','funded'):
        for bound in ('minimum','maximum'):page.locator(f'#prop-sim-{phase}_{bound}_micros').fill('10')
    page.locator('#prop-sim-simulations').fill('8')
    page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    page.locator('#prop-sim-check').click()
    playwright.expect(page.locator('#prop-sim-status')).to_contain_text('Source compatible',timeout=30000)
    with page.expect_response(lambda r:r.url.endswith('/api/prop-sim') and r.request.method=='POST') as reply:page.locator('#prop-sim-run').click()
    saved=reply.value.json();assert reply.value.status==202
    phase='funded';prefix=f"/api/prop-sim/{saved['id']}/validation/{phase}"
    playwright.expect(page.locator('#prop-sim-funded-progress')).to_contain_text('COMPLETE',timeout=90000)
    panel=page.locator('#prop-sim-funded-validation')
    page.get_by_label('Select 10 MNQ for funded validation',exact=True).check()
    panel.get_by_label('funded freeze rationale',exact=True).fill('SYNTHETIC retained result and lazy history demonstration')
    panel.get_by_role('button',name='Freeze selected sizes',exact=True).click()
    with page.expect_response(lambda r:r.url.endswith('/validation/funded') and r.request.method=='POST') as reply:panel.get_by_role('button',name='Run OOS qualification',exact=True).click()
    attempt=reply.value.json();assert reply.value.status==202
    current=panel.locator('.prop-sim-current-assessment')
    playwright.expect(current.locator('[role=status]')).to_contain_text('COMPLETE',timeout=180000)
    playwright.expect(panel.get_by_role('button',name='View OOS results',exact=True)).to_be_enabled(timeout=10000)
    assert panel.locator('.prop-sim-review-details').first.get_attribute('open') is None
    assert page.locator('#prop-sim-funded-results > .prop-sim-is-panel').get_attribute('open') is None
    assert panel.locator(':scope > details.prop-sim-policy').get_attribute('open') is None
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' and '/validation/funded' in r.url else None)
    panel.get_by_role('button',name='View OOS results',exact=True).click()
    assert posts==[]
    with httpx.Client(base_url=base,timeout=180) as client:
        before=client.get(prefix).json();count=len(before['assessments'])
        response=client.post(prefix,json=dict(request_id=uuid4().hex,kind='qualification'));assert response.status_code==202,response.text
        assert response.json()['reused'] and response.json()['request_id']==attempt['request_id']
        assert len(client.get(prefix).json()['assessments'])==count
        # Meaningfully different business policies retain their own verdicts and
        # reuse the qualified OOS account paths. Neither is eagerly rendered.
        assert client.post(prefix+'/policy',json=dict(minimum_funded_receipts='1')).status_code==200
        first=uuid4().hex
        assert client.post(prefix,json=dict(request_id=first,kind='oos')).status_code==202
        _,one=wait_assessment(client,prefix,first)
        policy=client.get(prefix).json()['assessment_policy']
        response=client.post(prefix+'/policy/revisions',json=dict(minimum_funded_receipts='999999',previous_policy_sha256=policy['policy_sha256'],reason='SYNTHETIC failing limit boundary'))
        assert response.status_code==200,response.text
        second=uuid4().hex
        assert client.post(prefix,json=dict(request_id=second,kind='oos')).status_code==202
        _,two=wait_assessment(client,prefix,second)
        assert one['calculations']['candidates'][0]['economic_assessment']['verdict']=='PASS'
        assert two['calculations']['candidates'][0]['economic_assessment']['verdict']=='FAIL'
        assert one['calculations']['candidates'][0]['paths']==two['calculations']['candidates'][0]['paths']
    loaded=[];page.on('request',lambda r:loaded.append(r.url) if '/validation/funded/' in r.url and '?summary=true' in r.url else None)
    page.reload();panel=page.locator('#prop-sim-funded-validation');current=panel.locator('.prop-sim-current-assessment')
    playwright.expect(current.locator('table')).to_have_count(1,timeout=60000)
    playwright.expect(panel.locator('.prop-sim-history > summary')).to_contain_text('2 previous')
    assert len(loaded)==1 and attempt['request_id'] in loaded[0]
    assert panel.locator('table:visible').count()==1
    panel.screenshot(path=str(tmp_path/'current-result.png'))
    history=panel.locator('.prop-sim-history');history.locator(':scope > summary').click()
    assert len(loaded)==1
    chosen=history.locator('.prop-sim-history-entry').filter(has=page.locator('[data-assessment="'+second+'"]'))
    chosen.locator(':scope > summary').click()
    playwright.expect(chosen.locator('table')).to_have_count(1,timeout=30000)
    assert len(loaded)==2 and second in loaded[-1]
    assert history.locator('.prop-sim-history-entry').filter(has=page.locator('[data-assessment="'+first+'"]')).locator('table').count()==0
    history.screenshot(path=str(tmp_path/'history-on-demand.png'))
    history.locator(':scope > summary').click()
    assert panel.locator('table:visible').count()==1
    with page.expect_download() as download:current.get_by_role('link',name='Assessment evidence ZIP ↓',exact=True).click()
    download.value.save_as(tmp_path/'qualification.zip')
    (tmp_path/'qualification.json').write_bytes(page.request.get(base+prefix+'/'+attempt['request_id']).body())
    (tmp_path/'business-pass.json').write_text(json.dumps(one,indent=2))
    (tmp_path/'business-fail.json').write_text(json.dumps(two,indent=2))
    page.set_viewport_size(dict(width=390,height=844));panel.screenshot(path=str(tmp_path/'mobile.png'))
    assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,simulation=saved['id'],qualification=attempt,
        source=source,assessment_count=3,duplicate_reused=True,current_tables=1,initial_summary_fetches=1,
        history_summary_fetches_after_opening_one=2,business_policy_outcomes=['PASS','FAIL'],
        mean_receipts=one['calculations']['candidates'][0]['metrics']['expected_funded_cash_payouts_within_horizon'],
        no_provider_parity_claim=True,server='Temporary server stopped on fixture teardown.'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_REUSE_EVIDENCE_DIR'):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        for file in tmp_path.iterdir():
            if file.is_file() and file.suffix in ('.json','.png','.zip'):shutil.copyfile(file,target/file.name)

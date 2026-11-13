"""Existing backtest -> Prop Sim -> frozen OOS confidence -> supplied-event monitor."""
import json
import os
from pathlib import Path
import shutil
import socket
from threading import Thread
import time

import httpx
import pytest
import uvicorn
from alphaquest.app import create_app
from test_backtests_browser import browser,page,playwright
from test_prop_oos_qualification import daily_csv
from test_prop_sim import qualified_source


@pytest.fixture
def qualification_portal(tmp_path,monkeypatch):
    root=tmp_path/'library'
    if source:=os.environ.get('ALPHAQUEST_QUALIFICATION_SEED_LIBRARY'):
        shutil.copytree(source,root)
    else:root.mkdir()
    app=create_app(root/'datasets.sqlite3')
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',loop='asyncio'))
    sock=socket.socket();sock.bind(('127.0.0.1',0));url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    thread=Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        deadline=time.monotonic()+10
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline
            time.sleep(.01)
        with httpx.Client(base_url=url,timeout=180) as client:
            items=client.get('/api/prop-sim/candidates').json()['items']
            if not items:
                import test_campaign_broad,test_campaign_narrow,test_campaign_oos
                original=test_campaign_broad.wait_job
                for module in (test_campaign_broad,test_campaign_narrow,test_campaign_oos):
                    monkeypatch.setattr(module,'wait_job',lambda client,id,timeout=600:original(client,id,timeout=600))
                _,source=qualified_source(client,daily_csv())
            else:source=items[0]
        yield dict(url=url,source=source,app=app,root=root)
    finally:
        server.should_exit=True;thread.join(timeout=15);sock.close()
        assert not thread.is_alive(),'Temporary qualification server failed to stop'


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_real_oos_confidence_and_forward_launcher(page,qualification_portal,tmp_path,profile):
    portal=qualification_portal;source=portal['source'];base=portal['url']
    page.goto(base+'/#backtests/report/'+source['source_backtest_id'])
    playwright.expect(page.locator('#report-prop-setup')).to_have_attribute('href','#prop-sim?source='+source['source_backtest_id'],timeout=30000)
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-sim-source')).to_have_value('0',timeout=30000)
    page.locator('#prop-sim-profile').select_option(profile)
    for phase in ('evaluation','funded'):
        for bound in ('minimum','maximum'):page.locator(f'#prop-sim-{phase}_{bound}_micros').fill('10')
    page.locator('#prop-sim-simulations').fill('8')
    page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'configure.png'))
    page.locator('#prop-sim-check').click()
    playwright.expect(page.locator('#prop-sim-status')).to_contain_text('Source compatible',timeout=30000)
    with page.expect_response(lambda r:r.url.endswith('/api/prop-sim') and r.request.method=='POST') as reply:page.locator('#prop-sim-run').click()
    saved=reply.value.json();assert reply.value.status==202
    (tmp_path/'simulation.json').write_text(json.dumps(saved,indent=2))
    observations={}
    for phase in ('evaluation','funded'):
        playwright.expect(page.locator('#prop-sim-'+phase+'-progress')).to_contain_text('COMPLETE',timeout=90000)
        panel=page.locator('#prop-sim-'+phase+'-validation')
        playwright.expect(panel.get_by_text('OOS qualification rules',exact=True)).to_be_visible()
        assert not panel.get_by_role('button',name='Save assessment limits',exact=True).is_visible()
        page.get_by_label(f'Select 10 MNQ for {phase} validation',exact=True).check()
        panel.get_by_label(phase+' freeze rationale',exact=True).fill('SYNTHETIC constant-day oracle; no future profitability claim')
        panel.get_by_role('button',name='Freeze selected sizes',exact=True).click()
        qualify=panel.get_by_role('button',name='Run OOS qualification',exact=True)
        playwright.expect(qualify).to_be_enabled(timeout=30000)
        with page.expect_response(lambda r:r.url.endswith('/validation/'+phase) and r.request.method=='POST') as reply:qualify.click()
        attempt=reply.value.json();assert reply.value.status==202
        resultBox=panel.locator('[data-assessment="'+attempt['request_id']+'"]')
        playwright.expect(resultBox.locator('[role=status]')).to_contain_text('COMPLETE',timeout=180000)
        playwright.expect(resultBox).to_contain_text('historical interval [1.00, 1.00]',timeout=30000)
        playwright.expect(resultBox).to_contain_text('Forward execution · PENDING')
        prefix=f"/api/prop-sim/{saved['id']}/validation/{phase}"
        report=page.request.get(base+prefix+'/'+attempt['request_id']).json()
        row=report['calculations']['candidates'][0]
        assert row['prop_qualification']['status']=='GO'
        assert report['calculations']['qualification_bootstrap'][0]['unique_histories_evaluated']==[1,1]
        assert all(c['lower']==c['upper']==1. for c in row['prop_qualification']['checks'])
        if phase=='evaluation' and profile=='apex-50k-eod':
            assert row['metrics']['cost_per_funded']==49+129
            assert row['metrics']['expected_calendar_days_to_funded']==2
        if phase=='funded':assert row['metrics']['expected_funded_cash_payouts_within_horizon']==sum(p['cash_received'] for p in row['paths'])/8
        assert report['calculations']['winner'] is None
        assert page.request.get(base+prefix).json()['assessment_policy'] is None
        resultBox.screenshot(path=str(tmp_path/(phase+'-qualification.png')))
        with page.expect_download() as download:resultBox.get_by_role('link',name='Assessment evidence ZIP ↓',exact=True).click()
        download.value.save_as(tmp_path/(phase+'-qualification.zip'))
        (tmp_path/(phase+'-qualification.json')).write_text(json.dumps(report,indent=2))
        for kind in ['source_checks.json','qualification_policy.json','oos_qualification.json','historical_bootstrap.json']:
            response=page.request.get(base+f"/api/prop-analyses/{attempt['analysis_id']}/files/"+kind);assert response.status==200
            (tmp_path/(phase+'-'+kind)).write_bytes(response.body())
        observations[phase]=dict(analysis_id=attempt['analysis_id'],request_id=attempt['request_id'],metrics=row['metrics'],review=row['prop_qualification'])
    funded=page.locator('#prop-sim-funded-validation')
    funded.get_by_text('Paper execution and parity review',exact=True).click()
    funded.get_by_role('button',name='Configure paper observation',exact=True).click()
    launcher=page.locator('#forward-launcher');playwright.expect(launcher.locator('#forward-policy option')).to_have_count(2)
    choice=launcher.locator('#forward-policy option').last.get_attribute('value');launcher.locator('#forward-policy').select_option(choice)
    launcher.locator('#forward-kind').select_option('paper')
    launcher.locator('#forward-name').fill('SYNTHETIC demo declaration; awaiting real paper events')
    launcher.locator('#forward-source-id').fill('paper-source-awaiting-evidence')
    launcher.locator('#forward-source-label').fill('No supplied paper execution yet')
    launcher.locator('#forward-cost-basis').select_option('fifo')
    launcher.locator('#forward-check').click()
    playwright.expect(launcher.locator('#forward-source-check')).to_contain_text('authoritative_prop_sim_policy',timeout=30000)
    launcher.screenshot(path=str(tmp_path/'forward-declaration.png'))
    # Declaration is checked only; no future or pretend paper observations are generated.
    page.reload();panel=page.locator('#prop-sim-funded-validation')
    playwright.expect(panel).to_contain_text('historical interval [1.00, 1.00]',timeout=60000)
    page.set_viewport_size(dict(width=390,height=844))
    panel.screenshot(path=str(tmp_path/'mobile-results.png'))
    assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,profile=profile,simulation_id=saved['id'],
        source=source,results=observations,expected='Identical constant IS/OOS daybooks imply every history ratio and bound = 1; forward remains pending.',
        server='Temporary server stopped by fixture teardown; no user server changed.'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_QUALIFICATION_EVIDENCE_DIR'):
        target=Path(destination)/profile;target.mkdir(parents=True,exist_ok=True)
        for file in tmp_path.iterdir():
            if file.is_file() and file.suffix in ('.json','.png','.zip','.csv'):shutil.copyfile(file,target/file.name)
        (target/'SYNTHETIC-source.csv').write_bytes(page.request.get(base+'/api/datasets/'+source['dataset']['id']+'/csv').body())

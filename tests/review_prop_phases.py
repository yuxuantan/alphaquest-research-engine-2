"""Reopen milestone-1 saved product evidence and qualify Lucid via real UI.

Uses the normal fixture library, existing API and report store. Owns/stops its
server/browser; never touches the user's normal data or another process.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import socket
from threading import Thread
import time

import uvicorn
from playwright.sync_api import sync_playwright, expect
from alphaquest.app import create_app


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();library=args.library.resolve();output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    verification=json.loads((library/'verification.json').read_text())
    before={str(p.relative_to(library)):sha256(p.read_bytes()).hexdigest() for p in library.rglob('*') if p.is_file() and p.suffix in ('.csv','.json','.zip','.gz')}
    sock=socket.socket();sock.bind(('127.0.0.1',0));url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(create_app(library/'datasets.sqlite3'),log_level='error',loop='asyncio'))
    thread=Thread(target=server.run,kwargs=dict(sockets=[sock]),daemon=True);thread.start()
    result=dict(original_outcomes=verification['outcomes'])
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline
            time.sleep(.02)
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport=dict(width=1440,height=1100));posts=[];errors=[]
                page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
                page.on('pageerror',lambda e:errors.append(str(e)))
                for label,case in verification['outcomes'].items():
                    page.goto(url+case['url']);expect(page.locator('#prop-report')).to_be_visible()
                    expect(page.locator('#prop-heading-title')).to_have_text('Dated phase lifecycle')
                    report=page.request.get(url+f"/api/prop-analyses/{case['analysis_id']}/downloads/report.json").json()
                    if label!='recovering':assert report['calculations']['phase_metrics']['funded']['trader_payouts']==case['payouts']
                    page.screenshot(path=str(output/(label+'-report.png')),full_page=True)
                    page.reload();expect(page.locator('#prop-report')).to_be_visible()
                assert not posts
                # Final-code configure/check/run for each saved source choice.
                # Existing backtests are reused; every report is published by
                # the real worker into this same ordinary AnalysisStore.
                current={}
                for label,case in verification['outcomes'].items():
                    evaluation=case['source_id'] if label=='recovering' else verification['evaluation_source']
                    page.goto(url+'/#backtests/prop/new/'+evaluation)
                    expect(page.locator('#prop-config')).to_be_visible()
                    page.locator('#prop-method').select_option('dated_lifecycle')
                    page.locator('#prop-commission-mode').select_option('source')
                    page.locator('#prop-funded-source').select_option('' if case['source_id']==evaluation else case['source_id'])
                    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:page.locator('#prop-check').click()
                    assert checked.value.status==200,checked.value.text()
                    (output/(label+'-check.json')).write_text(json.dumps(checked.value.json(),indent=2))
                    page.locator('#prop-run').click();expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
                    id=page.url.rsplit('/',1)[-1]
                    report=page.request.get(url+f'/api/prop-analyses/{id}/downloads/report.json').json();c=report['calculations']
                    if label=='recovering':assert c['outcome']=='account_breach' and c['trace'][0]['equity']==-3000
                    else:
                        assert c['phase_metrics']['funded']['trader_payouts']==case['payouts']
                        assert c['activation']['funded_start_session']=='2026-01-07'
                        assert c['trace'][2]['source_trade_ids']==[3]
                    (output/(label+'-report.json')).write_text(json.dumps(report,indent=2))
                    for name,kind in [('analysis.zip','downloads'),('transition_trace.csv','files'),('transition_trace.json','files')]:
                        response=page.request.get(url+f'/api/prop-analyses/{id}/{kind}/{name}');assert response.status==200
                        (output/(label+'-'+name)).write_bytes(response.body())
                    page.screenshot(path=str(output/(label+'-report.png')),full_page=True)
                    before_reload=len(posts);page.reload();expect(page.locator('#prop-report')).to_be_visible();assert len(posts)==before_reload
                    current[label]={**case,'analysis_id':id,'url':f'/#backtests/prop/job/{id}'}
                result['current_outcomes']=current
                # A new Lucid dated report on an existing saved backtest. No
                # dataset upload, backtest, reduced counts or external calculator.
                page.goto(url+'/#backtests/prop/new/'+verification['evaluation_source'])
                expect(page.locator('#prop-config')).to_be_visible()
                page.locator('#prop-model').select_option('1')
                page.locator('#prop-method').select_option('dated_lifecycle')
                page.locator('#prop-commission-mode').select_option('source')
                page.locator('#prop-evaluation-micros').fill('10');page.locator('#prop-funded-micros').fill('3')
                with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:page.locator('#prop-check').click()
                assert checked.value.status==200,checked.value.text()
                (output/'lucid-check.json').write_text(json.dumps(checked.value.json(),indent=2))
                page.locator('#prop-run').click();expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
                id=page.url.rsplit('/',1)[-1]
                report=page.request.get(url+f'/api/prop-analyses/{id}/downloads/report.json').json();c=report['calculations']
                assert c['phase_metrics']['evaluation']['pass_date']=='2026-01-07'
                assert c['activation']['eligible_session']=='2026-01-07'
                assert c['activation']['funded_start_session']=='2026-01-08'
                assert c['phase_metrics']['funded']['trader_payouts']==9000
                assert c['phase_metrics']['funded']['gross_withdrawals']==10000
                assert c['phase_metrics']['funded']['sessions']==25
                (output/'lucid-report.json').write_text(json.dumps(report,indent=2))
                for name,kind in [('analysis.zip','downloads'),('transition_trace.csv','files'),('transition_trace.json','files')]:
                    response=page.request.get(url+f'/api/prop-analyses/{id}/{kind}/{name}');assert response.status==200
                    (output/('lucid-'+name)).write_bytes(response.body())
                page.screenshot(path=str(output/'lucid-report.png'),full_page=True)
                before_reload=len(posts);page.reload();expect(page.locator('#prop-report')).to_be_visible();assert len(posts)==before_reload
                page.set_viewport_size(dict(width=390,height=900));page.screenshot(path=str(output/'mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert not errors,errors
                assert all('/api/prop-analyses' in p for p in posts)
                result['lucid']=dict(id=id,url=f'/#backtests/prop/job/{id}',evaluation_pass='2026-01-07',funded_start='2026-01-08',gross_withdrawals=10000,trader_payouts=9000)
            finally:browser.close()
    finally:
        server.should_exit=True;thread.join(15);sock.close()
        assert not thread.is_alive(),'Temporary server did not stop.'
        result['server_stopped']=True
        changed=[name for name,expected in before.items() if sha256((library/name).read_bytes()).hexdigest()!=expected]
        assert not changed,changed
        result['prior_library_files_unchanged']=len(before)
        (output/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

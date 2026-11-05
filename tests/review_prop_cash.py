"""Reopen the saved synthetic library and repeat its real configure/check/run flow.

Preserves existing inputs/reports, uses the normal AnalysisStore, owns/stops its
server and browser. Does not run strategy bars or use external calculators.
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
    before={str(p.relative_to(library)):sha256(p.read_bytes()).hexdigest() for p in library.rglob('*')
        if p.is_file() and p.suffix in ('.json','.csv','.zip','.gz')}
    sock=socket.socket();sock.bind(('127.0.0.1',0));url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(create_app(library/'datasets.sqlite3'),log_level='error',loop='asyncio'))
    thread=Thread(target=server.run,kwargs=dict(sockets=[sock]),daemon=True);thread.start()
    result={**verification,'outcomes':{}};posts=[];errors=[]
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline
            time.sleep(.02)
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport=dict(width=1440,height=1100))
                page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url+'/#backtests/report/'+verification['evaluation_source'])
                page.locator('#report-prop-setup').click();expect(page.locator('#prop-config')).to_be_visible()
                for label,case in verification['outcomes'].items():
                    page.goto(url+case['url']);expect(page.locator('#prop-report')).to_be_visible()
                    page.get_by_role('link',name='Configure new analysis',exact=True).click()
                    expect(page.locator('#prop-config')).to_be_visible()
                    expect(page.locator('#prop-method')).to_have_value('budgeted_lifecycle')
                    expect(page.locator('#prop-monthly-cap')).to_have_value('100.00')
                    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:page.locator('#prop-check').click()
                    assert checked.value.status==200,checked.value.text()
                    (output/(label+'-check.json')).write_text(json.dumps(checked.value.json(),indent=2))
                    with page.expect_request(lambda r:r.url.endswith('/api/prop-analyses') and r.method=='POST') as submission:page.locator('#prop-run').click()
                    request=submission.value.post_data_json
                    (output/(label+'-request.json')).write_text(json.dumps(request,indent=2))
                    expect(page.locator('#prop-heading-title')).to_have_text('Budgeted cash ledger',timeout=30000)
                    expect(page.locator('#prop-report')).to_be_visible()
                    id=page.url.rsplit('/',1)[-1]
                    report=page.request.get(url+f'/api/prop-analyses/{id}/downloads/report.json').json()
                    totals=report['calculations']['cash_totals']
                    assert totals['total_paid_fees']==case['paid_fees'] and totals['net_cash_within_horizon']==case['net_cash']
                    (output/(label+'-report.json')).write_text(json.dumps(report,indent=2))
                    for name,kind in [('cash_ledger.csv','files'),('cash_ledger.json','files'),('monthly_ledger.csv','files'),('monthly_ledger.json','files'),
                        ('pending_receipts.json','files'),('transition_trace.csv','files'),('analysis.zip','downloads')]:
                        response=page.request.get(url+f'/api/prop-analyses/{id}/{kind}/{name}');assert response.status==200
                        (output/(label+'-'+name)).write_bytes(response.body())
                    page.screenshot(path=str(output/(label+'-report.png')),full_page=True)
                    before_reload=len(posts);page.reload();expect(page.locator('#prop-report')).to_be_visible();assert len(posts)==before_reload
                    assert page.request.get(url+f'/api/prop-analyses/{id}/downloads/report.json').json()==report
                    result['outcomes'][label]={**case,'analysis_id':id,'url':f'/#backtests/prop/job/{id}'}
                page.set_viewport_size(dict(width=390,height=900));page.screenshot(path=str(output/'mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert not errors,errors
                assert all('/api/prop-analyses' in p for p in posts)
            finally:browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=15);sock.close()
        assert not thread.is_alive(),'Owned temporary server did not stop'
    changed=[name for name,digest in before.items() if not (library/name).is_file() or sha256((library/name).read_bytes()).hexdigest()!=digest]
    assert not changed,changed
    result.update(original_files_verified=len(before),original_files_changed=changed,javascript_errors=errors,
        temporary_server='Stopped after observed completion; no persistent server.',analysis_posts=len(posts))
    (output/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

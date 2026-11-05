"""Reopen saved lifecycle evidence and check its budgeted configuration successor.

Read-only against the normal fixture library; no backtests or analyses are
submitted. Owns/stops its server/browser without touching another process.
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
    result=dict(original_outcomes=verification['outcomes'],configurations={})
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
                    if 'payouts' in case:
                        assert report['calculations']['phase_metrics']['funded']['trader_payouts']==case['payouts']
                    page.screenshot(path=str(output/(label+'-report.png')),full_page=True)
                    page.reload();expect(page.locator('#prop-report')).to_be_visible()
                    page.get_by_role('link',name='Configure budgeted analysis',exact=True).click()
                    expect(page.locator('#prop-config')).to_be_visible()
                    expect(page.locator('#prop-method')).to_have_value('budgeted_lifecycle')
                    methods=page.locator('#prop-method option').evaluate_all('(nodes)=>nodes.map(n=>n.value)')
                    assert methods==['annualized','budgeted_lifecycle']
                    expect(page.locator('#prop-evaluation-micros')).to_have_value(report['settings']['EVALUATION_MICROS'])
                    expect(page.locator('#prop-funded-micros')).to_have_value(report['settings']['FUNDED_MICROS'])
                    for field in ['prop-monthly-cap','prop-start-date','prop-horizon-end','prop-payout-preset','prop-activation-preset']:
                        expect(page.locator('#'+field)).to_have_value('')
                    result['configurations'][label]=dict(methods=methods,selected='budgeted_lifecycle',
                        evaluation_size=page.locator('#prop-evaluation-micros').input_value(),
                        funded_size=page.locator('#prop-funded-micros').input_value(),
                        funded_source=page.locator('#prop-funded-source').input_value())
                    page.screenshot(path=str(output/(label+'-budgeted-config.png')),full_page=True)
                page.set_viewport_size(dict(width=390,height=900))
                page.screenshot(path=str(output/'mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert not errors,errors
                assert not posts,posts
                result['submitted_posts']=len(posts)
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

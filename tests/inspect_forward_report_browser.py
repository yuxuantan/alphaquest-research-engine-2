"""Read-only browser verification of already-published normal forward reports.

The expectation JSON is an independent fixture oracle supplied by the publisher;
this script never creates monitors, events, calculations, policies or a new API.
Run explicitly; ordinary pytest discovery does not collect this utility.
"""
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import socket
from threading import Thread
import time
import zipfile

import uvicorn
from playwright.sync_api import sync_playwright,expect
from alphaquest.app import create_app


def inspect(library,expectations,output):
    assert (library/'datasets.sqlite3').is_file(),'Use an existing published normal-product library.'
    output.mkdir(parents=True,exist_ok=False)
    server=uvicorn.Server(uvicorn.Config(create_app(library/'datasets.sqlite3'),log_level='error'))
    sock=socket.socket();sock.bind(('127.0.0.1',0));url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    thread=Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    result=dict(library=str(library),cases=[],post_requests=[],server_stopped=False)
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline
            time.sleep(.01)
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1280,'height':900})
            page.on('request',lambda request:result['post_requests'].append(request.url) if request.method=='POST' else None)
            for case in expectations['cases']:
                id=case['analysis_id'];page.goto(url+'/#backtests/prop/job/'+id)
                expect(page.locator('#forward-assessment-result')).to_be_visible(timeout=30000)
                response=page.request.get(url+f'/api/prop-analyses/{id}/downloads/report.json');assert response.ok,response.text()
                raw=response.body();report=response.json();assert report['model_version']=='forward-monitor-v1'
                conformance=report['calculations']['policy_conformance'];assert conformance['status']==case['status']
                rows=conformance['decisions'];assert [row['recalculated']['quantity'] for row in rows]==case['expected_quantities']
                if 'expected_supplied' in case:assert [row['supplied'].get('submitted_quantity',row['supplied'].get('quantity')) for row in rows]==case['expected_supplied']
                if 'denominator_values' in case:assert [row['recalculated'].get('denominator_value') for row in rows]==case['denominator_values']
                panel=page.locator('#forward-policy-conformance')
                if panel.get_attribute('open') is None:panel.locator(':scope > summary').click()
                expect(page.locator('#forward-sizing-decisions tbody tr')).to_have_count(len(rows))
                for index,row in enumerate(rows):
                    expect(page.locator('#forward-sizing-decisions tbody tr').nth(index)).to_contain_text(str(row['recalculated']['quantity'])+' / '+row['recalculated']['action'])
                panel.screenshot(path=str(output/(case['label']+'-decisions.png')))
                clocks=panel.get_by_text('Supplied causal sizing clocks and planned risk',exact=True)
                if clocks.count():clocks.click();panel.screenshot(path=str(output/(case['label']+'-causal-context.png')))
                page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.locator('#forward-sizing-decisions').screenshot(path=str(output/(case['label']+'-narrow.png')))
                page.set_viewport_size({'width':1280,'height':900})
                files={case['label']+'-report.json':raw};archive=page.request.get(url+f'/api/prop-analyses/{id}/downloads/analysis.zip');assert archive.ok,archive.text()
                files[case['label']+'-analysis.zip']=archive.body();members=0
                with zipfile.ZipFile(io.BytesIO(archive.body())) as z:
                    for name,entry in report['files'].items():assert sha256(z.read(name)).hexdigest()==entry['sha256'];members+=1
                hashes={}
                for name,data in files.items():(output/name).write_bytes(data);hashes[name]=sha256(data).hexdigest()
                page.reload();expect(page.locator('#forward-assessment-result')).to_be_visible();assert page.request.get(url+f'/api/prop-analyses/{id}/downloads/report.json').body()==raw
                result['cases'].append(dict(**case,downloads=hashes,verified_zip_members=members))
            current=expectations.get('current_analysis_id')
            if current:
                page.goto(url+'/#backtests/prop/job/'+current);page.locator('#forward-launcher > summary').click()
                page.locator('#forward-policy').select_option(expectations['package_sha256'])
                page.locator('#forward-observation-scope > summary').click();page.locator('#forward-scope-enabled').check()
                expect(page.locator('#forward-scope-fields')).to_contain_text('Supplied unchanged frozen trading/sizing policy')
                page.locator('#forward-observation-scope').screenshot(path=str(output/'final-scope-copy.png'))
                result['final_scope_copy_verified']=True
            assert not result['post_requests'];browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close();assert not thread.is_alive()
        result['server_stopped']=True
    (output/'verification.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--library',type=Path,required=True);parser.add_argument('--expectations',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(inspect(args.library,json.loads(args.expectations.read_text()),args.output),indent=2))

"""Create one new real IS report and inspect the normal prop product journey.

Run from the repository root; owns a temporary server/private browser only.
Does not run OOS or alter existing datasets, reports or the user's server.
"""
import argparse
import csv
from decimal import Decimal as D
import hashlib
import io
import json
from pathlib import Path
import socket
from threading import Thread
import time

import httpx
from playwright.sync_api import sync_playwright, expect
import uvicorn
from alphaquest.app import create_app


def review(output, database, request_file):
    output.mkdir(parents=True, exist_ok=False)
    original = Path('artifacts/eod-next-open-20261102')
    request = json.loads(request_file.read_text())
    request['reuse_results'] = False
    # Expected values are fixed before the new execution. The earlier qualified
    # raw next-Open repricing is retained; no new strategy function generates it.
    expected = dict(trades=486, gross='28155.00', commissions='1934.28', net='26220.72',
                    rationale='Same scheduled cutoffs/prices on this complete 2021-2024 source; independently qualified raw next-Open repricing retained in eod-next-open-20261102/independent-expected.json.')
    (output/'independent-expected.json').write_text(json.dumps(expected,indent=2))
    (output/'request.json').write_text(json.dumps(request,indent=2))
    old_trades = (original/'new-trades.csv').read_bytes()
    old_report = json.loads((original/'new-report.json').read_text())
    old_dir = database.parent/'backtest_runs'/old_report['id']
    preserved = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in old_dir.rglob('*') if p.is_file()}
    assert preserved, old_dir
    (output/'preserved-report-hashes.json').write_text(json.dumps(preserved,indent=2))
    app=create_app(database)
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',loop='asyncio'))
    sock=socket.socket();sock.bind(('127.0.0.1',0))
    url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    (output/'temporary-url.txt').write_text(url)
    worker=Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);worker.start()
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert worker.is_alive() and time.monotonic()<deadline
            time.sleep(.01)
        with httpx.Client(base_url=url,timeout=900) as client:
            print('Creating real IS report through POST /api/backtests at',url,flush=True)
            response=client.post('/api/backtests',json=request)
            (output/'backtest-response.txt').write_text(response.text)
            response.raise_for_status();record=response.json();run_id=record['id']
            (output/'new-report.json').write_text(json.dumps(record,indent=2))
            print('Saved real report',run_id,record['summary'],flush=True)
            for kind in ('trades','equity','intratrade_risk','report'):
                download=client.get(f'/api/backtests/{run_id}/exports/{kind}');download.raise_for_status()
                (output/(kind+('.json' if kind=='report' else '.csv'))).write_bytes(download.content)
            trades=list(csv.DictReader(io.StringIO((output/'trades.csv').read_text())))
            assert len(trades)==expected['trades']
            assert sum(D(t['gross_pnl']) for t in trades)==D(expected['gross'])
            assert sum(D(t['total_commissions']) for t in trades)==D(expected['commissions'])
            assert sum(D(t['net_pnl']) for t in trades)==D(expected['net'])
            assert (output/'trades.csv').read_bytes()==old_trades
            flatten=record['run_metadata']['strategy']['session_flattening']
            assert flatten['mode']=='csv_session_calendar_v1' and flatten['lookahead'] is False
            assert flatten['calendar']['sha256']==hashlib.sha256(Path('calendars/cme_nq_closures.csv').read_bytes()).hexdigest()
            automatic=record['run_metadata']['automatic_prop_analysis']
            errors=[]
            with sync_playwright() as runtime:
                browser=runtime.chromium.launch()
                try:
                    page=browser.new_page(viewport={'width':1440,'height':1100});page.set_default_timeout(45000)
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(url+'/#backtests/report/'+run_id)
                    label=page.locator("#backtest-completion-content [data-setting='session_flattening']")
                    expect(label).to_contain_text('Calendar-based session exits')
                    expect(label).to_contain_text('15:45 CT')
                    label.evaluate("el=>{const d=el.closest('details');if(d)d.open=true;}")
                    page.screenshot(path=str(output/'calendar-real-report.png'),full_page=True)
                    with page.expect_download() as download:page.locator('#report-trades-download').click()
                    download.value.save_as(output/'ui-trades.csv')
                    assert (output/'ui-trades.csv').read_bytes()==old_trades
                    page.reload();expect(label).to_contain_text('Calendar-based session exits')
                    page.set_viewport_size({'width':390,'height':844})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(output/'calendar-real-mobile.png'),full_page=True)
                    page.set_viewport_size({'width':1440,'height':1100})
                    page.locator('#report-prop-setup').click()
                    expect(page.locator('#prop-config')).to_be_visible()
                    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:
                        page.locator('#prop-check').click()
                    assert checked.value.ok,checked.value.text()
                    (output/'apex-source-check.json').write_text(json.dumps(checked.value.json(),indent=2))
                    expect(page.locator('#prop-check-output')).to_contain_text('Source check passed')
                    page.screenshot(path=str(output/'calendar-prop-source-check.png'),full_page=True)
                    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses') and r.request.method=='POST') as submitted:
                        page.locator('#prop-run').click()
                    job=submitted.value.json()
                    assert job['id']==automatic['id']
                    expect(page.locator('#prop-report')).to_be_visible()
                    page.reload();expect(page.locator('#prop-report')).to_be_visible()
                    page.screenshot(path=str(output/'calendar-durable-prop-report.png'),full_page=True)
                    report=client.get(f"/api/prop-analyses/{job['id']}/downloads/report.json");report.raise_for_status()
                    (output/'apex-report.json').write_bytes(report.content)
                    # Earlier report remains explicitly identified as historical lookahead.
                    page.goto(url+'/#backtests/report/'+old_report['id'])
                    expect(label).to_contain_text('Backtest lookahead')
                    page.screenshot(path=str(output/'preserved-earlier-model.png'),full_page=True)
                    assert not errors,errors
                finally:browser.close()
            for name,digest in preserved.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
            result=dict(run_id=run_id,prop_analysis_id=job['id'],expected=expected,
                        trades_byte_identical_to_qualified_reference=True,calendar=flatten['calendar'],
                        bar_lookahead=False,source_check_passed=True,run_action_reused_completed_analysis=True,
                        saved_report_reopened=True,older_report_preserved=True,browser_errors=errors,
                        temporary_server_stopped=True)
            (output/'verification.json').write_text(json.dumps(result,indent=2))
            print(json.dumps(result,indent=2),flush=True)
    finally:
        server.should_exit=True;worker.join(timeout=20);sock.close()
        assert not worker.is_alive(),'Owned temporary server did not stop'
        print('Owned temporary server stopped.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--database',type=Path,default=Path('data/datasets.sqlite3'))
    parser.add_argument('--request',type=Path,default=Path('artifacts/eod-next-open-20261102/request.json'))
    args=parser.parse_args();review(args.output.resolve(),args.database.resolve(),args.request.resolve())

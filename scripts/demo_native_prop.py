"""Demonstrate independent local calculations through the actual portal.

Reference outputs are read by the comparison harness only, after calculation.
The calculation worker is guarded against external executables and result files.
"""
import argparse,csv,io,json,shutil,socket,sqlite3,subprocess,sys,time,zipfile
from datetime import datetime,timezone
from pathlib import Path
from threading import Thread
import httpx
import uvicorn
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alphaquest.app import create_app
from alphaquest.prop.adapter import digest

SOURCE='d63265dc923444c799c2dfc59e090e76'
REFERENCE=Path('/Users/yx/Downloads/20261026_171955')


from verify_native_prop import compare


def backup_sqlite(source,destination):
    with sqlite3.connect(source) as a,sqlite3.connect(destination) as b:a.backup(b)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish-url');parser.add_argument('--reference',type=Path,default=REFERENCE);args=parser.parse_args()
    out=Path('artifacts')/('native-prop-parity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
    data=out/'server-data';data.mkdir();(data/'backtest_runs').mkdir()
    backup_sqlite('data/datasets.sqlite3',data/'datasets.sqlite3');backup_sqlite('data/backtests.sqlite3',data/'backtests.sqlite3')
    # APFS copy-on-write snapshot: source files remain immutable and independent.
    subprocess.run(['cp','-c','-R','data/backtest_runs/'+SOURCE,str(data/'backtest_runs')],check=True)
    old='863ef30f413b4b32a38cb1a59a543fa3';(data/'prop_analyses').mkdir()
    backup_sqlite('data/prop_analyses/catalog.sqlite3',data/'prop_analyses/catalog.sqlite3')
    subprocess.run(['cp','-c','-R','data/prop_analyses/'+old,str(data/'prop_analyses')],check=True)
    # No subprocess other than read-only Git provenance, and no foreign result
    # or executable reads, are allowed on the production calculation thread.
    import threading
    io_events=[]
    def audit(event,values):
        if not threading.current_thread().name.startswith('prop-analysis'):
            return
        if event=='open' and isinstance(values[0],(str,bytes)):
            path=str(values[0]);io_events.append(dict(event=event,path=path,mode=values[1]))
            if Path(path).suffix.lower() in ('.exe','.dll') or Path(path).name in ('results.json','report.html'):
                raise AssertionError('Local worker accessed external engine/result: '+path)
        if event=='subprocess.Popen':
            io_events.append(dict(event=event,command=values[1]))
            if Path(values[0]).name!='git':raise AssertionError('Local worker invoked a calculation subprocess')
    sys.addaudithook(audit)
    app=create_app(data/'datasets.sqlite3');sock=socket.socket();sock.bind(('127.0.0.1',0));url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',loop='asyncio'));thread=Thread(target=server.run,kwargs=dict(sockets=[sock]),daemon=True);thread.start()
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline;time.sleep(.02)
        with sync_playwright() as w:
            browser=w.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url+f'/#backtests/prop/job/{old}');expect(page.get_by_role('heading',name='Historical notebook report')).to_be_visible(timeout=20000)
            page.goto(url+f'/#backtests/report/{SOURCE}');page.locator('#report-prop-setup').click();expect(page.locator('#prop-config')).to_be_visible()
            expect(page.locator('#prop-trade-file')).not_to_have_value('');page.locator('#prop-check').click();expect(page.locator('#prop-run')).to_be_enabled(timeout=20000)
            page.screenshot(path=str(out/'source-check.png'),full_page=True)
            page.locator('#prop-run').click()
            deadline=time.monotonic()+600
            while not page.locator('#prop-report').is_visible():
                status=page.locator('#prop-status').inner_text()
                assert not any(s in status for s in ('Error:','failed','Cannot inspect','Lost contact')),status
                assert time.monotonic()<deadline,status
                page.wait_for_timeout(700)
            page.screenshot(path=str(out/'report.png'),full_page=True)
            expect(page.locator('#prop-report-content')).to_contain_text('34.1%');expect(page.locator('#prop-report-content')).to_contain_text('$2,005.43');expect(page.locator('#prop-report-content')).to_contain_text('83.7%')
            with page.expect_download() as d:page.get_by_role('link',name='Report data (JSON)',exact=True).click()
            d.value.save_as(out/'report.json');report=json.loads((out/'report.json').read_text())
            with page.expect_download() as d:page.get_by_role('link',name='Download all results (ZIP)',exact=True).click()
            d.value.save_as(out/'analysis.zip')
            posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
            page.reload();expect(page.locator('#prop-report')).to_be_visible(timeout=20000)
            page.locator('#prop-back').click();page.locator('#report-prop-setup').click();page.locator(f'#prop-saved a[href$="{report["id"]}"]').click();expect(page.locator('#prop-report')).to_be_visible(timeout=20000)
            assert not posts and not errors
            browser.close()
        checks=compare(report['calculations'],args.reference);assert checks['all_pass'],[c for c in checks['checks'] if not c['pass_']]
        with zipfile.ZipFile(out/'analysis.zip') as z:assert json.loads(z.read('calculations.json'))==report['calculations']
        evidence=dict(temporary_report_id=report['id'],exact_checks=checks,all_pass=True,browser_errors=errors,reload_reopen_without_post=True,model=report['model_version'],source=report['source']['excursion_input'],production_io=io_events)
        if args.publish_url:
            with httpx.Client(base_url=args.publish_url,timeout=60) as client:
                request=dict(source_backtest_id=SOURCE,trade_file=report['source']['excursion_input']['path'],settings=report['settings'])
                check=client.post('/api/prop-analyses/check',json=request);assert check.status_code==200,check.text
                response=client.post('/api/prop-analyses',json=request);assert response.status_code==202,response.text
                job=response.json();deadline=time.monotonic()+600
                while True:
                    current=client.get('/api/prop-analyses/'+job['id']).json()
                    if current['status'] in ('complete','error'):break
                    assert time.monotonic()<deadline;time.sleep(1)
                assert current['status']=='complete',current
                raw=client.get('/api/prop-analyses/'+job['id']+'/downloads/report.json');raw.raise_for_status();actual=raw.json()
                assert actual['calculations']==report['calculations']
                evidence['published_report_id']=job['id'];(out/'published-report.json').write_bytes(raw.content)
                evidence['published_exact_checks']=compare(actual['calculations'],args.reference);assert evidence['published_exact_checks']['all_pass']
        (out/'production-io.json').write_text(json.dumps(io_events,indent=2))
        (out/'validation.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(dict(evidence=str(out),temporary_report_id=report['id'],published_report_id=evidence.get('published_report_id'),comparison_count=checks['comparison_count'],all_pass=checks['all_pass'],browser_errors=errors,local_worker_processes=[e for e in io_events if e['event']=='subprocess.Popen']),indent=2))
    finally:
        server.should_exit=True;thread.join(30);sock.close();assert not thread.is_alive(),'Temporary server did not stop'

if __name__=='__main__':main()

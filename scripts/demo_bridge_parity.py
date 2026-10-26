"""Demonstrate the actual portal workflow on an isolated server, then optionally
publish a real new analysis through the user's already-running portal API.

The Bridge remains a black box. Compare its new actual results, all table rows,
CSV tables and chart bytes with the supplied reference; no fixture values enter
production execution. Preserve all original files and existing jobs.
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


def compare(directory,reference=REFERENCE):
    result=json.loads((directory/'results.json').read_text());expected=json.loads((reference/'results.json').read_text())
    checks={k:result[k]==expected[k] for k in ('account','settings_form','settings','files','dates','part1','part2','warnings','session_note')}
    checks['displayed_sections']=[s for s in result['sections'] if s['title']!='Saved files']==[s for s in expected['sections'] if s['title']!='Saved files']
    checks['chart_data']=result['charts']==expected['charts']
    checks['chart_metadata']=result['chart_files']==expected['chart_files']
    for prefix in ('files','evaluation','each_strategy_alone','export_checks','export_warnings','slot_accounts','slots_year_by_year','sizes_tried_in_sample'):
        a=list(csv.reader(next(reference.glob(prefix+'_*.csv')).open()));b=list(csv.reader(next(directory.glob(prefix+'_*.csv')).open()))
        checks['csv_'+prefix]=a==b
    for name in ('evaluation','outcomes','slots'):
        checks['chart_'+name]=digest(reference/'charts'/f'{name}.png')==digest(directory/'charts'/f'{name}.png')
    assert all(checks.values()),checks
    return checks


def backup_sqlite(source,destination):
    with sqlite3.connect(source) as a,sqlite3.connect(destination) as b:a.backup(b)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish-url');args=parser.parse_args()
    out=Path('artifacts')/('bridge-portal-parity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
    data=out/'server-data';data.mkdir();(data/'backtest_runs').mkdir()
    backup_sqlite('data/datasets.sqlite3',data/'datasets.sqlite3');backup_sqlite('data/backtests.sqlite3',data/'backtests.sqlite3')
    # APFS copy-on-write snapshot: source files remain immutable and independent.
    subprocess.run(['cp','-c','-R','data/backtest_runs/'+SOURCE,str(data/'backtest_runs')],check=True)
    old='863ef30f413b4b32a38cb1a59a543fa3';(data/'prop_analyses').mkdir()
    backup_sqlite('data/prop_analyses/catalog.sqlite3',data/'prop_analyses/catalog.sqlite3')
    subprocess.run(['cp','-c','-R','data/prop_analyses/'+old,str(data/'prop_analyses')],check=True)
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
            expect(page.locator('#prop-report-content')).to_contain_text('34.1%');expect(page.locator('#prop-report-content')).to_contain_text('$2,005');expect(page.locator('#prop-report-content')).to_contain_text('83.7%')
            with page.expect_download() as d:page.get_by_role('link',name='report.json ↓',exact=True).click()
            d.value.save_as(out/'report.json');report=json.loads((out/'report.json').read_text())
            with page.expect_download() as d:page.get_by_role('link',name='analysis.zip ↓',exact=True).click()
            d.value.save_as(out/'analysis.zip')
            posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
            page.reload();expect(page.locator('#prop-report')).to_be_visible(timeout=20000)
            page.locator('#prop-back').click();page.locator('#report-prop-setup').click();page.locator(f'#prop-saved a[href$="{report["id"]}"]').click();expect(page.locator('#prop-report')).to_be_visible(timeout=20000)
            assert not posts and not errors
            browser.close()
        checks=compare(app.state.prop_analyses.root/report['id']/'bridge')
        with zipfile.ZipFile(out/'analysis.zip') as z:assert json.loads(z.read('bridge/results.json'))==report['bridge_results']
        evidence=dict(temporary_report_id=report['id'],exact_checks=checks,all_pass=True,browser_errors=errors,reload_reopen_without_post=True,engine=report['engine'],source=report['source']['bridge_input'])
        if args.publish_url:
            with httpx.Client(base_url=args.publish_url,timeout=60) as client:
                request=dict(source_backtest_id=SOURCE,trade_file=report['source']['bridge_input']['path'],settings=report['settings'])
                check=client.post('/api/prop-analyses/check',json=request);assert check.status_code==200,check.text
                response=client.post('/api/prop-analyses',json=request);assert response.status_code==202,response.text
                job=response.json();deadline=time.monotonic()+600
                while True:
                    current=client.get('/api/prop-analyses/'+job['id']).json()
                    if current['status'] in ('complete','error'):break
                    assert time.monotonic()<deadline;time.sleep(1)
                assert current['status']=='complete',current
                raw=client.get('/api/prop-analyses/'+job['id']+'/downloads/report.json');raw.raise_for_status();actual=raw.json()
                for key in ('account','settings_form','settings','files','dates','part1','part2','warnings','session_note'):assert actual['bridge_results'][key]==report['bridge_results'][key]
                evidence['published_report_id']=job['id'];(out/'published-report.json').write_bytes(raw.content)
                evidence['published_exact_checks']=compare(Path('data/prop_analyses')/job['id']/'bridge')
        (out/'validation.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(dict(evidence=str(out),**evidence),indent=2))
    finally:
        server.should_exit=True;thread.join(30);sock.close();assert not thread.is_alive(),'Temporary server did not stop'

if __name__=='__main__':main()

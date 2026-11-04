"""Read-only review of the existing saved batch; no backtests or simulations."""
import argparse
import csv
import io
import json
from pathlib import Path
import socket
import sqlite3
import sys
from threading import Thread
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from alphaquest.app import create_app

BATCH='d69045ab437942618ec2afb54728c33c'


def review(output):
    output.mkdir(parents=True,exist_ok=False)
    with sqlite3.connect('data/prop_analyses/catalog.sqlite3') as db:
        assert not db.execute("SELECT 1 FROM analyses WHERE status IN ('running','queued')").fetchone(),'Wait for analysis jobs to finish.'
    app=create_app(Path('data/datasets.sqlite3'))
    sock=socket.socket();sock.bind(('127.0.0.1',0));url='http://127.0.0.1:'+str(sock.getsockname()[1])
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',loop='asyncio'))
    thread=Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start();verification={}
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline;time.sleep(.05)
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport=dict(width=1600,height=1000));errors=[];mutations=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:mutations.append(r.url) if r.method in ('POST','PATCH','PUT','DELETE') else None)
                base='/api/backtests/batches/'+BATCH
                before=page.request.get(url+base+'/results?limit=1000').json()
                (output/'results.json').write_text(json.dumps(before,indent=2)+'\n')
                page.goto(url+'/#backtests/batches/'+BATCH)
                expect(page.locator('#optimization-results tbody tr')).to_have_count(50,timeout=30000)
                page.locator('#optimization-freeze summary').click()
                page.get_by_role('button',name='Hide all',exact=True).click()
                columns=['trial','historical_net','lucid_historical_net','max_drawdown_pct','max_drawdown_duration_seconds','run_id']
                for key in columns:page.locator('.optimization-column-choice[data-column="'+key+'"] input[data-control="show"]').check()
                page.locator('#optimization-freeze summary').click()
                expect(page.locator('th[data-column="historical_net"]')).to_contain_text('Apex historical net /slot')
                expect(page.locator('th[data-column="lucid_historical_net"]')).to_contain_text('Lucid historical net / slot')
                expect(page.locator('th[data-column="max_drawdown_duration_seconds"]')).to_contain_text('trading days')
                # Exact numeric cell matching keeps trial 4 distinct from 14/40.
                row=page.locator('#optimization-results tbody tr').filter(has=page.locator('td[data-column="trial"]').get_by_text('4',exact=True))
                expect(row.locator('[data-column="max_drawdown_pct"]')).to_have_text('11.38')
                expect(row.locator('[data-column="max_drawdown_duration_seconds"]')).to_have_text('199')
                expect(row.locator('[data-column="historical_net"] a')).to_have_text('$8,832')
                expect(row.locator('[data-column="lucid_historical_net"] a')).to_have_text('$7,490')
                for key in ('historical_net','lucid_historical_net'):
                    cells=page.locator('td[data-column="'+key+'"]')
                    expect(cells.filter(has_not_text='N/A').locator('small')).to_have_count(0)
                    for unavailable in cells.filter(has_text='N/A').all():
                        assert unavailable.locator('small').count()>0
                page.screenshot(path=str(output/'table.png'),full_page=True)
                for metric in ('max_drawdown_duration_seconds','historical_net','lucid_historical_net'):
                    for direction in ('ascending','descending'):
                        page.locator('th[data-column="'+metric+'"] button').click()
                        expect(page.locator('th[data-column="'+metric+'"]')).to_have_attribute('aria-sort',direction)
                for selector,name in [('#optimization-download','results.csv'),('#optimization-original-download','original-results.csv')]:
                    with page.expect_download() as downloaded:page.locator(selector).click()
                    downloaded.value.save_as(output/name)
                exported=list(csv.DictReader(io.StringIO((output/'results.csv').read_text())))
                raw=next(r for r in exported if r['trial']=='4')
                assert raw['historical_net']=='176638' and raw['lucid_historical_net']=='37452'
                assert raw['max_drawdown_duration_seconds']=='24096000'
                # Open the same durable analysis: its cash totals retain all slots.
                page.goto(url+'/#backtests/prop/job/74e35dc0382343fa85a56645d561f6d3')
                expect(page.locator('#prop-report')).to_be_visible()
                page.get_by_role('tab',name='Historical replay',exact=True).click()
                expect(page.locator('#prop-view-history')).to_contain_text('$176,638')
                page.screenshot(path=str(output/'original-report-total.png'),full_page=True)
                page.goto(url+'/#backtests/batches/'+BATCH);expect(page.locator('#optimization-results tbody tr')).to_have_count(50)
                page.reload();expect(page.locator('#optimization-results tbody tr')).to_have_count(50)
                assert page.request.get(url+base+'/results?limit=1000').json()==before
                assert not mutations and not errors,(mutations,errors)
                verification=dict(batch_id=BATCH,trial4=dict(drawdown_pct='11.38',trading_days=199,
                    apex_per_slot=8831.9,lucid_per_slot=7490.4,apex_total=176638,lucid_total=37452),
                    saved_api_results_unchanged=True,raw_csv_units_preserved=True,sorting=True,
                    report_navigation_and_reload=True,mutating_requests=mutations,browser_errors=errors)
            finally:browser.close()
    finally:
        server.should_exit=True;thread.join(15);sock.close();assert not thread.is_alive()
        verification['temporary_server_stopped']=True
        (output/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
    print(json.dumps(verification))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    review(parser.parse_args().output)

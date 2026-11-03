"""Existing saved backtest -> joint sizing -> normal durable report.

Owns a temporary server and Chromium instance. Publishes through the existing
AnalysisStore only. Requires an idle catalogue; no strategy backtest is run.
"""
import argparse
from contextlib import contextmanager
from decimal import Decimal
import json
from pathlib import Path
import socket
import sqlite3
from threading import Thread
import time
from types import SimpleNamespace

import numpy as np
from playwright.sync_api import expect, sync_playwright
import uvicorn

from alphaquest.app import create_app
from alphaquest.prop.native_analysis import prepare, day_book
from alphaquest.prop.lucid_backend import evaluation
from review_lucid_funding_reference import ledger


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def review(data, old_id, output):
    output.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(f'file:{data / "backtests.sqlite3"}?mode=ro', uri=True) as db:
        assert not db.execute("SELECT 1 FROM optimizations WHERE json_extract(payload,'$.status') IN ('queued','running')").fetchone(), 'Review requires an idle catalogue'
    with sqlite3.connect(f'file:{data / "prop_analyses/catalog.sqlite3"}?mode=ro', uri=True) as db:
        assert not db.execute("SELECT 1 FROM analyses WHERE status IN ('queued','running')").fetchone(), 'Review requires idle analyses'
    sock=socket.socket();sock.bind(('127.0.0.1',0))
    url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(create_app(data/'datasets.sqlite3'),log_level='error',loop='asyncio'))
    thread=Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline
            time.sleep(.05)
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch()
            try:
                page=browser.new_page(viewport=dict(width=1440,height=1100))
                posts=[];errors=[]
                page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
                page.on('pageerror',lambda error:errors.append(str(error)))
                def get(path):
                    response=page.request.get(url+path)
                    assert response.ok,response.text()
                    return response
                old_bytes=get('/api/prop-analyses/'+old_id+'/downloads/report.json').body()
                old=json.loads(old_bytes);source_id=old['source']['backtest']['id']
                source_bytes=get('/api/backtests/'+source_id+'/exports/trades').body()
                (output/'earlier-report.json').write_bytes(old_bytes)
                page.goto(url+'/#backtests/report/'+source_id)
                expect(page.locator('#report-prop-setup')).to_be_visible(timeout=30000)
                page.screenshot(path=str(output/'01-backtest.png'),full_page=True)
                page.goto(url+'/#backtests/prop/job/'+old_id)
                expect(page.locator('#prop-report')).to_be_visible()
                expect(page.locator('#prop-report-content')).to_contain_text('Saved earlier model:')
                page.get_by_role('link',name='Configure new analysis',exact=True).click()
                expect(page.locator('#prop-config')).to_be_visible()
                with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:
                    page.locator('#prop-check').click()
                assert checked.value.status==200
                check=checked.value.json()
                assert check['settings']==old['settings'] and check['source']==old['source']
                save(output/'source-check.json',check)
                page.screenshot(path=str(output/'02-source-check.png'),full_page=True)
                with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses') and r.request.method=='POST') as submitted:
                    page.locator('#prop-run').click()
                assert submitted.value.status==202
                id=submitted.value.json()['id'];print('Joint analysis:',id,flush=True)
                save(output/'submitted-job.json',submitted.value.json())
                deadline=time.monotonic()+1800;previous=None
                while not page.locator('#prop-report').is_visible():
                    job=get('/api/prop-analyses/'+id).json()
                    assert job['status']!='error',job
                    if job['progress']!=previous:
                        print(job['status'],job['progress'],flush=True);previous=job['progress']
                    assert time.monotonic()<deadline
                    page.wait_for_timeout(500)
                report=get('/api/prop-analyses/'+id+'/downloads/report.json').json()
                save(output/'report.json',report)
                assert id!=old_id and report['source']==old['source'] and report['settings']==old['settings']
                joint=report['calculations']['joint_sizing'];chosen=joint['selected']
                assert joint['status']=='selected',joint['reason']
                ranked=[r for r in joint['pairs'] if r['status']=='ranked']
                for row in ranked:
                    expected=Decimal(261)*(Decimal(str(row['expected_receipts']))-Decimal(str(row['acquisition_cost'])))/(Decimal(str(row['funded_days']))+Decimal(str(row['acquisition_days'])))
                    assert abs(Decimal(str(row['slot_year']))-expected)<Decimal('.000000001')
                expected=max(ranked,key=lambda r:(r['slot_year'],-r['acquisition_cost'],-r['funded_micros'],-r['evaluation_micros']))
                assert chosen==expected
                assert all(r['upper_bound']<chosen['slot_year'] for r in joint['pairs'] if r['status']=='bounded')
                page.get_by_role('tab',name='Sizing',exact=True).click()
                expect(page.locator('#prop-joint-sizing')).to_contain_text('Evaluation and funded sizes chosen together')
                page.screenshot(path=str(output/'03-joint-sizing.png'),full_page=True)
                for name in ['joint_sizing.json','joint_sizing.csv','training_economics.json']:
                    (output/name).write_bytes(get('/api/prop-analyses/'+id+'/files/'+name).body())
                page.get_by_role('tab',name='Evaluation',exact=True).click()
                page.screenshot(path=str(output/'04-evaluation.png'),full_page=True)
                page.get_by_role('tab',name='Historical replay',exact=True).click()
                page.screenshot(path=str(output/'05-history.png'),full_page=True)
                page.get_by_role('tab',name='Source & model',exact=True).click()
                with page.expect_download() as download:page.get_by_role('link',name='Download all results (ZIP)',exact=True).click()
                download.value.save_as(output/'analysis.zip')
                page.reload();expect(page.locator('#prop-report')).to_be_visible()
                assert get('/api/prop-analyses/'+old_id+'/downloads/report.json').body()==old_bytes
                assert get('/api/backtests/'+source_id+'/exports/trades').body()==source_bytes
                assert not any('/api/backtests' in path for path in posts) and not errors
                save(output/'portal-verification.json',dict(old_id=old_id,new_id=id,source_id=source_id,
                    selected=chosen,pairs_checked=len(ranked),total_pairs=len(joint['pairs']),
                    history=report['calculations']['history']['totals'],holdout=joint['validation'],
                    prior_report_and_source_unchanged=True,backtest_posts=0,javascript_errors=errors))
            finally:browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=60);sock.close()
        assert not thread.is_alive(),'Temporary review server did not stop'
    # Independent scalar chains after closing the browser/server. This only
    # reads immutable source files and checks the published training economics.
    @contextmanager
    def connect():
        db=sqlite3.connect(f'file:{data / "backtests.sqlite3"}?mode=ro',uri=True)
        try:yield db
        finally:db.close()
    snapshot,rows,settings=prepare(SimpleNamespace(root=data/'backtest_runs',connect=connect),source_id,'',report['settings'])
    _,days,split=day_book(rows,settings)
    dll=1200. if settings['DAILY_LOSS_LIMIT']=='on' else None
    expected=ledger(days[:split],20000,45,int(settings['BLOCK_DAYS']),chosen['evaluation_micros'],dll)
    actual=evaluation(days[:split],chosen['evaluation_micros'],20000,45,int(settings['BLOCK_DAYS']),chain=True,daily_loss=dll)
    assert np.array_equal(expected,np.column_stack([actual['days'],actual['attempts'],actual['longest_attempt_days']]))
    assert float(expected[:,0].mean())==report['calculations']['training_economics']['replacement_days']
    np.savez_compressed(output/'independent-training-chains.npz',actual=actual['days'],independent=expected)
    save(output/'independent-verification.json',dict(simulations=20000,every_training_chain_matches=True,
        mean_days=float(expected[:,0].mean()),source_trades_sha256=snapshot['trades_sha256'],temporary_server_stopped=True))
    print(json.dumps(dict(id=id,selected=chosen,independent_chains=20000,temporary_server_stopped=True)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('data'))
    parser.add_argument('--old-id',default='9994b7072e2e46e19f6c6c28540041ce')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    review(args.data.resolve(),args.old_id,args.output)

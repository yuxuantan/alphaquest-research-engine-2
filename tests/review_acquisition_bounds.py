"""Actual saved Apex reports through configure/check/run; no strategy reruns.

Publishes new reports through the normal catalogue, owns and closes a temporary
server/browser, and independently checks probability bounds, pair scores, cash
accounting and all selected training funding chains.
"""
import argparse
from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal, localcontext
import json
from math import comb
from pathlib import Path
import socket
import sqlite3
from threading import Thread
import time
from types import SimpleNamespace

import numpy as np
from playwright.sync_api import sync_playwright, expect
import uvicorn

from alphaquest.app import create_app
from alphaquest.prop.native_analysis import prepare, day_book
from alphaquest.prop.native_backend import evaluation


def save(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def apex_chains(days,size,count=20000,seed=45,block=5):
    """Scalar MT19937 and first-adverse ledger, independent of account helpers."""
    rng=np.random.RandomState(seed);values=[]
    for _ in range(count):
        def sessions():
            while True:
                start=int(rng.randint(len(days)))
                for offset in range(block):yield days[(start+offset)%len(days)]
        source=sessions();total=0
        for attempt in range(1,10001):
            balance=peak=0.;outcome='timeout'
            for day in range(1,22):
                opened=balance;floor=min(peak-2000.,3000.);daily=opened-1000.;stop=max(floor,daily)
                for trade in next(source):
                    before=balance;hit=None
                    if before-trade[1]*size/10.<=stop and len(trade)>2:
                        for loss,jump in trade[2]:
                            mark=before-loss*size/10.
                            if mark<=stop:
                                balance=mark if jump else stop
                                hit='blown' if (balance<=floor if jump else floor>=daily) else 'pause'
                                break
                    if hit is None and before-trade[1]*size/10.<=stop:
                        balance=stop;hit='blown' if floor>=daily else 'pause'
                    if hit:
                        if hit=='blown':outcome='blown'
                        break
                    balance=before+trade[0]*size/10.
                    if daily>floor and balance<=daily:
                        balance=daily;break
                    if daily<=floor and balance<=floor:
                        outcome='blown';break
                    if balance>=3000.:
                        outcome='passed';break
                peak=max(peak,balance)
                if outcome!='timeout':break
            total+=day
            if outcome=='passed':break
        else:raise AssertionError('Independent funding chain did not resolve')
        values.append((total+1,attempt)) # Apex activation weekday.
    return np.array(values)


def check_bounds(joint):
    for candidate in joint['excluded_acquisition_candidates']+joint['blocking_acquisition_candidates']:
        with localcontext() as ctx:
            ctx.prec=60
            n=candidate['simulations'];k=candidate['passed']
            p=Decimal(str(candidate['pass_probability_upper']))
            target=Decimal('.05')/Decimal(candidate['bound_candidate_count'])
            # Actual affected Apex profiles contain uncensored evaluations.
            cdf=sum(Decimal(comb(n,index))*p**index*(1-p)**(n-index) for index in range(k+1))
            assert abs(cdf-target)<target*Decimal('0.0000001')
            minimum=Decimal(49)/p+Decimal(129)
            assert abs(minimum-Decimal(str(candidate['acquisition_cost_lower_bound'])))<Decimal('.000001')
    for row in joint['pairs']:
        if row['status']=='ranked':
            expected=Decimal(261)*(Decimal(str(row['expected_receipts']))-Decimal(str(row['acquisition_cost'])))/(Decimal(str(row['funded_days']))+Decimal(str(row['acquisition_days'])))
            assert abs(expected-Decimal(str(row['slot_year'])))<Decimal('.000000001')
        if row['status']=='excluded':
            assert row['acquisition_days'] is None and row['slot_year'] is None
            assert row['upper_bound']<joint['selected']['slot_year']


def check_cash(report):
    c=report['calculations'];slots=int(report['settings']['SLOTS']);ladder=c['rules']['ladder']
    receipts=defaultdict(Decimal);costs=defaultdict(Decimal)
    def quarter(date):return date[:4]+'Q'+str((int(date[5:7])-1)//3+1)
    for account in c['history']['accounts']:
        costs[quarter(account['start'])]+=Decimal(str(c['training_economics']['cost_per_funded']))*slots
        for index,date in enumerate(account['payout_days']):receipts[quarter(date)]+=Decimal(str(ladder[index]))*slots
    for q in c['history']['quarters']:
        assert q['payouts']==round(receipts[q['period']])
        assert q['costs']==round(costs[q['period']])
        assert q['net']==q['payouts']-q['costs']


def review(data,output):
    output.mkdir(parents=True,exist_ok=False)
    for path,sql in [(data/'backtests.sqlite3',"select 1 from optimizations where json_extract(payload,'$.status') in ('queued','running')"),
                     (data/'prop_analyses/catalog.sqlite3',"select 1 from analyses where status in ('queued','running')")]:
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as db:assert db.execute(sql).fetchone() is None,'Review requires an idle catalogue'
    sock=socket.socket();sock.bind(('127.0.0.1',0));url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(create_app(data/'datasets.sqlite3'),log_level='error',loop='asyncio'))
    thread=Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    results=[]
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert time.monotonic()<deadline and thread.is_alive();time.sleep(.05)
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch()
            try:
                page=browser.new_page(viewport=dict(width=1600,height=1100));posts=[];errors=[]
                page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
                page.on('pageerror',lambda error:errors.append(str(error)))
                def get(path):
                    response=page.request.get(url+path);assert response.ok,response.text();return response
                for label,old_id,expected_status in [('trial-4','2f616c80f6d74bd4b01423af27eadcad','selected'),
                                                     ('trial-21','2030900931bc4dde9dd7effaa1d919f4','unavailable')]:
                    directory=output/label;directory.mkdir()
                    old_bytes=get('/api/prop-analyses/'+old_id+'/downloads/report.json').body();old=json.loads(old_bytes)
                    source_id=old['source']['backtest']['id'];source_bytes=get('/api/backtests/'+source_id+'/exports/trades').body()
                    (directory/'earlier-report.json').write_bytes(old_bytes)
                    page.goto(url+'/#backtests/report/'+source_id)
                    expect(page.locator('#report-prop-setup')).to_be_visible(timeout=30000)
                    page.screenshot(path=str(directory/'01-backtest.png'),full_page=True)
                    page.goto(url+'/#backtests/prop/job/'+old_id);expect(page.locator('#prop-report')).to_be_visible()
                    page.get_by_role('link',name='Configure new analysis',exact=True).click()
                    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:page.locator('#prop-check').click()
                    assert checked.value.status==200
                    check=checked.value.json();assert check['settings']==old['settings'] and check['source']==old['source']
                    save(directory/'source-check.json',check)
                    page.screenshot(path=str(directory/'02-source-check.png'),full_page=True)
                    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses') and r.request.method=='POST') as submitted:page.locator('#prop-run').click()
                    assert submitted.value.status==202
                    id=submitted.value.json()['id'];print(label,id,flush=True)
                    save(directory/'submitted-job.json',submitted.value.json())
                    deadline=time.monotonic()+1800;last=None
                    while not page.locator('#prop-report').is_visible():
                        job=get('/api/prop-analyses/'+id).json();assert job['status']!='error',job
                        if job['progress']!=last:print(label,job['progress'],flush=True);last=job['progress']
                        assert time.monotonic()<deadline;page.wait_for_timeout(500)
                    report=get('/api/prop-analyses/'+id+'/downloads/report.json').json();save(directory/'report.json',report)
                    assert id!=old_id and report['source']==old['source'] and report['settings']==old['settings']
                    joint=report['calculations']['joint_sizing'];assert joint['status']==expected_status
                    check_bounds(joint)
                    page.get_by_role('tab',name='Sizing',exact=True).click()
                    if expected_status=='selected':
                        expected=max((r for r in old['calculations']['joint_sizing']['pairs'] if r['status']=='ranked'),key=lambda r:r['slot_year'])
                        assert joint['selected']['evaluation_micros']==expected['evaluation_micros']==40
                        assert joint['selected']['funded_micros']==expected['funded_micros']==8
                        assert joint['selected']['slot_year']==expected['slot_year']
                        assert [e['evaluation_micros'] for e in joint['excluded_acquisition_candidates']]==[3]
                        expect(page.locator('#prop-acquisition-exclusions')).to_contain_text('Uncompetitive evaluation sizes excluded')
                        page.screenshot(path=str(directory/'03-exclusion-and-selection.png'),full_page=True)
                        page.locator('#prop-joint-eval-filter').select_option('3')
                        expect(page.locator('#prop-joint-pairs')).to_contain_text('excluded')
                        page.screenshot(path=str(directory/'04-excluded-pairs.png'),full_page=True)
                        page.get_by_role('tab',name='Historical replay',exact=True).click()
                        check_cash(report)
                        page.screenshot(path=str(directory/'05-historical-net.png'),full_page=True)
                    else:
                        assert report['calculations']['history'] is None and report['calculations']['funded'] is None
                        assert joint['blocking_acquisition_candidates'] and not joint['selected']
                        expect(page.locator('#prop-joint-sizing')).to_contain_text('cannot be excluded by their optimistic bounds')
                        page.screenshot(path=str(directory/'03-genuine-ambiguity.png'),full_page=True)
                    for name in ['joint_sizing.json','joint_sizing.csv','training_economics.json']:
                        (directory/name).write_bytes(get('/api/prop-analyses/'+id+'/files/'+name).body())
                    page.get_by_role('tab',name='Source & model',exact=True).click()
                    with page.expect_download() as download:page.get_by_role('link',name='Download all results (ZIP)',exact=True).click()
                    download.value.save_as(directory/'analysis.zip')
                    page.reload();expect(page.locator('#prop-report')).to_be_visible()
                    assert get('/api/prop-analyses/'+old_id+'/downloads/report.json').body()==old_bytes
                    assert get('/api/backtests/'+source_id+'/exports/trades').body()==source_bytes
                    results.append(dict(case=label,old_id=old_id,new_id=id,status=joint['status'],selected=joint['selected'],
                        exclusions=joint['excluded_acquisition_candidates'],blockers=joint['blocking_acquisition_candidates'],
                        history=report['calculations'].get('history',{}),original_source_and_report_unchanged=True))
                assert not any('/api/backtests' in path for path in posts) and not errors
                save(output/'portal-verification.json',dict(cases=results,backtest_posts=0,javascript_errors=errors))
            finally:browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=60);sock.close();assert not thread.is_alive()
    positive=json.loads((output/'trial-4/report.json').read_text())
    @contextmanager
    def connect():
        db=sqlite3.connect(f'file:{data / "backtests.sqlite3"}?mode=ro',uri=True)
        try:yield db
        finally:db.close()
    _,rows,settings=prepare(SimpleNamespace(root=data/'backtest_runs',connect=connect),positive['source']['backtest']['id'],'',positive['settings'])
    _,days,split=day_book(rows,settings);size=positive['calculations']['joint_sizing']['selected']['evaluation_micros'];block=int(settings['BLOCK_DAYS'])
    expected=apex_chains(days[:split],size,block=block)
    actual=evaluation(days[:split],size,20000,45,block,chain=True)
    observed=np.column_stack([actual['days'],actual['attempts']])
    assert np.array_equal(observed,expected)
    assert float(expected[:,0].mean())==positive['calculations']['training_economics']['replacement_days']
    np.savez_compressed(output/'independent-training-chains.npz',actual=observed,independent=expected)
    save(output/'independent-verification.json',dict(chains=20000,every_chain_matches=True,mean_days=float(expected[:,0].mean()),
        exact_binomial_bounds_independently_verified=True,pair_scores_independently_verified=True,historical_cash_independently_reconciled=True,temporary_server_stopped=True))
    print(json.dumps([dict(case=r['case'],id=r['new_id'],status=r['status'],selected=r['selected']) for r in results]),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('data'))
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    review(args.data.resolve(),args.output)

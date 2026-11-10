"""Normal-product synthetic early-close demo; server stops automatically.

.venv/bin/python tests/review_twin_calendar.py --output artifacts/twin-calendar-NEW
"""
import argparse
from dataclasses import replace
from datetime import datetime,timedelta
from decimal import Decimal
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright,expect

from review_optimization_portal import serve_review
from research_fixtures import reserved_source,declare_in_form
from prop_setup_helpers import open_prop_task
from test_backtests_browser import set_parameter
from test_twin_continuation import momentum_rows,momentum_parameters,prices,CT,config
from test_twin_continuation_api import csv_bytes,values
from alphaquest.strategies.twin_continuation import Parameters,TwinContinuation
from alphaquest.execution import execute,Trade


def early_rows():
    all_rows=[]
    for index,day in enumerate(('2024-06-19','2024-07-04')):
        rows=momentum_rows(day)[:26]
        if index:
            start=rows[0].timestamp_utc
            rows=[prices(1,start-timedelta(minutes=15-i)) for i in range(15)]+rows
        rows.extend([prices(1,datetime.fromisoformat(day+'T11:59:00').replace(tzinfo=CT),120,121,119,120),
                     prices(1,datetime.fromisoformat(day+'T12:00:00').replace(tzinfo=CT),120,121,119,120),
                     prices(1,datetime.fromisoformat(day+'T17:01:00').replace(tzinfo=CT),120,121,119,120)])
        all_rows.extend(rows)
    return [replace(b,bar_number=i+1) for i,b in enumerate(all_rows)]


def review(output,url):
    raw,split=reserved_source(csv_bytes(early_rows()))
    source=output/'SYNTHETIC-Twin-two-noon-closes.csv';source.write_bytes(raw)
    with sync_playwright() as runtime,httpx.Client(base_url=url,timeout=120) as client:
        browser=runtime.chromium.launch()
        try:
            page=browser.new_page(viewport=dict(width=1440,height=1000));page.set_default_timeout(60000)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url);page.locator('#csv-file').set_input_files(source)
            page.locator('#dataset-name').fill('SYNTHETIC Twin two scheduled noon closes')
            page.locator('#symbol').fill('NQ');page.locator('#source-timezone').select_option('UTC')
            page.locator('#dataset-tick-size').fill('.25');page.locator('#dataset-point-value').fill('20')
            page.locator('#validate-button').click();expect(page.locator('#validation-result')).to_contain_text('Validation passed')
            page.locator('#save-button').click();expect(page.locator('#validation-result')).to_contain_text('Dataset saved')
            dataset=client.get('/api/datasets').json()[0]
            page.goto(url+'/#backtests/new');page.locator('#backtest-dataset').select_option(dataset['id'])
            page.locator('#backtest-strategy').select_option('twin_continuation');declare_in_form(page,split)
            defaults=values(Parameters())
            for name,value in values(momentum_parameters()).items():
                if value!=defaults[name]:set_parameter(page,name,value if type(value) is bool else str(value))
            expect(page.locator('#backtest-session-calendar')).to_contain_text('scheduled closing bar Close')
            page.locator('#backtest-slippage-ticks').fill('1');page.locator('#backtest-commission').fill('1')
            page.locator('#optimization-automatic-prop').uncheck()
            page.screenshot(path=str(output/'configuration.png'),full_page=True)
            with page.expect_response(lambda r:r.url.endswith('/api/backtests') and r.request.method=='POST') as completed:
                page.locator('#start-backtest').click()
            assert completed.value.status==202,completed.value.text()
            job=completed.value.json()['id']
            expect(page.locator('#optimization-status')).to_contain_text('COMPLETE',timeout=120000)
            trial=client.get(f'/api/optimizations/{job}/results').json()['items'][0]
            run=trial['run_id'];record=client.get(f'/api/backtests/{run}').json()
            assert record['run_metadata']['strategy']['parameters']['use_session_calendar'] is True
            page.goto(url+'/#backtests/report/'+run)
            expect(page.locator('#backtest-completion')).to_be_visible()
            trades=client.get(f'/api/backtests/{run}/trades').json()['items']
            assert len(trades)==2 and Decimal(record['summary']['total_net_pnl'])==296
            for t,day in zip(trades,('2024-06-19','2024-07-04')):
                assert t['exit_time_utc']==day+'T17:00:00Z' and t['exit_reason']=='session_close'
                assert Decimal(t['entry_fill_price'])==Decimal('112.25') and Decimal(t['exit_fill_price'])==Decimal('119.75')
                assert Decimal(t['net_pnl'])==148
            flatten=record['run_metadata']['strategy']['session_flattening']
            assert flatten['mode']=='twin_csv_session_close_v2' and flatten['minutes_before_close']==0
            setting=page.locator("[data-setting='session_flattening']")
            setting.evaluate("el=>{const d=el.closest('details');if(d)d.open=true;}")
            expect(setting).to_contain_text('scheduled closing bar Close')
            expect(setting).to_contain_text('no next-Open buffer')
            page.screenshot(path=str(output/'backtest-report.png'),full_page=True)
            for kind in ('report','trades','equity'):
                response=client.get(f'/api/backtests/{run}/exports/{kind}');assert response.status_code==200
                (output/f'{kind}.{ "json" if kind=="report" else "csv"}').write_bytes(response.content)
            page.reload();expect(page.locator('#backtest-completion')).to_be_visible()
            page.locator('#report-prop-setup').click();expect(page.locator('#prop-config')).to_be_visible()
            open_prop_task(page,'legacy')
            page.locator('#prop-advanced > summary').click()
            page.locator('#prop-max-nq').fill('0.1')
            page.locator('#prop-commission-mode').select_option('source')
            with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:page.locator('#prop-check').click()
            assert checked.value.status==200,checked.value.text()
            check=checked.value.json()
            assert Decimal(check['source']['reconciliation']['source_totals']['net_pnl'])==296
            assert check['source']['excursion_input']['measured_mae_count']==0
            (output/'source-check.json').write_text(json.dumps(check,indent=2)+'\n')
            page.screenshot(path=str(output/'source-check.png'),full_page=True)
            with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses') and r.request.method=='POST') as submitted:page.locator('#prop-run').click()
            assert submitted.value.status==202,submitted.value.text()
            analysis=submitted.value.json()['id'];expect(page.locator('#prop-report')).to_be_visible(timeout=120000)
            report=client.get(f'/api/prop-analyses/{analysis}/downloads/report.json');assert report.status_code==200
            (output/'prop-report.json').write_bytes(report.content)
            archive=client.get(f'/api/prop-analyses/{analysis}/downloads/analysis.zip');assert archive.status_code==200
            (output/'analysis.zip').write_bytes(archive.content)
            page.screenshot(path=str(output/'prop-report.png'),full_page=True)
            page.reload();expect(page.locator('#prop-report')).to_be_visible()
            assert client.get(f'/api/prop-analyses/{analysis}/downloads/report.json').content==report.content
            assert client.get(f"/api/datasets/{dataset['id']}/csv").content==raw
            assert not errors,errors
            result=dict(synthetic=True,source_id=dataset['id'],run_id=run,analysis_id=analysis,optimization_id=job,automatic_prop=False,
                expected_net='296',trades=trades,calendar=flatten,source_unchanged=True,reopened=True,browser_errors=errors)
            (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps(dict(run_id=run,analysis_id=analysis,optimization_id=job,automatic_prop=False,net=record['summary']['total_net_pnl']),indent=2))
        finally:browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    serve_review(parser.parse_args().output,review)

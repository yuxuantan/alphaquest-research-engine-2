"""Demonstrate an actionable Twin session-close rejection in the normal UI.

.venv/bin/python tests/review_twin_session_rejection.py --output artifacts/twin-rejection-NEW
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import parse_qs,urlparse

import httpx
from playwright.sync_api import sync_playwright,expect

from review_optimization_portal import serve_review
from research_fixtures import reserved_source,declare_in_form
from test_backtests_browser import set_parameter
from test_twin_continuation import momentum_rows,momentum_parameters,prices,CT,Parameters
from test_twin_continuation_api import csv_bytes,values


def review(output,url):
    rows=momentum_rows()[:26]
    rows.extend([prices(27,datetime(2024,1,16,12,0,tzinfo=CT),120,121,119,120),
                 prices(28,datetime(2024,1,16,17,1,tzinfo=CT),120,121,119,120)])
    raw,split=reserved_source(csv_bytes(rows))
    source=output/'SYNTHETIC-Twin-session-gap.csv';source.write_bytes(raw)
    with sync_playwright() as runtime,httpx.Client(base_url=url,timeout=60) as client:
        browser=runtime.chromium.launch()
        try:
            page=browser.new_page(viewport=dict(width=1440,height=1000));page.set_default_timeout(30000)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url)
            page.locator('#csv-file').set_input_files(source)
            page.locator('#dataset-name').fill('SYNTHETIC Twin session-close rejection')
            page.locator('#symbol').fill('NQ');page.locator('#source-timezone').select_option('UTC')
            page.locator('#dataset-tick-size').fill('0.25');page.locator('#dataset-point-value').fill('20')
            page.locator('#validate-button').click();expect(page.locator('#validation-result')).to_contain_text('Validation passed')
            page.locator('#save-button').click();expect(page.locator('#validation-result')).to_contain_text('Dataset saved')
            dataset=client.get('/api/datasets').json()[0]
            page.goto(url+'/#backtests/new');page.locator('#backtest-dataset').select_option(dataset['id'])
            page.locator('#backtest-strategy').select_option('twin_continuation');declare_in_form(page,split)
            defaults=values(Parameters())
            for name,value in values(momentum_parameters()).items():
                if value!=defaults[name]:set_parameter(page,name,value if type(value) is bool else str(value))
            page.locator('#backtest-slippage-ticks').fill('1');page.locator('#backtest-commission').fill('1')
            page.screenshot(path=str(output/'configuration.png'),full_page=True)
            with page.expect_response(lambda r:'/api/backtests?' in r.url and r.request.method=='POST') as finished:
                page.locator('#start-backtest').click()
            response=finished.value;assert response.status==422,response.text()
            error=response.json()['detail']
            for text in ('2024-01-16 16:00','2024-01-16 12:00','2024-01-16 17:01','selected bar 28','holding MO long','shortened-session policy'):
                expect(page.locator('#backtest-error')).to_contain_text(text)
            expect(page.locator('#backtest-progress-title')).to_have_text('Backtest failed')
            operation=parse_qs(urlparse(response.url).query)['progress_id'][0]
            progress=client.get('/api/progress/'+operation).json()
            assert progress['stage']=='failed' and progress['error']==error
            assert client.get('/api/backtests').json()['total']==0
            assert client.get('/api/datasets/'+dataset['id']+'/csv').content==raw
            page.screenshot(path=str(output/'actionable-error.png'),full_page=True)
            result=dict(synthetic=True,http_status=response.status,error=error,progress=progress,
                completed_runs=0,source_unchanged=True,split=split,browser_errors=errors)
            assert not errors,errors
            (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps(result,indent=2))
        finally:browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    serve_review(parser.parse_args().output,review)

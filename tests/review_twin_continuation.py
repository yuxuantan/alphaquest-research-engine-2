"""Saved normal-product demonstration, in a new isolated library.

.venv/bin/python tests/review_twin_continuation.py --output artifacts/twin-review-NEW
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect

from review_optimization_portal import serve_review
from research_fixtures import reserved_source, declare_in_form
from test_backtests_browser import set_parameter
from prop_setup_helpers import open_prop_task
from test_twin_continuation import momentum_rows, momentum_two_session_rows, momentum_parameters, breakout_rows, Parameters
from test_twin_continuation_api import csv_bytes, values


def review(output,url):
    observations=[]
    with sync_playwright() as runtime, httpx.Client(base_url=url,timeout=90) as client:
        browser=runtime.chromium.launch()
        page=browser.new_page(viewport=dict(width=1440,height=1100))
        page.set_default_timeout(45000)
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        for name,rows,p,expected in (
            ('momentum',momentum_rows(),momentum_parameters(),dict(entry='112.25',exit='119.75',net='148',reason='MO-L')),
            ('breakout',breakout_rows(),Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1,immediate_protection=False),
             dict(entry='110.25',exit='126.25',net='318',reason='BO-L')),
            ('momentum-prop',momentum_two_session_rows(),momentum_parameters(),dict(entry='112.25',exit='119.75',net='296',reason='MO-L'))):
            raw,split=reserved_source(csv_bytes(rows))
            source=output/f'SYNTHETIC-twin-{name}.csv';source.write_bytes(raw)
            page.goto(url)
            page.locator('#csv-file').set_input_files(source)
            page.locator('#dataset-name').fill('SYNTHETIC Twin '+name)
            page.locator('#symbol').fill('NQ')
            page.locator('#source-timezone').select_option('UTC')
            page.locator('#dataset-tick-size').fill('0.25')
            page.locator('#dataset-point-value').fill('20')
            page.locator('#validate-button').click()
            expect(page.locator('#validation-result')).to_contain_text('Validation passed')
            page.locator('#save-button').click()
            expect(page.locator('#validation-result')).to_contain_text('Dataset saved')
            dataset=next(d for d in client.get('/api/datasets').json() if d['name']=='SYNTHETIC Twin '+name)
            page.goto(url+'/#backtests/new')
            page.locator('#backtest-dataset').select_option(dataset['id'])
            page.locator('#backtest-strategy').select_option('twin_continuation')
            declare_in_form(page,split)
            defaults=values(Parameters())
            for key,value in values(p).items():
                if value != defaults[key]:set_parameter(page,key,value if type(value) is bool else str(value))
            page.locator('#backtest-slippage-ticks').fill('1')
            page.locator('#backtest-commission').fill('1')
            expect(page.locator('#backtest-fill-assumption')).to_contain_text('OCO entry stops')
            page.screenshot(path=str(output/f'{name}-configuration.png'),full_page=True)
            with page.expect_response(lambda r:'/api/backtests?' in r.url and r.request.method=='POST',timeout=90000) as completed:
                page.locator('#start-backtest').click()
            record=completed.value.json()
            assert completed.value.status==201,record
            run=record['id']
            expect(page.locator('#backtest-completion')).to_be_visible()
            trade=client.get(f'/api/backtests/{run}/trades').json()['items'][0]
            assert Decimal(trade['entry_fill_price'])==Decimal(expected['entry'])
            assert Decimal(trade['exit_fill_price'])==Decimal(expected['exit'])
            assert Decimal(trade['net_pnl'])==Decimal('148' if name=='momentum-prop' else expected['net'])
            assert trade['entry_reason']==expected['reason']
            assert Decimal(record['summary']['total_net_pnl'])==Decimal(expected['net'])
            assert record['run_metadata']['strategy']['parameters']==values(p)
            for kind in ('trades','equity','report'):
                response=client.get(f'/api/backtests/{run}/exports/{kind}')
                assert response.status_code==200
                (output/f'{name}-{kind}.{ "json" if kind=="report" else "csv"}').write_bytes(response.content)
            assert client.get(f"/api/datasets/{dataset['id']}/csv").content==raw
            page.screenshot(path=str(output/f'{name}-report.png'),full_page=True)
            page.reload()
            expect(page.locator('#backtest-completion')).to_be_visible()
            page.locator('#report-prop-setup').click()
            expect(page.locator('#prop-config')).to_be_visible()
            open_prop_task(page,'legacy')
            with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:
                page.locator('#prop-check').click()
            if name!='momentum-prop':
                assert checked.value.status==422 and 'At least two session weekdays' in checked.value.text(),checked.value.text()
                (output/f'{name}-source-rejection.json').write_text(checked.value.text()+'\n')
                expect(page.locator('#prop-run')).to_be_disabled()
                page.screenshot(path=str(output/f'{name}-source-rejection.png'),full_page=True)
                observations.append(dict(case=name,dataset_id=dataset['id'],run_id=run,
                    portal_path=f'/#backtests/report/{run}',expected=expected,actual=trade,parameters=values(p),
                    split=split,source_unchanged=True,reopened_after_reload=True,
                    expected_source_rejection='At least two session weekdays are needed for separate training and validation.'))
                continue
            assert checked.value.status==200,checked.value.text()
            check=checked.value.json()
            assert Decimal(check['source']['reconciliation']['source_totals']['net_pnl'])==Decimal(expected['net'])
            assert check['source']['excursion_input']['measured_mae_count']==0
            (output/f'{name}-source-check.json').write_text(json.dumps(check,indent=2)+'\n')
            page.screenshot(path=str(output/f'{name}-source-check.png'),full_page=True)
            with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses') and r.request.method=='POST') as submitted:
                page.locator('#prop-run').click()
            assert submitted.value.status==202,submitted.value.text()
            analysis_id=submitted.value.json()['id']
            expect(page.locator('#prop-report')).to_be_visible(timeout=90000)
            report=client.get(f'/api/prop-analyses/{analysis_id}/downloads/report.json')
            assert report.status_code==200,report.text
            (output/f'{name}-prop-report.json').write_bytes(report.content)
            archive=client.get(f'/api/prop-analyses/{analysis_id}/downloads/analysis.zip')
            assert archive.status_code==200
            (output/f'{name}-analysis.zip').write_bytes(archive.content)
            page.screenshot(path=str(output/f'{name}-prop-report.png'),full_page=True)
            page.reload()
            expect(page.locator('#prop-report')).to_be_visible()
            assert client.get(f'/api/prop-analyses/{analysis_id}/downloads/report.json').content==report.content
            observations.append(dict(case=name,dataset_id=dataset['id'],run_id=run,analysis_id=analysis_id,
                portal_path=f'/#backtests/report/{run}',expected=expected,actual=trade,parameters=values(p),
                split=split,source_unchanged=True,reopened_after_reload=True,prop_reopened_after_reload=True))
            print(f'PASS {name}: {run}, expected/actual net {expected["net"]}')
        assert not errors,errors
        browser.close()
    (output/'verification.json').write_text(json.dumps(dict(synthetic=True,observations=observations,browser_errors=errors),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    serve_review(parser.parse_args().output,review)

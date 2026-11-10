"""Retain immediate/legacy examples through ordinary saved backtests and UI.

PYTHONPATH=.:tests .venv/bin/python tests/review_twin_immediate_protection.py --output artifacts/twin-immediate-product-NEW
Creates an isolated normal library, never edits the user's library or runs OOS.
"""
import argparse
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect

from review_optimization_portal import serve_review
from research_fixtures import reserved_source
from test_twin_continuation import momentum_rows, momentum_parameters, breakout_rows
from test_twin_continuation_api import csv_bytes, values
from alphaquest.strategies.twin_continuation import Parameters


def review(output,url):
    observations=[]
    with httpx.Client(base_url=url,timeout=90) as client, sync_playwright() as runtime:
        browser=runtime.chromium.launch()
        page=browser.new_page(viewport=dict(width=1440,height=1050))
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(url+'/#backtests/new')
        page.locator('#backtest-strategy').select_option('twin_continuation')
        mode=page.locator('#optimization-ranges tr[data-parameter="immediate_protection"]')
        expect(mode.locator('[data-range="start"]')).to_have_value('true')
        expect(page.locator('#backtest-fill-assumption')).to_contain_text('activate at fill')
        page.screenshot(path=str(output/'default-immediate-configuration.png'),full_page=True)
        datasets={}
        for kind,rows,p in (
            ('momentum',momentum_rows(),momentum_parameters(immediate_protection=True)),
            ('breakout',breakout_rows(),Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1))):
            raw,split=reserved_source(csv_bytes(rows))
            (output/('SYNTHETIC-'+kind+'.csv')).write_bytes(raw)
            response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-'+kind+'.csv',
                name='SYNTHETIC immediate protection '+kind,symbol='NQ',source_timezone='UTC',tick_size='.25',point_value='20'),content=raw)
            assert response.status_code==201,response.text
            dataset=response.json();datasets[kind]=(dataset,split,p)
            for immediate in (False,True):
                params=replace(p,immediate_protection=immediate)
                payload=dict(dataset_id=dataset['id'],strategy_id='twin_continuation',strategy_parameters=values(params),sample_split=split,
                    execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1'))
                response=client.post('/api/backtests',json=payload)
                assert response.status_code==201,response.text
                record=response.json();run=record['id']
                trade=client.get(f'/api/backtests/{run}/trades').json()['items'][0]
                expected_net=-1507 if kind=='momentum' and immediate else 148 if kind=='momentum' else 318
                expected_entry=26 if kind=='momentum' else 106
                expected_exit=expected_entry if immediate else 28 if kind=='momentum' else 107
                assert Decimal(trade['net_pnl'])==expected_net
                assert (trade['entry_bar_number'],trade['exit_bar_number'])==(expected_entry,expected_exit)
                activation=record['run_metadata']['strategy']['session_flattening']['protection_activation']
                assert activation==('on_entry_fill' if immediate else 'following_bar_legacy')
                label=kind+('-immediate' if immediate else '-legacy')
                for export in ('report','trades','intratrade_risk'):
                    saved=client.get(f'/api/backtests/{run}/exports/{export}')
                    assert saved.status_code==200,saved.text
                    (output/(label+'-'+export+('.json' if export=='report' else '.csv'))).write_bytes(saved.content)
                before=client.get(f'/api/backtests/{run}/exports/report').content
                page.goto(url+f'/#backtests/report/{run}')
                expect(page.locator('#backtest-completion')).to_be_visible(timeout=30000)
                page.screenshot(path=str(output/(label+'-report.png')),full_page=True)
                page.reload();expect(page.locator('#backtest-completion')).to_be_visible()
                assert client.get(f'/api/backtests/{run}/exports/report').content==before
                assert client.get(f"/api/datasets/{dataset['id']}/csv").content==raw
                observations.append(dict(case=label,run_id=run,dataset_id=dataset['id'],parameters=values(params),split=split,
                    expected_net=expected_net,expected_entry_bar=expected_entry,expected_exit_bar=expected_exit,actual=trade,
                    protection_activation=activation,reopened_unchanged=True,portal_path=f'/#backtests/report/{run}'))
        dataset,split,p=datasets['breakout']
        response=client.post('/api/backtests',json=dict(dataset_id=dataset['id'],strategy_id='twin_continuation',
            strategy_parameters=values(replace(p,bo_max_stop_mult=Decimal('.25'))),sample_split=split,
            execution_settings=dict(initial_capital='10000',slippage_ticks=1,commission_per_contract_per_side='1')))
        assert response.status_code==422 and 'Immediate entry protection is ambiguous' in response.text,response.text
        (output/'ambiguous-entry-protection-rejection.json').write_text(response.text+'\n')
        assert not errors,errors
        browser.close()
    result=dict(synthetic=True,observations=observations,ambiguous_entry_rejected=True,browser_errors=errors,
        oos_run=False,windows_multicharts_verified=False)
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([dict(case=o['case'],run_id=o['run_id'],net=o['actual']['net_pnl'],exit_bar=o['actual']['exit_bar_number']) for o in observations],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    serve_review(parser.parse_args().output,review)

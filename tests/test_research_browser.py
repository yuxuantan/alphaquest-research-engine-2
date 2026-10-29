"""Actual upload -> declared IS -> selected OOS -> durable native prop reports."""

from test_backtests_browser import set_parameter
from hashlib import sha256
import json
import re
from uuid import uuid4

from test_backtests_browser import browser,page,portal,playwright
from test_research_workflow import history
from test_automatic_prop import expected_cash


def upload(page,portal,days=2,point='10'):
    response=page.request.post(portal['url']+'/api/datasets',params=dict(filename='SYNTHETIC-holdout.csv',name='SYNTHETIC IS/OOS cash arithmetic',symbol='SYNTHETIC',source_timezone='UTC',tick_size='.25',point_value=point),data=history(days))
    assert response.status==201,response.text()
    return response.json()


def configure(page,portal,dataset):
    page.goto(portal['url']+'/#backtests/new')
    page.locator('#backtest-dataset').select_option(dataset['id'])
    for name in ('green_bar_count','hold_minutes','contracts'):set_parameter(page, name, '1')
    page.locator('#backtest-slippage-ticks').fill('0');page.locator('#backtest-commission').fill('0')


def test_editable_dates_and_unlimited_manual_oos_in_actual_portal(page,portal,tmp_path):
    dataset=upload(page,portal,days=4);configure(page,portal,dataset)
    playwright.expect(page.locator('#start-backtest')).to_be_disabled()
    page.locator('#sample-split-mode').select_option('percentage')
    page.locator('#sample-is-percent').fill('70')
    playwright.expect(page.locator('#sample-oos-percent')).to_have_value('30')
    page.locator('#sample-split-mode').select_option('dates')
    for id,value in [('backtest-from-date','2026-01-05'),('backtest-to-date','2026-01-05'),('sample-oos-start','2026-01-05'),('sample-oos-end','2026-01-06')]:page.locator('#'+id).fill(value)
    page.locator('#sample-review').click()
    playwright.expect(page.locator('#sample-status')).to_contain_text('IS end < OOS start')
    playwright.expect(page.locator('#start-backtest')).to_be_disabled()
    page.locator('#sample-oos-start').fill('2026-01-06');page.locator('#sample-review').click()
    playwright.expect(page.locator('#sample-status')).to_contain_text('IS 2026-01-05 → 2026-01-05 (3 bars)')
    playwright.expect(page.locator('#start-backtest')).to_be_enabled()
    page.screenshot(path=str(tmp_path/'declared-date-split.png'),full_page=True)
    page.locator('#start-backtest').click()
    playwright.expect(page.locator('#report-research-title')).to_have_text('In-sample backtest')
    playwright.expect(page.locator('#report-oos-budget')).to_contain_text('No attempt limit')
    is_id=page.url.rsplit('/',1)[1]
    playwright.expect(page.locator('#report-run-oos')).to_be_enabled()
    page.once('dialog',lambda d:d.dismiss());page.locator('#report-run-oos').click()
    assert page.request.get(portal['url']+'/api/backtests/'+is_id+'/oos').json()['used']==0
    page.once('dialog',lambda d:d.accept());page.locator('#report-run-oos').click()
    playwright.expect(page.locator('#report-research-title')).to_have_text('Out-of-sample backtest',timeout=30000)
    playwright.expect(page.locator('#report-oos-budget')).to_contain_text('No attempt limit')
    oos_id=page.url.rsplit('/',1)[1]
    playwright.expect(page.locator('#report-run-oos')).to_be_hidden()
    for _ in range(3):
        response=page.request.post(portal['url']+'/api/backtests/'+is_id+'/oos',data=dict(request_id=str(uuid4())))
        assert response.status==201,response.text()
    page.goto(portal['url']+'/#backtests/report/'+is_id)
    playwright.expect(page.locator('#report-oos-budget')).to_contain_text('No attempt limit')
    playwright.expect(page.locator('#report-run-oos')).to_be_enabled()
    assert page.request.get(portal['url']+'/api/backtests/'+is_id+'/oos').json()['used']==4
    page.screenshot(path=str(tmp_path/'four-oos-runs.png'),full_page=True)
    page.goto(portal['url']+'/#backtests/new')
    playwright.expect(page.locator('#sample-split-mode')).to_be_enabled()
    playwright.expect(page.locator('#sample-status')).to_contain_text('editable')
    playwright.expect(page.locator('#backtest-to-date')).to_be_enabled()
    page.locator('#backtest-to-date').fill('2026-01-06')
    page.locator('#sample-oos-start').fill('2026-01-07')
    page.locator('#sample-oos-end').fill('2026-01-08')
    playwright.expect(page.locator('#start-backtest')).to_be_disabled()
    page.locator('#sample-review').click()
    playwright.expect(page.locator('#start-backtest')).to_be_enabled()
    page.screenshot(path=str(tmp_path/'edited-split.png'),full_page=True)
    page.locator('#start-backtest').click()
    playwright.expect(page.locator('#report-research-title')).to_have_text('In-sample backtest')
    playwright.expect(page.locator('#report-net')).to_have_text('60.00')
    assert page.request.get(portal['url']+'/api/backtests/'+is_id+'/oos').json()['used']==4,'Editing and IS execution must not run OOS'
    page.set_viewport_size(dict(width=390,height=844))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    (tmp_path/'manual-oos-verification.json').write_text(json.dumps(dict(synthetic=True,is_id=is_id,first_oos_id=oos_id,history=page.request.get(portal['url']+'/api/backtests/'+is_id+'/oos').json(),fourth_succeeded=True,explicit_cancel_did_not_consume=True,edited_is_net='60.00',is_did_not_run_oos=True),indent=2))


def test_percentage_is_sweep_select_oos_with_default_prop_and_reopen_downloads(page,portal,tmp_path):
    # 120 weekdays: first 60 IS, next 60 OOS. Each period independently earns
    # 60 * (103-100) * 1000 = 180,000; the known cash fixture gives 352,880 net.
    raw=history(120);source=tmp_path/'SYNTHETIC-120-weekday-holdout.csv';source.write_bytes(raw)
    page.goto(portal['url'])
    page.locator('#csv-file').set_input_files(source);page.locator('#dataset-name').fill('SYNTHETIC 120 weekday holdout')
    page.locator('#source-timezone').select_option('UTC');page.locator('#dataset-tick-size').fill('.25');page.locator('#dataset-point-value').fill('1000')
    page.locator('#validate-button').click();playwright.expect(page.locator('#validation-result')).to_contain_text('Validation passed')
    page.locator('#save-button').click();playwright.expect(page.locator('#validation-result')).to_contain_text('Dataset saved')
    dataset=next(d for d in page.request.get(portal['url']+'/api/datasets').json() if d['name']=='SYNTHETIC 120 weekday holdout')
    configure(page,portal,dataset)
    page.locator('#sample-split-mode').select_option('percentage');page.locator('#sample-is-percent').fill('50')
    playwright.expect(page.locator('#sample-oos-percent')).to_have_value('50')
    page.locator('#sample-review').click();playwright.expect(page.locator('#sample-status')).to_contain_text('(180 bars)')
    page.locator('#start-backtest').click()
    playwright.expect(page.locator('#report-prop-historical-net')).to_have_text('$352,880',timeout=180000)
    is_id=page.url.rsplit('/',1)[1];is_record=page.request.get(portal['url']+'/api/backtests/'+is_id).json()
    assert is_record['summary']['trades_taken']==60 and float(is_record['summary']['total_net_pnl'])==180000
    is_prop_id=is_record['run_metadata']['automatic_prop_analysis']['id']
    is_prop=page.request.get(portal['url']+'/api/prop-analyses/'+is_prop_id+'/downloads/report.json').json();expected_cash(is_prop)
    assert is_prop['source']['backtest']['run_metadata']['research']['phase']=='is'
    assert is_prop['source']['backtest']['run_metadata']['selection']['row_count']==180
    page.screenshot(path=str(tmp_path/'is-cash-summary.png'),full_page=True)
    # Enter the normal configuration -> source checking -> run -> durable report
    # workflow. Identical native analysis reopens the verified saved calculation.
    page.locator('#report-prop-setup').click();playwright.expect(page.locator('#prop-activation')).to_have_value('129')
    page.locator('#prop-check').click();playwright.expect(page.locator('#prop-run')).to_be_enabled()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('180000')
    page.screenshot(path=str(tmp_path/'is-native-source-check.png'),full_page=True)
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
    assert page.url.endswith('/'+is_prop_id)
    page.goto(portal['url']+'/#backtests/new')
    for label,value in [('Green bar count start','1'),('Green bar count end','2'),('Hold minutes start','1'),('Hold minutes end','1')]:page.get_by_label(label,exact=True).fill(value)
    page.get_by_label('Green bar count step',exact=True).fill('1')
    page.locator('#optimization-workers').select_option('1')
    page.locator('#start-backtest').click()
    playwright.expect(page.locator('#optimization-status')).to_contain_text('COMPLETE',timeout=180000)
    playwright.expect(page.locator('#optimization-context')).to_contain_text('IS only')
    batch=page.url.rsplit('/',1)[1]
    rows=page.request.get(portal['url']+'/api/backtests/batches/'+batch+'/results').json()['items']
    assert len(rows)==2 and rows[0]['metrics']['historical_net']==352880 and rows[1]['metrics']['historical_net'] is None
    assert page.request.get(portal['url']+'/api/backtests/'+is_id+'/oos').json()['used']==0
    page.goto(portal['url']+'/#backtests/report/'+rows[0]['run_id'])
    playwright.expect(page.locator('#report-run-oos')).to_be_enabled()
    page.once('dialog',lambda d:d.accept());page.locator('#report-run-oos').click()
    playwright.expect(page.locator('#report-research-title')).to_have_text('Out-of-sample backtest',timeout=180000)
    playwright.expect(page.locator('#report-prop-historical-net')).to_have_text('$352,880',timeout=180000)
    oos_id=page.url.rsplit('/',1)[1];oos_record=page.request.get(portal['url']+'/api/backtests/'+oos_id).json()
    assert oos_record['summary']['trades_taken']==60 and float(oos_record['summary']['total_net_pnl'])==180000
    assert oos_record['run_metadata']['research']['parent_run_id']==rows[0]['run_id']
    assert oos_record['run_metadata']['selection']['from_date']>'2026-03-27'
    oos_prop_id=oos_record['run_metadata']['automatic_prop_analysis']['id']
    response=page.request.get(portal['url']+'/api/prop-analyses/'+oos_prop_id+'/downloads/report.json');oos_bytes=response.body()
    oos_prop=json.loads(oos_bytes);expected_cash(oos_prop)
    assert oos_prop['runtime']['calculation_reused_from'] is None
    assert oos_prop['source']['backtest']['run_metadata']['research']['phase']=='oos'
    assert oos_prop['source']['backtest']['run_metadata']['selection']['row_count']==180
    # A manually executed saved OOS source can use editable prop settings.
    changed=dict(source_backtest_id=oos_id,trade_file='',settings=dict(ACTIVATION_FEE='0'))
    assert page.request.post(portal['url']+'/api/prop-analyses/check',data=changed).status==200
    assert len(page.request.get(portal['url']+'/api/prop-analyses/sources/'+oos_id+'?discover_exports=false').json()['analyses'])==1
    page.screenshot(path=str(tmp_path/'oos-cash-summary.png'),full_page=True)
    page.locator('#report-prop-setup').click();page.locator('#prop-check').click();playwright.expect(page.locator('#prop-run')).to_be_enabled()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('180000')
    page.screenshot(path=str(tmp_path/'oos-native-source-check.png'),full_page=True)
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
    assert page.url.endswith('/'+oos_prop_id)
    with page.expect_download() as download:page.get_by_role('link',name='Report data (JSON)',exact=True).click()
    download.value.save_as(tmp_path/'oos-prop-report.json');assert (tmp_path/'oos-prop-report.json').read_bytes()==oos_bytes
    page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert page.request.get(portal['url']+'/api/prop-analyses/'+oos_prop_id+'/downloads/report.json').body()==oos_bytes
    (tmp_path/'is-prop-report.json').write_text(json.dumps(is_prop,indent=2))
    (tmp_path/'is-backtest.json').write_text(json.dumps(is_record,indent=2));(tmp_path/'oos-backtest.json').write_text(json.dumps(oos_record,indent=2))
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,dataset=dataset,is_id=is_id,batch_id=batch,batch_rows=rows,oos_id=oos_id,expected_net_pnl_each=180000,expected_trades_each=60,expected_historical_net_each=352880,expected_payouts_each=360000,expected_fees_each=7120,oos_report_sha256=sha256(oos_bytes).hexdigest(),budget=page.request.get(portal['url']+'/api/backtests/'+is_id+'/oos').json(),configure_check_run_reopen_download=True),indent=2))

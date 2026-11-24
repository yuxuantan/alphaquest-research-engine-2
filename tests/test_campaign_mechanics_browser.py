"""Normal upload/setup → native mechanics run → saved human review → next phase."""
import json
import re
from hashlib import sha256

import httpx
from research_fixtures import declare_in_form
from test_backtests_browser import browser, page, portal, playwright
from test_campaign_mechanics import mechanics_csv, create_workflow, run_validation


def test_upload_default_run_review_resume_and_phase_lock(page, portal, tmp_path):
    page.goto(portal['url']+'/#campaigns/consecutive_green_hold')
    page.get_by_role('link',name='New backtest →',exact=True).click()
    playwright.expect(page.locator('#optimization-settings')).to_be_hidden()
    page.get_by_role('link',name='Upload a new dataset →',exact=True).click()
    page.locator('#csv-file').set_input_files({'name':'SYNTHETIC-mechanics.csv','mimeType':'text/csv','buffer':mechanics_csv()})
    page.locator('#dataset-name').fill('SYNTHETIC mechanics product review')
    page.locator('#symbol').fill('SYNTHETIC')
    page.locator('#dataset-tick-size').fill('.25')
    page.locator('#dataset-point-value').fill('10')
    page.locator('#validate-button').click()
    playwright.expect(page.locator('#validation-result')).to_contain_text('Validation passed')
    page.locator('#save-button').click()
    page.get_by_role('link',name='Continue to backtest →',exact=True).click()
    playwright.expect(page.locator('#backtest-strategy')).to_have_value('consecutive_green_hold')
    playwright.expect(page.locator('#backtest-dataset-info')).to_contain_text('25 bars')
    page.locator('#backtest-slippage-ticks').fill('1')
    page.locator('#backtest-commission').fill('1')
    declare_in_form(page,dict(is_start='2026-01-05',is_end='2026-01-05',oos_start='2026-01-06',oos_end='2026-01-06'))
    page.get_by_role('button',name='Open mechanic validation →',exact=True).click()
    playwright.expect(page.locator('#mechanic-run')).to_be_visible()
    assert page.request.get(portal['url']+'/api/backtests').json()['total']==0
    assert page.locator('#mechanic-content button').count()==1
    assert page.locator('#mechanic-metrics').count()==0
    playwright.expect(page.locator('#mechanic-phases button:disabled')).to_have_count(3)
    playwright.expect(page.locator('#mechanic-phases .mechanic-step-index')).to_have_text(['01','02','03','04'])
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(tmp_path/'01-ready.png'),full_page=True)
    page.locator('#mechanic-run').click()
    playwright.expect(page.locator('#mechanic-trades tbody tr')).to_have_count(5,timeout=30000)
    workflow_url=page.url
    id=workflow_url.split('/')[-2];prefix=portal['url']+'/api/campaign-workflows/'+id
    result=page.request.get(prefix).json()
    assert result['declaration']['default_parameters']==dict(green_bar_count=3,hold_minutes=20,contracts=1)
    assert float(result['report']['summary']['total_net_pnl'])==78
    playwright.expect(page.locator('#mechanic-metrics tbody tr')).to_have_count(10)
    for key in ['initial_capital','final_equity','ending_position_contracts','max_drawdown_pct','max_drawdown_duration_seconds']:
        playwright.expect(page.locator(f'#mechanic-metrics tr[data-metric="{key}"]')).to_have_count(0)
        assert key in result['report']['summary']
    assert [s['trade']['trade_number'] for s in result['trade_samples']]==[1,6,2,3,4]
    risk=page.locator('#mechanic-content .research-risk-diagnostics')
    risk.locator('summary').click()
    playwright.expect(risk).to_contain_text('Research baseline: 1 fixed contract(s)')
    playwright.expect(risk).to_contain_text('Full-history R summaries are unavailable')
    playwright.expect(risk.locator('tbody tr')).to_have_count(5)
    assert risk.locator('input[type=checkbox]').count()==0
    risk.locator('summary').click()
    playwright.expect(page.locator('#mechanic-confirm')).to_be_disabled()
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(tmp_path/'02-results-unreviewed.png'),full_page=True)
    first=page.locator('[data-review-group="metric_checks"]').first
    first.check()
    playwright.expect(page.locator('#mechanic-status')).to_have_text('Review checks saved.')
    page.reload()
    playwright.expect(page.locator('[data-review-group="metric_checks"]').first).to_be_checked()
    for locator in page.locator('[data-review-group]').all()[:-1]:
        if not locator.is_checked():
            locator.check()
            playwright.expect(page.locator('#mechanic-status')).to_have_text('Review checks saved.')
    playwright.expect(page.locator('#mechanic-confirm')).to_be_disabled()
    saved=page.request.get(prefix).json()
    rejection=page.request.post(prefix+'/confirm',data={'revision':saved['review']['revision']})
    assert rejection.status==409
    page.locator('[data-review-group]').last.check()
    playwright.expect(page.locator('#mechanic-confirm')).to_be_enabled()
    page.locator('#mechanic-confirm').click()
    playwright.expect(page.locator('#mechanic-status')).to_contain_text('Mechanic validation passed')
    playwright.expect(page.locator('#mechanic-phases [data-phase="is_broad"]')).to_be_enabled()
    playwright.expect(page.locator('#mechanic-phases [data-phase="is_narrow"]')).to_be_disabled()
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(tmp_path/'03-confirmed.png'),full_page=True)
    with page.expect_download() as download:
        page.get_by_role('link',name='Saved review JSON ↓',exact=True).click()
    download.value.save_as(tmp_path/'mechanic-review.json')
    result=json.loads((tmp_path/'mechanic-review.json').read_bytes())
    assert result['status']=='passed' and result['review']['confirmed_at_utc']
    page.locator('#mechanic-phases [data-phase="is_broad"]').click()
    playwright.expect(page.locator('#broad-config')).to_be_visible()
    page.locator('#mechanic-phases').screenshot(path=str(tmp_path/'phase-sequence.png'))
    page.goto(workflow_url.rsplit('/',1)[0]+'/oos')
    playwright.expect(page.locator('#mechanic-status')).to_contain_text('Previous phases must all pass')
    page.goto(portal['url']+'/#campaigns/consecutive_green_hold')
    playwright.expect(page.get_by_role('link',name='Inspect validation results →',exact=True)).to_have_count(0)
    playwright.expect(page.get_by_role('link',name='SYNTHETIC mechanics product review',exact=True)).to_be_visible()
    page.screenshot(path=str(tmp_path/'campaign-navigation.png'),full_page=True)
    page.get_by_role('link',name='SYNTHETIC mechanics product review',exact=True).click()
    playwright.expect(page.locator('#broad-config')).to_be_visible()
    page.locator('#mechanic-phases [data-phase="mechanic_validation"]').click()
    playwright.expect(page.locator('#mechanic-confirm')).to_have_text('Mechanics confirmed')
    page.reload()
    playwright.expect(page.locator('#mechanic-confirm')).to_have_text('Mechanics confirmed')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(tmp_path/'04-mobile.png'),full_page=True)
    page.get_by_role('link',name='Open backtest report',exact=True).click()
    playwright.expect(page.locator('#report-summary')).to_contain_text('78.00')
    playwright.expect(page.locator('#report-run-oos')).to_be_hidden()
    assert page.request.post(portal['url']+'/api/backtests/'+result['run_id']+'/oos',data={'request_id':'00000000-0000-0000-0000-000000000001'}).status==409
    assert page.request.get(portal['url']+'/api/backtests').json()['total']==1
    for name,path in [('trades.csv',f'/api/backtests/{result["run_id"]}/exports/trades'),('report.json',f'/api/backtests/{result["run_id"]}'),('SYNTHETIC-mechanics.csv',f'/api/datasets/{result["declaration"]["dataset"]["id"]}/csv')]:
        response=page.request.get(portal['url']+path);assert response.ok
        (tmp_path/name).write_bytes(response.body())
    (tmp_path/'journey.json').write_text(json.dumps({'workflow_id':id,'report_id':result['run_id'],'workflow_hash_route':'/#campaigns/workflows/'+id+'/mechanic_validation','expected_trade_net':[3,43,-37,13,23,33],'expected_net':78,'expected_sample_trade_numbers':[1,6,2,3,4],'mc_parity':'Synthetic UI attestation exercise; no automated or measured MultiCharts comparison','temporary_server':'Stopped by fixture teardown','files':{p.name:sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir() if p.is_file()}},indent=2))


def test_existing_campaign_dataset_opens_setup_or_saved_validation(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=30) as client:
        dataset,body,workflow=create_workflow(client)
        result=run_validation(client,workflow)
    page.goto(portal['url']+'/#campaigns/consecutive_green_hold')
    page.get_by_role('link',name='SYNTHETIC mechanics',exact=True).click()
    playwright.expect(page.locator('#mechanic-trades tbody tr')).to_have_count(5)
    playwright.expect(page.locator('#mechanic-confirm')).to_be_disabled()
    # A non-workflow historical source remains inspectable and does not inherit a pass.
    from test_backtest_api import body as request_body
    payload=request_body(portal['saved']['arithmetic_5m']['id'])
    with httpx.Client(base_url=portal['url'],timeout=30) as client:
        from research_fixtures import declaration
        payload['sample_split']=declaration(payload['dataset_id'])
        response=client.post('/api/backtests',json=payload);assert response.status_code==201,response.text
    page.goto(portal['url']+'/#campaigns/consecutive_green_hold')
    page.get_by_role('link',name='arithmetic_5m',exact=True).click()
    playwright.expect(page.locator('#backtest-dataset')).to_have_value(portal['saved']['arithmetic_5m']['id'])
    playwright.expect(page.locator('#start-backtest')).to_have_text('Open mechanic validation →')
    page.locator('#backtest-slippage-ticks').fill('1')
    page.locator('#backtest-commission').fill('1')
    declare_in_form(page,declaration(portal['saved']['arithmetic_5m']['id']))
    page.locator('#start-backtest').click()
    page.locator('#mechanic-run').click()
    playwright.expect(page.locator('#mechanic-trades tbody tr')).to_have_count(1,timeout=30000)
    playwright.expect(page.locator('#mechanic-trades')).to_contain_text('First trade · Last trade · Biggest win · Shortest duration')
    playwright.expect(page.locator('#mechanic-trades')).to_contain_text('No qualifying trade for: Biggest loss')
    id=page.url.split('/')[-2]
    result=page.request.get(portal['url']+'/api/campaign-workflows/'+id).json()
    assert float(result['report']['summary']['total_net_pnl'])==13
    assert len(result['trade_samples'])==1
    (tmp_path/'overlap-review.json').write_text(json.dumps(result,indent=2))
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(tmp_path/'05-overlap.png'),full_page=True)


def test_orb_vwap_external_calendar_is_optional_in_backtest_setup(page, portal):
    from research_fixtures import ResearchHTTPClient, declaration
    from test_backtests_browser import set_parameter
    from test_inferred_session_close import csv_bytes, session_rows

    with ResearchHTTPClient(base_url=portal['url']) as client:
        upload = client.post('/api/datasets', params=dict(
            filename='SYNTHETIC-fixed-weekday.csv', name='SYNTHETIC fixed weekday',
            source_timezone='UTC', tick_size='.25', point_value='20'),
            content=csv_bytes(session_rows(close=(16, 0))))
        assert upload.status_code == 201, upload.text
    dataset_id = upload.json()['id']
    page.goto(portal['url'] + '/#backtests')
    page.locator('#backtest-dataset').select_option(dataset_id)
    page.locator('#backtest-strategy').select_option('vwap_pullback_risk_sizing')
    declare_in_form(page, declaration(dataset_id))
    playwright.expect(page.locator('#backtest-session-calendar')).to_contain_text('No reviewed session calendar')
    playwright.expect(page.locator('#start-backtest')).to_be_disabled()
    set_parameter(page, 'use_external_calendar', False)
    playwright.expect(page.locator('#backtest-session-calendar')).to_contain_text('16:00 Chicago')
    playwright.expect(page.locator('#start-backtest')).to_be_enabled()
    set_parameter(page, 'stop_swing_len', 1)
    set_parameter(page, 'target_swing_len', 1)
    set_parameter(page, 'use_adx_elev', False)
    set_parameter(page, 'use_adx_decay', False)
    page.locator('#backtest-slippage-ticks').fill('1')
    page.locator('#backtest-commission').fill('1')
    with page.expect_response(lambda r: '/api/backtests?' in r.url and r.request.method == 'POST') as completed:
        page.locator('#start-backtest').click()
    report = completed.value.json()
    assert completed.value.status == 201, report
    assert report['run_metadata']['strategy']['parameters']['use_eod_flat'] is True
    assert report['summary']['total_net_pnl'] == '88.00'
    page.reload()
    playwright.expect(page.locator('[data-setting=session_flattening]')).to_contain_text('Fixed weekday session exits')


def test_overnight_bias_orb_default_mechanics_and_downloads(page, portal, tmp_path):
    from test_overnight_bias_orb import product_fixture
    raw, start, signal, oos = product_fixture()
    url = portal['url']
    source = page.request.post(url + '/api/datasets', params=dict(filename='synthetic-overnight-orb.csv',
        name='SYNTHETIC Overnight Bias ORB mechanics', symbol='NQ', source_timezone='America/New_York',
        tick_size='.25', point_value='20'), data=raw)
    assert source.status == 201, source.text()
    page.goto(url + '/#campaigns/overnight_bias_orb')
    playwright.expect(page.locator('#workflow-campaign-detail h2')).to_have_text('Overnight Bias ORB')
    page.get_by_role('link', name='New backtest →', exact=True).click()
    playwright.expect(page.locator('#backtest-strategy')).to_have_value('overnight_bias_orb')
    page.locator('#backtest-dataset').select_option(source.json()['id'])
    page.locator('#backtest-slippage-ticks').fill('0')
    page.locator('#backtest-commission').fill('0')
    page.locator('#backtest-initial-capital').fill('10000')
    declare_in_form(page, dict(is_start=str(start), is_end=str(signal), oos_start=str(oos), oos_end=str(oos)))
    page.get_by_role('button', name='Open mechanic validation →', exact=True).click()
    page.locator('#mechanic-run').click()
    playwright.expect(page.locator('#mechanic-trades tbody tr')).to_have_count(1, timeout=60000)
    playwright.expect(page.locator('#mechanic-trades')).to_contain_text('320')
    playwright.expect(page.locator('#mechanic-confirm')).to_be_disabled()
    for label, path in [('Trades CSV ↓', 'trades.csv'), ('Saved review JSON ↓', 'mechanic-review.json')]:
        with page.expect_download() as download:
            page.get_by_role('link', name=label, exact=True).click()
        download.value.save_as(tmp_path / path)
    page.get_by_role('link', name='Open backtest report', exact=True).click()
    playwright.expect(page.locator('[data-setting="session_flattening"]')).to_contain_text('15:30 ET')


def test_noise_campaign_explanation_mechanics_and_downloads(page, portal, tmp_path):
    import csv
    from decimal import Decimal
    from test_noise import product_fixture

    raw, start, signal, oos = product_fixture()
    url = portal['url']
    page.goto(url + '/#campaigns/noise')
    detail = page.locator('#workflow-campaign-detail')
    overview = detail.locator('.campaign-overview')
    datasets = detail.locator('.workflow-datasets')
    playwright.expect(detail.get_by_role('heading', name='Noise', exact=True)).to_be_visible()
    playwright.expect(overview).to_contain_text('prior 20 observations')
    playwright.expect(datasets).to_contain_text('No saved datasets for this campaign')
    assert overview.bounding_box()['y'] < datasets.bounding_box()['y']
    page.screenshot(path=str(tmp_path / 'noise-campaign.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    playwright.expect(overview).to_contain_text('14:30 CT')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width': 1440, 'height': 1100})

    name = 'SYNTHETIC Noise mechanics'
    source = page.request.post(url + '/api/datasets', params=dict(filename='synthetic-noise.csv',
        name=name, symbol='NQ', source_timezone='America/Chicago', tick_size='.25', point_value='20'), data=raw)
    assert source.status == 201, source.text()
    page.get_by_role('link', name='New backtest →', exact=True).click()
    playwright.expect(page.locator('#backtest-strategy')).to_have_value('noise')
    page.locator('#backtest-dataset').select_option(source.json()['id'])
    page.locator('#backtest-slippage-ticks').fill('0')
    page.locator('#backtest-commission').fill('0')
    page.locator('#backtest-initial-capital').fill('10000')
    declare_in_form(page, dict(is_start=str(start), is_end=str(signal), oos_start=str(oos), oos_end=str(oos)))
    page.get_by_role('button', name='Open mechanic validation →', exact=True).click()
    page.locator('#mechanic-run').click()
    playwright.expect(page.locator('#mechanic-trades tbody tr')).to_have_count(1, timeout=60000)
    playwright.expect(page.locator('#mechanic-confirm')).to_be_disabled()
    page.screenshot(path=str(tmp_path / 'noise-mechanics.png'), full_page=True)
    for label, path in [('Trades CSV ↓', 'trades.csv'), ('Saved review JSON ↓', 'mechanic-review.json')]:
        with page.expect_download() as download:
            page.get_by_role('link', name=label, exact=True).click()
        download.value.save_as(tmp_path / path)

    with (tmp_path / 'trades.csv').open() as download:
        trade, = csv.DictReader(download)
    assert trade['entry_reason'] == 'NoiseLong'
    assert trade['exit_reason'] == 'take_profit'
    assert Decimal(trade['entry_fill_price']) == 20015
    assert Decimal(trade['exit_fill_price']) == 20040
    assert Decimal(trade['net_pnl']) == 1000
    (tmp_path / 'synthetic-noise.csv').write_bytes(raw)
    page.get_by_role('link', name='Open backtest report', exact=True).click()
    playwright.expect(page.locator('[data-setting="session_flattening"]')).to_contain_text('exactly 14:30 CT')
    report_id = page.url.rsplit('/', 1)[-1]
    saved = page.request.get(url + '/api/backtests/' + report_id)
    assert saved.ok, saved.text()
    (tmp_path / 'report.json').write_bytes(saved.body())
    page.reload()
    playwright.expect(page.locator('[data-setting="session_flattening"]')).to_contain_text('exactly 14:30 CT')


def test_relative_strength_explanation_paired_source_and_default_mechanics(page, portal, tmp_path):
    import csv
    from decimal import Decimal
    from test_relative_strength import product_fixture

    raw, start, signal, oos = product_fixture()
    url = portal['url']
    page.goto(url + '/#campaigns/relative_strength')
    detail = page.locator('#workflow-campaign-detail')
    overview = detail.locator('.campaign-overview')
    datasets = detail.locator('.workflow-datasets')
    playwright.expect(detail.get_by_role('heading', name='Relative Strength', exact=True)).to_be_visible()
    playwright.expect(overview).to_contain_text('decision minute is included')
    playwright.expect(overview).to_contain_text('following bar')
    playwright.expect(datasets).to_contain_text('No saved datasets for this campaign')
    assert overview.bounding_box()['y'] < datasets.bounding_box()['y']
    page.screenshot(path=str(tmp_path / 'relative-strength-campaign.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    playwright.expect(overview).to_contain_text('15:00 CT')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width': 1440, 'height': 1100})

    settings = dict(symbol='NQ', source_timezone='America/Chicago', tick_size='.25', point_value='20')
    primary = page.request.post(url + '/api/datasets', params=dict(
        filename='synthetic-nq.csv', name='SYNTHETIC unpaired NQ', **settings),
        data=b'\n'.join(line.rsplit(b',', 1)[0] for line in raw.splitlines()) + b'\n')
    assert primary.status == 201, primary.text()
    source = page.request.post(url + '/api/datasets', params=dict(
        filename='synthetic-relative-strength.csv', name='SYNTHETIC Relative Strength', **settings), data=raw)
    assert source.status == 201, source.text()
    page.get_by_role('link', name='New backtest →', exact=True).click()
    playwright.expect(page.locator('#backtest-strategy')).to_have_value('relative_strength')
    playwright.expect(page.locator(f'#backtest-dataset option[value="{primary.json()["id"]}"]')).to_be_disabled()
    page.locator('#backtest-dataset').select_option(source.json()['id'])
    page.locator('#backtest-slippage-ticks').fill('0')
    page.locator('#backtest-commission').fill('0')
    page.locator('#backtest-initial-capital').fill('10000')
    declare_in_form(page, dict(is_start=start, is_end=signal, oos_start=oos, oos_end=oos))
    page.get_by_role('button', name='Open mechanic validation →', exact=True).click()
    page.locator('#mechanic-run').click()
    playwright.expect(page.locator('#mechanic-trades tbody tr')).to_have_count(1, timeout=60000)
    playwright.expect(page.locator('#mechanic-confirm')).to_be_disabled()
    for label, path in [('Trades CSV ↓', 'trades.csv'), ('Saved review JSON ↓', 'mechanic-review.json')]:
        with page.expect_download() as download:
            page.get_by_role('link', name=label, exact=True).click()
        download.value.save_as(tmp_path / path)

    with (tmp_path / 'trades.csv').open() as download:
        trade, = csv.DictReader(download)
    assert trade['entry_reason'] == 'RS.L'
    assert trade['exit_reason'] == 'take_profit'
    assert Decimal(trade['entry_fill_price']) == 20100
    assert Decimal(trade['exit_fill_price']) == 20120
    assert Decimal(trade['net_pnl']) == 400
    page.get_by_role('link', name='Open backtest report', exact=True).click()
    playwright.expect(page.locator('[data-setting="session_flattening"]')).to_contain_text('ES closes are part of the saved dataset hash')
    page.reload()
    playwright.expect(page.locator('[data-setting="session_flattening"]')).to_contain_text('15:00 CT')

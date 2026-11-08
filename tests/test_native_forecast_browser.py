"""Declared native forecasts beside actual history through normal product routes."""
from decimal import Decimal
from hashlib import sha256
import io
import json
import re
import zipfile

import pytest

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_native_replay_api import source
from test_native_replay_browser import configure, run


def configure_forecast(page,horizon=9):
    page.locator('#native-forecast-enabled').check()
    page.locator('#native-forecast-paths').fill('4')
    page.locator('#native-forecast-seed').fill('1729')
    page.locator('#native-forecast-block').select_option('1')
    page.locator('#native-forecast-horizon').fill(str(horizon))
    page.locator('#native-forecast-capture').fill('2')
    page.locator('#native-forecast-calendar-version').fill('explicit-demo-weekdays-v1')
    page.locator('.native-forecast-start').fill('2026-01-26')
    page.locator('#native-forecast-coverage-end').fill('2026-02-05')


def check_rejection(page,text):
    page.locator('#native-check').click()
    playwright.expect(page.locator('#native-status')).to_contain_text(text,timeout=60000)
    playwright.expect(page.locator('#native-run')).to_be_disabled()


@pytest.mark.parametrize('phase,horizon',[('funded',9),('evaluation',9),('evaluation',3)])
def test_native_forecast_is_separate_and_keeps_all_paths(page,portal,tmp_path,phase,horizon):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        original=source(client,days=7,payout=True)
    configure(page,portal,original,phase,kind=None,cap='3')
    configure_forecast(page,horizon)
    if phase=='funded':
        page.locator('.native-forecast-start').fill('2026-01-13')
        check_rejection(page,'follow the last admitted source IS session')
        page.locator('.native-forecast-start').fill('2026-01-26')
        page.locator('#native-forecast-start-add').click()
        page.locator('.native-forecast-start').nth(1).fill('2026-01-27')
        page.locator('#native-forecast-paths').fill('3')
        check_rejection(page,'equal number of paths per start cohort')
        page.locator('.native-forecast-start-row').nth(1).get_by_role('button',name='Remove date',exact=True).click()
        page.locator('#native-forecast-paths').fill('4')
        page.locator('#native-forecast-configure').get_by_text('Declare target calendar closures and early closes',exact=True).click()
        page.locator('#native-forecast-early-close-add').click()
        page.locator('.native-forecast-early-close').fill('2026-01-27')
        check_rejection(page,'No complete source block matches modeled target shape')
        page.locator('.native-forecast-early-close-row').get_by_role('button',name='Remove date',exact=True).click()
        page.locator('#native-forecast-capture').fill('5')
        check_rejection(page,'Retained detailed paths cannot exceed total simulations')
        page.locator('#native-forecast-capture').fill('2')
        page.locator('#native-forecast-configure').screenshot(path=str(tmp_path/'declared-native-forecast.png'))
    report=run(page,portal,tmp_path);forecast=report['native_forecast'];plan=report['source']['native_forecast_plan']
    assert forecast['mode']=='native_modeled_forecast' and forecast['observed_future_data'] is False
    assert forecast['readiness']=='MODELED_SCENARIO_ONLY'
    assert forecast['metrics']['paths']==4 and len(forecast['paths'])==4
    assert forecast['capture_path_indices']==[0,1]
    assert [c['path_index'] for c in forecast['captures']]==[0,1]
    assert all(s['start_date']=='2026-01-26' for s in forecast['schedules'])
    assert plan['retained_path_indices']==[0,1] and plan['paths_per_cohort']==4
    assert plan['work']['total_bar_work']==sum(plan['work'][k] for k in ['source_validation_bars','warmup_bars','executed_bars'])
    assert all(d['pool_count']==7 for s in forecast['schedules'] for d in s['draws'])
    assert report['calculations']['historical_paths']==1
    assert report['calculations']['native_forecast_available'] is False
    assert 'observed_future_data' not in report['calculations']
    metrics=forecast['metrics'];estimates=forecast['uncertainty']['metrics']
    if phase=='funded':
        assert forecast['status']=='finite_horizon_model_mean'
        assert metrics['mean_received_cash']==1500 and metrics['mean_pending_cash']==0
        assert metrics['mean_gross_account_deductions']==1500 and metrics['mean_provider_equity_change']==4800
        assert Decimal(report['calculations']['trading_profit'])==6300
        for path in forecast['paths']:
            assert Decimal(path['trading_profit'])==6300 and Decimal(path['equity'])==4800
            assert Decimal(path['cash_received'])==1500 and Decimal(path['pending_cash'])==0
            payout,=path['payout_events']
            assert payout['request_date']=='2026-01-30' and payout['receipt_date']=='2026-02-01'
        expected=dict(mean_received_cash=1500,mean_pending_cash=0,gross_deduction=1500,provider_equity_change=4800,
            path_trading_profit=6300,request_date='2026-01-30',receipt_date='2026-02-01')
    elif horizon==9:
        assert forecast['status']=='identified_model_mean'
        assert metrics['mean_acquisition_cost']==70 and metrics['mean_calendar_days_to_funded']==7
        assert metrics['completed_paths']==4 and metrics['censored_paths']==0
        for path in forecast['paths']:
            assert Decimal(path['paid_evaluation_fees'])==30 and Decimal(path['paid_activation_fees'])==40
            assert path['pass_date']=='2026-01-29' and path['ready_date']=='2026-02-02'
            assert path['acquisition_completed'] is True
        expected=dict(mean_acquisition_cost=70,mean_calendar_days_to_funded=7,completed_paths=4,
            pass_date='2026-01-29',ready_date='2026-02-02')
    else:
        assert forecast['status']=='unresolved_censoring'
        assert metrics['mean_acquisition_cost'] is None and metrics['mean_calendar_days_to_funded'] is None
        assert metrics['restricted_mean_paid_fees']==30 and metrics['restricted_mean_observed_calendar_days']==3
        assert metrics['completed_paths']==0 and metrics['censored_paths']==4
        assert all(not p['acquisition_completed'] and p['censored'] and Decimal(p['paid_fees'])==30 for p in forecast['paths'])
        expected=dict(mean_acquisition_cost=None,mean_calendar_days_to_funded=None,restricted_mean_paid_fees=30,
            restricted_mean_observed_calendar_days=3,completed_paths=0,censored_paths=4)
    assert all(e['mc_standard_error']==(None if e['mean'] is None else 0) for e in estimates.values())
    assert all(e['cohort_counts']==[4] for e in estimates.values())
    preserve_forecast(page,portal,report,original,tmp_path,expected)


def preserve_forecast(page,portal,report,original,tmp_path,expected):
    forecast=report['native_forecast'];phase=forecast['phase'];horizon=forecast['settings']['horizon_calendar_days']
    playwright.expect(page.locator('#native-forecast-result')).to_contain_text(forecast['status'])
    playwright.expect(page.locator('#native-forecast-result')).to_contain_text('including zero cash, failure and censoring')
    playwright.expect(page.locator('#native-forecast-result')).to_contain_text('not evidence of future precision or provider parity')
    if phase=='evaluation' and horizon==3:
        playwright.expect(page.locator('#native-forecast-metrics')).to_contain_text('Unavailable')
        playwright.expect(page.locator('#native-forecast-result')).to_contain_text('Successful-only averages')
    page.locator('#native-forecast-paths-detail > summary').click()
    playwright.expect(page.locator('#native-forecast-paths tbody tr')).to_have_count(4)
    page.locator('#native-forecast-captures-detail > summary').click()
    page.locator('#native-forecast-inspect').select_option('1')
    playwright.expect(page.locator('#native-forecast-clock-mapping')).to_contain_text('2026-01-26')
    playwright.expect(page.locator('#native-forecast-decisions')).to_contain_text('118')
    page.locator('#native-forecast-result').screenshot(path=str(tmp_path/'native-forecast-result.png'))
    page.locator('#native-forecast-captures-detail').screenshot(path=str(tmp_path/'retained-native-path.png'))
    id=report['id'];downloads={}
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        urls={'report.json':f'/api/prop-analyses/{id}/downloads/report.json',
            'analysis.zip':f'/api/prop-analyses/{id}/downloads/analysis.zip',
            'original-source-report.json':f"/api/backtests/{original['id']}",
            'SYNTHETIC-MNQ-observed-bars.csv':f"/api/datasets/{original['run_metadata']['dataset']['id']}/csv"}
        urls.update({name:f'/api/prop-analyses/{id}/files/{name}' for name in report['files']})
        for name,url in urls.items():
            response=client.get(url);assert response.status_code==200,(name,response.text)
            (tmp_path/name).write_bytes(response.content);downloads[name]=sha256(response.content).hexdigest()
        assert downloads['SYNTHETIC-MNQ-observed-bars.csv']==original['run_metadata']['dataset']['sha256']
        assert client.get('/api/backtests/'+original['id']).json()==original
        declaration=json.dumps(original['run_metadata']['research'],indent=2).encode()
        (tmp_path/'source-research-declaration.json').write_bytes(declaration)
        downloads['source-research-declaration.json']=sha256(declaration).hexdigest()
        with zipfile.ZipFile(io.BytesIO((tmp_path/'analysis.zip').read_bytes())) as archive:
            assert archive.read('native_forecast.json')==(tmp_path/'native_forecast.json').read_bytes()
            assert archive.read('trades.csv')==(tmp_path/'trades.csv').read_bytes()
    page.locator('#native-result').get_by_role('link',name='Open actual controlled backtest',exact=True).click()
    playwright.expect(page.locator('#report-prop-status')).to_contain_text('A separate native Monte Carlo forecast')
    page.goto(portal['url']+'/#backtests/prop/job/'+id)
    playwright.expect(page.locator('#native-forecast-result')).to_be_visible()
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#native-forecast-result')).to_be_visible();assert not posts
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#native-forecast-result h2').scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path/'narrow-native-forecast.png'))
    page.locator('#native-forecast-metrics').scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path/'narrow-forecast-metrics.png'))
    (tmp_path/'browser-evidence.json').write_text(json.dumps(dict(source_id=original['id'],analysis_id=id,
        native_backtest_id=report['native_backtest_id'],source_dataset_id=original['run_metadata']['dataset']['id'],
        source_dataset_sha256=original['run_metadata']['dataset']['sha256'],source_research_plan=original['run_metadata']['research']['plan'],
        request=report['request'],expected=expected,downloads=downloads,reopen_posts=posts,
        historical_trading_profit=report['calculations']['trading_profit'],engine_identity=report['engine_identity'],
        library=str(tmp_path),source_fixture_note='Exact downloaded source includes one synthetic reserved OOS row; forecasts use only admitted IS blocks.',
        server='Owned temporary uvicorn server stopped by portal fixture.'),indent=2))


def test_native_forecast_dynamic_quantity_continues_across_sampled_blocks(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client: original=source(client)
    configure(page,portal,original)
    configure_forecast(page,horizon=3)
    report=run(page,portal,tmp_path);f=report['native_forecast']
    # Independent source-unit arithmetic: loss -10/risk 10; win +20/risk 10;
    # win +20/risk 20. Provider capital is 50,000, risk 0.2%, floor quantity.
    # Seed 1729, Funded addressed draws, complete three-member source pool.
    expected_blocks=[[1,2,0],[1,0,0],[2,2,0],[0,1,1]]
    expected_quantities=[[10,5,10],[10,10,10],[5,5,10],[10,9,10]]
    expected_nets=[[200,100,-100],[200,-100,-100],[100,100,-100],[-100,180,200]]
    assert [[d['source_block_index'] for d in s['draws']] for s in f['schedules']]==expected_blocks
    assert [Decimal(p['equity']) for p in f['paths']]==[200,0,100,280]
    assert [Decimal(p['trading_profit']) for p in f['paths']]==[200,0,100,280]
    for capture in f['captures']:
        i=capture['path_index']
        assert [d['quantity'] for d in capture['result']['sizing_decisions']]==expected_quantities[i]
        trades=[e for block in capture['captures'] for e in block['events'] if e['event_type']=='Trade']
        assert [Decimal(t['net_pnl']) for t in trades]==expected_nets[i]
    assert f['metrics']['mean_provider_equity_change']==145
    assert f['uncertainty']['metrics']['mean_provider_equity_change']['mc_standard_error']==pytest.approx(60.759087111860616)
    assert f['metrics']['mean_received_cash']==f['metrics']['mean_pending_cash']==0
    # Actual chronology remains source Jan 5/6/7, with its different final stop.
    assert [d['quantity'] for d in report['calculations']['sizing_decisions']]==[10,9,5]
    assert Decimal(report['calculations']['trading_profit'])==180
    expected=dict(source_block_indices=expected_blocks,quantities=expected_quantities,trade_nets=expected_nets,
        path_provider_equity_changes=[200,0,100,280],mean_provider_equity_change=145,
        mean_provider_equity_change_mcse=60.759087111860616,mean_received_cash=0,mean_pending_cash=0,
        historical_quantities=[10,9,5],historical_trading_profit=180)
    preserve_forecast(page,portal,report,original,tmp_path,expected)

"""Commission demonstration through backtest -> configure -> check -> report."""
import csv
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
import io
import json
import zipfile

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright
from test_backtest_api import body


def synthetic_nq():
    rows=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    day=date(2026,1,5);count=0
    while count<60:
        if day.weekday()<5:
            for minute,prices in [(0,'9999,10000,9999,10000'),(1,'10000,10150,10000,10150'),(2,'10150,10150,10150,10150')]:
                rows.append(day.strftime('%m/%d/%Y')+f',18:0{minute},{prices},100,60,40')
            count+=1
        day+=timedelta(days=1)
    return ('\n'.join(rows)+'\n').encode()


def test_actual_instrument_commission_workflow_downloads_and_reopen(page,portal,tmp_path):
    raw=synthetic_nq();(tmp_path/'SYNTHETIC-NQ-commission.csv').write_bytes(raw)
    with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:
        uploaded=client.post('/api/datasets',params=dict(filename='SYNTHETIC-NQ-commission.csv',
            name='SYNTHETIC NQ commission arithmetic - not market history',symbol='NQ',
            source_timezone='UTC',tick_size='0.25',point_value='20'),content=raw)
        assert uploaded.status_code==201,uploaded.text
        request=body(uploaded.json()['id'])
        request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
        request['execution_settings'].update(slippage_ticks=1,commission_per_contract_per_side='1.99')
        response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
        record=response.json();source_id=record['id']
        (tmp_path/'backtest-request.json').write_text(json.dumps(request,indent=2))
        source_csv=client.get(f'/api/backtests/{source_id}/exports/trades').content
        original_hash=sha256(source_csv).hexdigest()
        source_rows=list(csv.DictReader(io.StringIO(source_csv.decode())))
        assert len(source_rows)==60
        assert all(Decimal(r['net_pnl'])==Decimal('2986.02') for r in source_rows)
        automatic_id=record['run_metadata']['automatic_prop_analysis']['id']
        default_report=client.get(f'/api/prop-analyses/{automatic_id}/downloads/report.json').json()
        assert default_report['source']['commission_simulation']['per_side']=='0.51'
        default_rows=list(csv.DictReader(io.StringIO(client.get(f'/api/prop-analyses/{automatic_id}/downloads/trades.csv').text)))
        # Independent arithmetic: (3000 - 10)/10 - 2*.51 = 297.98 per MNQ.
        assert all(Decimal(r['simulation_net_per_nq'])==Decimal('2979.80') for r in default_rows)
        (tmp_path/'default-report.json').write_text(json.dumps(default_report,indent=2))
        # Rejections use real source checking and may not publish a report.
        rejected={}
        for label,settings in [('negative',dict(COMMISSION_PER_SIDE='-1')),
                               ('identity',dict(SOURCE_INSTRUMENT='MNQ')),
                               ('missing_rate',dict(COMMISSION_BROKER='Other',COMMISSION_PER_SIDE=''))]:
            result=client.post('/api/prop-analyses/check',json=dict(source_backtest_id=source_id,trade_file='',settings=settings))
            assert result.status_code==422,result.text
            rejected[label]=result.json()
        (tmp_path/'rejections.json').write_text(json.dumps(rejected,indent=2))
    page.goto(portal['url']+'/#backtests/report/'+source_id)
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    playwright.expect(page.locator('#prop-commission-side')).to_have_value('0.51')
    playwright.expect(page.locator('#prop-commission-help')).to_contain_text('Detected source: NQ')
    page.locator('#prop-trade-file').fill('')
    page.locator('#prop-commission-broker').fill('Custom broker')
    page.locator('#prop-commission-side').fill('0.7')
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('$0.7 per side, $1.4 round turn')
    page.screenshot(path=str(tmp_path/'source-check.png'),full_page=True)
    # Editing fees invalidates a previous successful check.
    page.locator('#prop-commission-side').fill('0')
    playwright.expect(page.locator('#prop-run')).to_be_disabled()
    page.locator('#prop-commission-side').fill('0.7')
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    page.locator('#prop-run').click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=120000)
    id=page.url.rsplit('/',1)[-1]
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('Custom broker · MNQ commission $0.7')
    page.get_by_role('tab',name='Source & model',exact=True).click()
    with page.expect_download() as download:
        page.get_by_role('link',name='Download commission reconciliation (JSON)',exact=True).click()
    download.value.save_as(tmp_path/'commission_reconciliation.json')
    costs=json.loads((tmp_path/'commission_reconciliation.json').read_text())
    assert costs['per_side']=='0.7' and costs['round_turn']=='1.4'
    page.screenshot(path=str(tmp_path/'source-model.png'),full_page=True)
    with page.expect_download() as download:
        page.get_by_role('link',name='Download all results (ZIP)',exact=True).click()
    download.value.save_as(tmp_path/'analysis.zip')
    with zipfile.ZipFile(tmp_path/'analysis.zip') as archive:
        assert json.loads(archive.read('commission_reconciliation.json'))==costs
        rows=list(csv.DictReader(io.StringIO(archive.read('trades.csv').decode())))
        # Custom rate: $299 - 2*$0.70 = $297.60 per MNQ.
        assert all(Decimal(r['simulation_net_per_nq'])==Decimal('2976.00') for r in rows)
        assert all(Decimal(r['source_commission'])==Decimal('3.98') for r in rows)
        report=json.loads(archive.read('report.json'))
        assert len(report['calculations']['evaluation_sweep'])==40
        assert len(report['calculations']['funded']['sweep'])==40
        assert all(r['simulations']==3000 for r in report['calculations']['evaluation_sweep'])
        assert report['calculations']['funded']['selected']['sims']==20000
    (tmp_path/'report.json').write_text(json.dumps(report,indent=2))
    with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:
        assert sha256(client.get(f'/api/backtests/{source_id}/exports/trades').content).hexdigest()==original_hash
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert not posts
    page.locator('#prop-back').click();page.locator('#report-prop-setup').click()
    page.locator(f'#prop-saved a[href$="{id}"]').click()
    playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert not posts
    (tmp_path/'validation.json').write_text(json.dumps(dict(source_id=source_id,analysis_id=id,
        automatic_id=automatic_id,source_trades_sha256=original_hash,source_unchanged=True,
        expected_default_mnq_net='297.98',expected_custom_mnq_net='297.60',
        actual_default_net_per_nq=default_rows[0]['simulation_net_per_nq'],actual_custom_net_per_nq=rows[0]['simulation_net_per_nq'],
        reload_and_reopen_without_post=True,full_counts=True,synthetic=True),indent=2))

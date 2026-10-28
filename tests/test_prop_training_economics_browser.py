"""Actual report -> configure -> check -> run -> saved calibration/downloads."""
import csv
from datetime import date,timedelta
import io,json

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal,playwright
from test_backtest_api import body
from test_automatic_prop import save_history,expected_cash


def open_native(page,portal,record):
    page.goto(portal['url']+'/#backtests/report/'+record['id'])
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    page.locator('#prop-trade-file').fill('')
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    page.locator('#prop-run').click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=60000)


def test_actual_training_calibration_and_sweep_download_reopen(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:
        dataset=save_history(client);request=body(dataset['id'])
        request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
        request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
        response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
        record=response.json();id=record['run_metadata']['automatic_prop_analysis']['id']
        report=client.get('/api/prop-analyses/'+id+'/downloads/report.json').json();expected_cash(report)
    open_native(page,portal,record)
    assert page.url.endswith(id)
    page.get_by_role('tab',name='Sizing',exact=True).click()
    sizing=page.locator('#prop-view-sizing')
    playwright.expect(sizing).to_contain_text('training-derived acquisition economics')
    playwright.expect(sizing).to_contain_text('100.0% evaluation pass rate, 11 replacement trading days')
    playwright.expect(sizing).to_contain_text('$178.00 per funded account')
    assert 'Training selection assumes' not in sizing.inner_text()
    playwright.expect(sizing.locator('tbody tr')).to_have_count(40)
    page.screenshot(path=str(tmp_path/'training-sizing.png'),full_page=True)
    page.get_by_role('tab',name='Historical replay',exact=True).click()
    playwright.expect(page.locator('#prop-view-history')).to_contain_text('frozen training calibration')
    page.get_by_role('tab',name='Evaluation',exact=True).click()
    playwright.expect(page.locator('#prop-view-evaluation')).to_contain_text('Training calibration used for selection')
    with page.expect_download() as download:
        page.get_by_role('link',name='Download training calibration (JSON)',exact=True).click()
    download.value.save_as(tmp_path/'training_economics.json')
    economics=json.loads((tmp_path/'training_economics.json').read_text())
    assert economics['pass_rate']==1 and economics['cost_per_funded']==178 and economics['replacement_days']==11
    assert economics['method']=='training_simulation' and economics['sample']==report['calculations']['samples']['train']
    rows=list(csv.DictReader(io.StringIO(page.request.get(portal['url']+'/api/prop-analyses/'+id+'/files/funded_sizing.csv').text())))
    assert len(rows)==40 and all(float(row['acquisition_cost'])==178 and float(row['replacement_days'])==11 for row in rows)
    (tmp_path/'report.json').write_text(json.dumps(report,indent=2))
    posts=[];page.on('request',lambda req:posts.append(req.url) if req.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert not posts


def test_zero_training_passes_are_visible_even_when_holdout_passes(page,portal,tmp_path):
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol'];day=date(2026,1,5);n=0
    while n<10:
        if day.weekday()<5:
            close='100' if n<7 else '103'
            for minute,prices in ((0,'99,100,99,100'),(1,f'100,{close},100,{close}'),(2,f'{close},{close},{close},{close}')):
                lines.append(day.strftime('%m/%d/%Y')+f',18:0{minute},{prices},100,60,40')
            n+=1
        day+=timedelta(days=1)
    raw=('\n'.join(lines)+'\n').encode();(tmp_path/'SYNTHETIC-zero-training.csv').write_bytes(raw)
    with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:
        saved=client.post('/api/datasets',params=dict(filename='SYNTHETIC-zero-training.csv',name='SYNTHETIC zero training and profitable holdout',source_timezone='UTC',tick_size='.25',point_value='1000'),content=raw)
        assert saved.status_code==201,saved.text
        request=body(saved.json()['id']);request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
        request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
        response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
        record=response.json();id=record['run_metadata']['automatic_prop_analysis']['id']
        report=client.get('/api/prop-analyses/'+id+'/downloads/report.json').json()
        assert report['calculations']['training_economics']['pass_rate']==0
        assert report['calculations']['evaluation']['pass_rate']==1
        assert report['calculations']['funded'] is None
    open_native(page,portal,record)
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('No training evaluation passed')
    playwright.expect(page.get_by_role('tab',name='Sizing',exact=True)).to_have_count(0)
    page.get_by_role('tab',name='Evaluation',exact=True).click()
    panel=page.locator('#prop-view-evaluation')
    playwright.expect(panel).to_contain_text('100.0%')
    playwright.expect(panel).to_contain_text('Training calibration used for selection')
    playwright.expect(panel).to_contain_text('No training evaluation passed')
    page.screenshot(path=str(tmp_path/'zero-training-rejection.png'),full_page=True)
    (tmp_path/'rejection-report.json').write_text(json.dumps(report,indent=2))

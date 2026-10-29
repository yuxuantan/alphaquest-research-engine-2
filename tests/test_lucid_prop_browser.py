"""Two automatic models through the real report/configure/check/run workflow."""
import io,json,zipfile
from hashlib import sha256
from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal,playwright
from test_backtest_api import body
from test_automatic_prop import save_history,expected_cash


def expected_lucid(report):
    c=report['calculations'];t=c['training_economics'];s=c['funded']['selected']
    assert report['model_version']=='alphaquest-lucidflex50k-eod-v1'
    assert report['settings']['EVAL_PRICE']=='80.5' and report['settings']['ACTIVATION_FEE']=='0'
    assert (t['pass_rate'],t['replacement_days'],t['cost_per_funded'])==(1,10,80.5)
    assert t['activation_days']==0 and t['funding_chain_simulations']==20000
    assert s['micros']==3 and s['E[payout]']==9000 and s['days alive']==25 and s['sims']==20000
    assert c['history']['totals']['payouts']==90000
    assert c['history']['totals']['costs']==805
    assert c['history']['totals']['net']==89195
    assert len(c['evaluation_sweep'])==len(c['funded']['sweep'])==40
    assert all(r['simulations']==3000 for r in c['evaluation_sweep'])
    assert all(r['sims']==3000 for r in c['funded']['sweep'])
    assert c['rules']['payout_share']==.9 and len(c['rules']['ladder'])==5


def test_both_automatic_models_actual_product_download_and_reopen(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        dataset=save_history(client);request=body(dataset['id'])
        request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
        request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
        response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
        record=response.json();automatic=record['run_metadata']['automatic_prop_analysis'];lucid=automatic['companions'][0]
        apex_bytes=client.get('/api/prop-analyses/'+automatic['id']+'/downloads/report.json').content
        lucid_bytes=client.get('/api/prop-analyses/'+lucid['id']+'/downloads/report.json').content
        expected_cash(json.loads(apex_bytes));expected_lucid(json.loads(lucid_bytes))
        source=client.get('/api/backtests/'+record['id']+'/exports/trades').content
        (tmp_path/'backtest.json').write_text(json.dumps(record,indent=2))
        (tmp_path/'backtest-request.json').write_text(json.dumps(request,indent=2))
        (tmp_path/'apex-report.json').write_bytes(apex_bytes);(tmp_path/'lucid-report.json').write_bytes(lucid_bytes)
    page.goto(portal['url']+'/#backtests/report/'+record['id'])
    playwright.expect(page.locator('#report-historical-net')).to_have_text('$352,880',timeout=30000)
    playwright.expect(page.locator('#report-lucid-historical-net')).to_have_text('$89,195',timeout=30000)
    playwright.expect(page.locator('#report-prop-companions')).to_contain_text('LucidFlex 50K')
    page.screenshot(path=str(tmp_path/'two-account-backtest-report.png'),full_page=True)
    page.locator('#report-prop-setup').click()
    page.locator('#prop-model').select_option('1')
    playwright.expect(page.locator('#prop-eval-fee')).to_have_value('80.5')
    playwright.expect(page.locator('#prop-activation')).to_have_value('0')
    playwright.expect(page.locator('#prop-slots')).to_have_value('5')
    playwright.expect(page.locator('#prop-commission-side')).to_have_value('0.50')
    playwright.expect(page.locator('#prop-commission-source')).to_have_attribute('href','https://support.lucidtrading.com/en/articles/11508978-approved-products-and-commissions')
    page.locator('#prop-trade-file').fill('')
    # Boundary rejection occurs in the same source check, not a test-only page.
    page.locator('#prop-slots').fill('6');page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-status')).to_contain_text('SLOTS must be an integer from 1 to 5')
    playwright.expect(page.locator('#prop-run')).to_be_disabled()
    page.locator('#prop-slots').fill('5')
    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as check:
        page.locator('#prop-check').click()
    assert check.value.status==200
    checked=check.value.json();assert checked['matched_trades']==60
    assert checked['model_version']=='alphaquest-lucidflex50k-eod-v1'
    assert checked['source']['excursion_input']['native_ohlc_count']==60
    (tmp_path/'source-check.json').write_text(json.dumps(checked,indent=2))
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    page.screenshot(path=str(tmp_path/'lucid-configure-source-check.png'),full_page=True)
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
    assert page.url.endswith(lucid['id']) # The durable automatic report reopens.
    playwright.expect(page.locator('#prop-heading-note')).to_contain_text('LucidFlex 50K')
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('All 5 payouts')
    page.get_by_role('tab',name='Historical replay',exact=True).click()
    playwright.expect(page.locator('#prop-view-history')).to_contain_text('$89,195')
    page.screenshot(path=str(tmp_path/'lucid-history.png'),full_page=True)
    page.get_by_role('tab',name='Source & model',exact=True).click()
    playwright.expect(page.locator('#prop-view-model')).to_contain_text('LucidFlex rules checked 2026-10-29')
    with page.expect_download() as download:page.get_by_role('link',name='Download LucidFlex rule snapshot (JSON)',exact=True).click()
    download.value.save_as(tmp_path/'provider_rules.json')
    with page.expect_download() as download:page.get_by_role('link',name='Download all results (ZIP)',exact=True).click()
    download.value.save_as(tmp_path/'analysis.zip')
    with zipfile.ZipFile(tmp_path/'analysis.zip') as archive:
        assert archive.read('report.json')==lucid_bytes
        assert json.loads(archive.read('provider_rules.json'))==json.loads((tmp_path/'provider_rules.json').read_text())
    page.screenshot(path=str(tmp_path/'lucid-provider-rules.png'),full_page=True)
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert not posts
    assert page.request.get(portal['url']+'/api/prop-analyses/'+automatic['id']+'/downloads/report.json').body()==apex_bytes
    assert sha256(page.request.get(portal['url']+'/api/backtests/'+record['id']+'/exports/trades').body()).hexdigest()==sha256(source).hexdigest()
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,source_id=record['id'],apex_id=automatic['id'],lucid_id=lucid['id'],
        expected_apex_net=352880,expected_lucid_net=89195,expected_lucid_payout=9000,source_unchanged=True,apex_unchanged=True,
        source_check_trades=60,sizing_points_each=40,standard_counts=True,reload_posts=posts),indent=2))


def test_known_nq_source_provider_commissions_and_renewal_cash(page,portal,tmp_path):
    from decimal import Decimal
    import csv
    from test_prop_commissions_browser import synthetic_nq
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        uploaded=client.post('/api/datasets',params=dict(filename='SYNTHETIC-NQ-Lucid.csv',
            name='SYNTHETIC NQ provider commission arithmetic - not market history',symbol='NQ',
            source_timezone='UTC',tick_size='.25',point_value='20'),content=synthetic_nq())
        assert uploaded.status_code==201,uploaded.text
        request=body(uploaded.json()['id']);request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
        request['execution_settings'].update(slippage_ticks=1,commission_per_contract_per_side='1.99')
        response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
        record=response.json();a=record['run_metadata']['automatic_prop_analysis'];id=a['companions'][0]['id']
        report=client.get('/api/prop-analyses/'+id+'/downloads/report.json').json();c=report['calculations']
        assert report['source']['commission_simulation']['applied']
        assert report['source']['commission_simulation']['per_side']=='0.50'
        rows=list(csv.DictReader(io.StringIO(client.get('/api/prop-analyses/'+id+'/downloads/trades.csv').text)))
        # Source NQ: 3000 - 10 slippage - 3.98 fee = 2986.02. Per MNQ:
        # (2986.02 + 3.98)/10 - 2*.50 = 298; 10 days earn 2980, so eval takes 11.
        assert all(Decimal(row['simulation_net_per_mnq'])==298 and Decimal(row['source_net_pnl'])==Decimal('2986.02') for row in rows)
        assert c['training_economics']['replacement_days']==11
        assert c['training_economics']['cost_per_funded']==80.5
        assert c['funded']['selected']['micros']==3 and c['funded']['selected']['E[payout]']==9000
        # 25 funded days + 11 replacement days leave 24 funded days. The second
        # account receives four payouts: (9000 + 7200)*5 - 2*80.50*5 = 80,195.
        assert c['history']['totals']['payouts']==81000 and c['history']['totals']['costs']==805
        assert c['history']['totals']['net']==80195
        assert client.get('/api/prop-analyses/'+a['id']).json()['historical_net']==352880
        (tmp_path/'backtest.json').write_text(json.dumps(record,indent=2));(tmp_path/'lucid-report.json').write_text(json.dumps(report,indent=2))
        (tmp_path/'trades.csv').write_text(client.get('/api/prop-analyses/'+id+'/downloads/trades.csv').text)
        (tmp_path/'analysis.zip').write_bytes(client.get('/api/prop-analyses/'+id+'/downloads/analysis.zip').content)
    page.goto(portal['url']+'/#backtests/report/'+record['id'])
    playwright.expect(page.locator('#report-lucid-historical-net')).to_have_text('$80,195',timeout=30000)
    page.screenshot(path=str(tmp_path/'priced-nq-two-model-summary.png'),full_page=True)
    page.locator('#report-prop-setup').click();page.locator('#prop-model').select_option('1');page.locator('#prop-trade-file').fill('')
    page.locator('#prop-check').click();playwright.expect(page.locator('#prop-run')).to_be_enabled()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('Lucid · NQ source → MNQ orders')
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
    assert page.url.endswith(id)
    page.screenshot(path=str(tmp_path/'priced-nq-lucid-report.png'),full_page=True)
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,source_id=record['id'],lucid_id=id,
        micro_net='298',replacement_days=11,lifetime_payout=9000,historical_payouts=81000,acquisition_cost=805,historical_net=80195),indent=2))

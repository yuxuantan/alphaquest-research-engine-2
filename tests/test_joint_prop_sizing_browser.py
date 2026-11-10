"""Normal product journey with independently derived joint sizing and cash."""
from prop_setup_helpers import open_prop_task
import csv
from decimal import Decimal
import io
import json
import zipfile

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright
from test_backtest_api import body
from test_automatic_prop import save_history, expected_cash
from test_lucid_prop_browser import expected_lucid


def test_joint_sizing_actual_backtest_configure_check_run_download_and_reopen(page, portal, tmp_path):
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        dataset=save_history(client)
        request=body(dataset['id'])
        request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
        request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
        response=client.post('/api/backtests',json=request)
        assert response.status_code==201,response.text
        record=response.json();automatic=record['run_metadata']['automatic_prop_analysis']
        id=automatic['companions'][0]['id']
        expected_cash(client.get('/api/prop-analyses/'+automatic['id']+'/downloads/report.json').json())
        report=client.get('/api/prop-analyses/'+id+'/downloads/report.json').json();expected_lucid(report)
        original=client.get('/api/backtests/'+record['id']+'/exports/trades').content
        joint=report['calculations']['joint_sizing'];chosen=joint['selected']
        # Source: $3000 per NQ each weekday, no costs/risk. Four MNQ make
        # $1200/day and pass in three days with a 1/3 largest-day share. Three
        # funded MNQ make $900/day and pay all five $2000 caps, less 10%, in
        # 25 sessions. Smaller funded size cannot pay every cap that quickly.
        assert (chosen['evaluation_micros'],chosen['funded_micros'])==(4,3)
        expected=Decimal(261)*(Decimal(9000)-Decimal('80.5'))/Decimal(28)
        assert chosen['slot_year']==float(expected)
        assert chosen['acquisition_days']==3 and chosen['funded_days']==25
        assert len(joint['pairs'])==1600
        assert joint['selected']['evaluation_simulations']==20000
        assert joint['selected']['funded_simulations']==20000
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.goto(portal['url']+'/#backtests/report/'+record['id'])
    page.locator('#report-prop-setup').click();open_prop_task(page, 'legacy');page.locator('#prop-model').select_option('1')
    open_prop_task(page, 'legacy', close_outer=False)
    page.locator('#prop-advanced > summary').click()
    open_prop_task(page, 'legacy', close_outer=False)
    page.locator('#prop-slots').fill('6');page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-status')).to_contain_text('SLOTS must be an integer from 1 to 5')
    playwright.expect(page.locator('#prop-run')).to_be_disabled()
    page.locator('#prop-slots').fill('5')
    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as check:
        open_prop_task(page, 'legacy', close_outer=False)
        page.locator('#prop-check').click()
    assert check.value.status==200
    (tmp_path/'source-check.json').write_text(json.dumps(check.value.json(),indent=2))
    page.screenshot(path=str(tmp_path/'01-source-check.png'),full_page=True)
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=60000)
    assert page.url.endswith(id)
    page.get_by_role('tab',name='Sizing',exact=True).click()
    panel=page.locator('#prop-joint-sizing')
    playwright.expect(panel).to_contain_text('Evaluation and funded sizes chosen together')
    playwright.expect(panel).to_contain_text('4 MNQ')
    playwright.expect(panel).to_contain_text('3 MNQ')
    playwright.expect(page.locator('#prop-joint-pairs tbody tr')).to_have_count(40)
    page.screenshot(path=str(tmp_path/'02-joint-sizing.png'),full_page=True)
    for label,name in [('Download all evaluation/funded pairs (CSV)','joint_sizing.csv'),
                       ('Download joint sizing and provenance (JSON)','joint_sizing.json')]:
        with page.expect_download() as download:page.get_by_role('link',name=label,exact=True).click()
        download.value.save_as(tmp_path/name)
    pairs=list(csv.DictReader(io.StringIO((tmp_path/'joint_sizing.csv').read_text())))
    assert len(pairs)==1600
    for row in pairs:
        assert row['status']=='ranked'
        expected=Decimal(261)*(Decimal(row['expected_receipts'])-Decimal(row['acquisition_cost']))/(Decimal(row['funded_days'])+Decimal(row['acquisition_days']))
        assert abs(Decimal(row['slot_year'])-expected)<Decimal('.000000001')
    page.locator('#prop-joint-eval-filter').select_option('1')
    playwright.expect(page.locator('#prop-joint-pairs tbody tr')).to_have_count(40)
    page.get_by_role('tab',name='Historical replay',exact=True).click()
    playwright.expect(page.locator('#prop-view-history')).to_contain_text('$88,792')
    page.screenshot(path=str(tmp_path/'03-historical-cash.png'),full_page=True)
    page.get_by_role('tab',name='Source & model',exact=True).click()
    with page.expect_download() as download:page.get_by_role('link',name='Download all results (ZIP)',exact=True).click()
    download.value.save_as(tmp_path/'analysis.zip')
    with zipfile.ZipFile(tmp_path/'analysis.zip') as archive:
        assert json.loads(archive.read('joint_sizing.json'))==joint
        assert archive.read('joint_sizing.csv')==(tmp_path/'joint_sizing.csv').read_bytes()
    page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert page.request.get(portal['url']+'/api/backtests/'+record['id']+'/exports/trades').body()==original
    assert not any('/api/backtests' in path for path in posts)
    (tmp_path/'report.json').write_text(json.dumps(report,indent=2))
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,source_id=record['id'],analysis_id=id,
        evaluation_micros=4,funded_micros=3,independent_training_annualized_net=float(Decimal(261)*(Decimal(9000)-Decimal('80.5'))/Decimal(28)),
        historical_payouts=90000,historical_costs=1208,historical_net=88792,
        pairs_independently_checked=1600,source_unchanged=True,same_report_reopened=True),indent=2))

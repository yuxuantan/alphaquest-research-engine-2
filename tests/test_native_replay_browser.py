"""Real MNQ bars -> saved source -> native account control -> durable product evidence."""
from prop_setup_helpers import open_prop_task
from decimal import Decimal
from hashlib import sha256
import io
import json
import re
import zipfile

import pytest

from native_replay_fixtures import EXPECTED
from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_native_replay_api import source


def configure(page, portal, record, phase='funded', kind='percentage_risk', risk='0.2', cap='40'):
    page.goto(portal['url']+'/#backtests/report/'+record['id'])
    playwright.expect(page.locator('#report-prop-setup')).to_be_visible()
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'inspect', close_outer=True)
    page.locator('#native-configure > summary').click()
    page.locator('#native-phase').select_option(phase)
    page.locator('#native-micros').fill(cap)
    if kind:
        page.locator('.native-sizing-mode').select_option('policies')
        page.locator('.native-policy-kind').select_option(kind)
        if kind == 'percentage_risk':
            page.locator('.native-policy-percent').fill(risk)
            page.locator('.native-policy-reference').select_option('current_account_balance')
        elif kind == 'fixed_dollar_risk':
            page.locator('.native-policy-dollars').fill(risk)
    if phase == 'evaluation':
        page.locator('#native-evaluation-fee').fill('30')
        page.locator('#native-activation-fee').fill('40')


def run(page, portal, tmp_path):
    page.locator('#native-check').click()
    playwright.expect(page.locator('#native-run')).to_be_enabled(timeout=60000)
    playwright.expect(page.locator('#native-check-output')).to_contain_text('Actual costs charged once')
    page.locator('#prop-native-replay').screenshot(path=str(tmp_path/'checked-native-source.png'))
    page.locator('#native-run').click()
    playwright.expect(page.locator('#native-result')).to_be_visible(timeout=90000)
    id = page.url.rsplit('/',1)[-1]
    response = page.request.get(portal['url']+f'/api/prop-analyses/{id}/downloads/report.json')
    assert response.ok, response.text()
    return response.json()


def preserve(page, portal, report, tmp_path, expected, original, **fixture):
    id = report['id']; native_id = report['native_backtest_id']
    response = page.request.get(portal['url']+f'/api/backtests/{native_id}/trades')
    assert response.ok
    trades = response.json()['items']
    assert [t['contracts'] for t in trades] == expected['quantities']
    assert [Decimal(t['net_pnl']) for t in trades] == list(map(Decimal,expected['trade_nets']))
    assert Decimal(report['calculations']['trace'][-1]['state_after']['balance']) == Decimal(expected['final_balance'])
    assert report['calculations']['native_forecast_available'] is False
    assert page.request.get(portal['url']+'/api/backtests/'+original['id']).json() == original
    playwright.expect(page.locator('#native-result')).to_contain_text('HISTORICAL_SCENARIO_ONLY')
    playwright.expect(page.locator('#native-result')).to_contain_text('This saved report contains no native Monte Carlo forecast')
    playwright.expect(page.locator('#native-decision-table')).to_contain_text('118')
    page.locator('#native-decisions').screenshot(path=str(tmp_path/'causal-decisions-and-fills.png'))
    page.locator('#native-cash-ledger').screenshot(path=str(tmp_path/'dated-cash-ledger.png'))
    page.screenshot(path=str(tmp_path/'native-result.png'), full_page=True)
    downloads={}
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        urls={'report.json':f'/api/prop-analyses/{id}/downloads/report.json',
              'analysis.zip':f'/api/prop-analyses/{id}/downloads/analysis.zip',
              'original-trades.csv':f"/api/backtests/{original['id']}/exports/trades",
              'original-source-report.json':f"/api/backtests/{original['id']}",
              'SYNTHETIC-MNQ-observed-bars.csv':f"/api/datasets/{original['run_metadata']['dataset']['id']}/csv",
              'actual-trades.csv':f'/api/backtests/{native_id}/exports/trades',
              'actual-equity.csv':f'/api/backtests/{native_id}/exports/equity'}
        urls.update({name:f'/api/prop-analyses/{id}/files/{name}' for name in report['files']})
        for name,url in urls.items():
            r=client.get(url);assert r.status_code==200,(name,r.text)
            path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(r.content)
            downloads[name]=sha256(r.content).hexdigest()
        assert downloads['SYNTHETIC-MNQ-observed-bars.csv']==original['run_metadata']['dataset']['sha256']
        declaration=json.dumps(original['run_metadata']['research'],indent=2).encode()
        (tmp_path/'source-research-declaration.json').write_bytes(declaration)
        downloads['source-research-declaration.json']=sha256(declaration).hexdigest()
        with zipfile.ZipFile(io.BytesIO((tmp_path/'analysis.zip').read_bytes())) as archive:
            assert archive.read('trades.csv') == (tmp_path/'actual-trades.csv').read_bytes()
            assert {'execution_decisions.jsonl','control_events.json','sizing_decisions.json','session_trace.json','cash_ledger.json'} <= set(archive.namelist())
    page.locator('#native-result').get_by_role('link',name='Open actual controlled backtest',exact=True).click()
    playwright.expect(page).to_have_url(re.compile('/#backtests/report/'+native_id+'$'))
    playwright.expect(page.locator('#report-prop-setup')).to_be_visible()
    playwright.expect(page.locator('#report-research-title')).to_have_text('Native account-state historical replay')
    playwright.expect(page.locator('#backtest-completion-content')).to_contain_text('Actual native account-controlled replay')
    playwright.expect(page.locator('#report-prop-status')).to_contain_text('One historical native strategy path')
    playwright.expect(page.locator('#report-prop-native-trading')).to_be_visible()
    page.screenshot(path=str(tmp_path/'ordinary-controlled-backtest.png'),full_page=True)
    page.goto(portal['url']+'/#backtests/prop/job/'+id)
    playwright.expect(page.locator('#native-result')).to_be_visible()
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#native-result')).to_be_visible()
    assert posts==[]
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path/'narrow-native-result.png'))
    page.locator('#native-decisions h3').scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path/'narrow-native-decisions.png'))
    (tmp_path/'browser-evidence.json').write_text(json.dumps(dict(source_id=original['id'],analysis_id=id,
        native_backtest_id=native_id,expected=expected,downloads=downloads,reopen_posts=posts,
        source_dataset_id=original['run_metadata']['dataset']['id'],
        source_dataset_sha256=original['run_metadata']['dataset']['sha256'],
        source_research_plan=original['run_metadata']['research']['plan'],
        source_fixture_note='All bars are synthetic. The final saved row is a separately reserved synthetic OOS date; it is not executed in the native IS replay. Use the saved research declaration for exact split dates.',
        engine_identity=report['engine_identity'],library=str(tmp_path),
        server='Owned temporary uvicorn server stopped by portal fixture.'),indent=2))


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_native_percentage_balance_changes_real_quantities(page,portal,tmp_path,phase):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client: original=source(client)
    configure(page,portal,original,phase)
    # A missing session is rejected by the real source checker, with no result publication.
    page.locator('#native-first').fill('2026-01-04');page.locator('#native-last').fill('2026-01-07')
    page.locator('#native-check').click()
    playwright.expect(page.locator('#native-status')).to_contain_text('whole observed',timeout=60000)
    playwright.expect(page.locator('#native-run')).to_be_disabled()
    page.locator('#prop-native-replay').screenshot(path=str(tmp_path/'rejected-unobserved-session.png'))
    page.locator('#native-first').fill('');page.locator('#native-last').fill('')
    report=run(page,portal,tmp_path)
    c=report['calculations'];oracle=EXPECTED['percentage']
    assert [Decimal(d['state_before']['balance']) for d in c['sizing_decisions']] == list(map(Decimal,oracle['decision_balances']))
    assert [Decimal(d['planned_risk_per_mnq']) for d in c['sizing_decisions']] == [10,10,20]
    if phase=='evaluation':
        assert Decimal(c['paid_evaluation_fees'])==30 and Decimal(c['paid_activation_fees'])==0
        assert c['acquisition_completed'] is False and c['censored'] is True
    else: assert Decimal(c['cash_received'])==Decimal(c['pending_cash'])==0
    preserve(page,portal,report,tmp_path,oracle,original)


def test_native_gap_keeps_causal_quantity_and_discloses_actual_risk(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client: original=source(client,gap=True)
    configure(page,portal,original)
    report=run(page,portal,tmp_path)
    fill=next(e for e in report['calculations']['control_events'] if e['event']=='entry_fill')
    assert Decimal(fill['actual_fill_price'])==120 and fill['quantity']==10
    assert Decimal(fill['fill_gap_risk_change_per_mnq'])==4
    preserve(page,portal,report,tmp_path,EXPECTED['gap_percentage'],original,gap=True)


def test_native_fixed_dollars_reacts_to_known_stop_distance(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client: original=source(client)
    configure(page,portal,original,kind='fixed_dollar_risk',risk='100')
    report=run(page,portal,tmp_path)
    assert [Decimal(d['planned_risk_per_mnq']) for d in report['calculations']['sizing_decisions']] == [10,10,20]
    preserve(page,portal,report,tmp_path,EXPECTED['fixed_dollars'],original)


def test_native_skipped_signal_preserves_later_strategy_eligibility(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client: original=source(client,days=1,skip_retry=True)
    assert original['summary']['trades_taken']==1 and Decimal(original['summary']['total_net_pnl'])==-10
    configure(page,portal,original,kind='fixed_dollar_risk',risk='1')
    report=run(page,portal,tmp_path)
    rows=report['calculations']['sizing_decisions'];accepted=[r for r in rows if r['quantity']]
    assert len(accepted)==1 and accepted[0]['quantity']==2
    assert accepted[0]['sizing_decision_time_utc'].startswith('2026-01-05T15:06:')
    assert any(r['quantity']==0 and 'below_minimum_tradable_quantity' in r['reasons'] for r in rows)
    preserve(page,portal,report,tmp_path,dict(quantities=[2],trade_nets=['12'],final_balance='50012'),original,days=1,skip_retry=True)


def test_native_payout_keeps_trading_equity_and_provider_cash_distinct(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client: original=source(client,days=7,payout=True)
    configure(page,portal,original,kind=None,cap='3')
    report=run(page,portal,tmp_path);c=report['calculations']
    assert Decimal(c['trading_profit'])==6300 and Decimal(c['gross_account_deductions'])==1500
    assert Decimal(c['cash_received'])==1500 and Decimal(c['pending_cash'])==0
    assert Decimal(report['native_backtest']['summary']['final_equity'])==16300
    payout,=c['payout_events'];assert payout['request_date']=='2026-01-09' and payout['receipt_date']=='2026-01-11'
    playwright.expect(page.locator('#native-payout-table')).to_contain_text('2026-01-11')
    preserve(page,portal,report,tmp_path,dict(quantities=[3]*7,trade_nets=['900']*7,final_balance='54800'),original,days=7,payout=True)

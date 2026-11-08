"""Normal source report → explicit frozen pair → actual dated cash report."""
from prop_setup_helpers import open_prop_task
from decimal import Decimal
from hashlib import sha256
import io
import json
from uuid import uuid4
import zipfile

import httpx
from test_backtests_browser import browser, page, playwright
from test_research_procedure_browser import portal
from test_frozen_pair_api import save_complete_native_split, frozen_phase


def select_phase(page, phase, reference, oos_id):
    prefix='#pair-1-'+phase
    page.locator(prefix+'-campaign').select_option(reference['campaign_id'])
    playwright.expect(page.locator(prefix+'-candidate option')).to_have_count(2,timeout=30000)
    page.locator(prefix+'-candidate').select_option(reference['candidate_id'])
    playwright.expect(page.locator(prefix+'-oos option')).to_have_count(2,timeout=30000)
    page.locator(prefix+'-oos').select_option(oos_id)


def test_frozen_pair_normal_report_check_run_cash_and_reopen(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        parent=save_complete_native_split(client)
        evaluation,evaluation_bytes=frozen_phase(client,parent,'evaluation')
        funded,funded_bytes=frozen_phase(client,parent,'funded')
        response=client.post('/api/backtests/'+parent['id']+'/oos',json=dict(request_id=uuid4().hex))
        assert response.status_code==201,response.text
        oos=response.json()
    access_before=page.request.get(portal['url']+'/api/backtests/'+parent['id']+'/oos').json()['used']
    page.goto(portal['url']+'/#backtests/report/'+oos['id'])
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'pair', close_outer=True)
    page.locator('#pair-configure > summary').click()
    page.locator('#pair-1-name').fill('SYNTHETIC frozen 3 MNQ Evaluation → 3 MNQ Funded')
    page.locator('#pair-first').fill('2026-01-26')
    page.locator('#pair-cutoff').fill('2026-02-10')
    select_phase(page,'evaluation',evaluation,oos['id']);select_phase(page,'funded',funded,oos['id'])
    page.locator('#pair-check').click()
    playwright.expect(page.locator('#pair-status')).to_contain_text('cannot exceed either independently tested native horizon',timeout=60000)
    playwright.expect(page.locator('#pair-run')).to_be_disabled()
    page.locator('#pair-status').screenshot(path=str(tmp_path/'common-horizon-rejection.png'))
    page.locator('#pair-cutoff').fill('2026-02-09')
    page.locator('#pair-check').click()
    playwright.expect(page.locator('#pair-run')).to_be_enabled(timeout=60000)
    assert page.request.get(portal['url']+'/api/backtests/'+parent['id']+'/oos').json()['used']==access_before
    page.locator('#pair-form').screenshot(path=str(tmp_path/'reviewed-frozen-pair.png'))
    page.locator('#pair-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Frozen Evaluation / Funded pair comparison',timeout=180000)
    analysis_id=page.url.rsplit('/',1)[-1]
    response=page.request.get(portal['url']+f'/api/prop-analyses/{analysis_id}/downloads/report.json');assert response.ok,response.text()
    report=response.json();calc=report['calculations'];row,=calc['pairs']
    assert calc['winner'] is None and calc['selection_status']=='comparison_only_no_selection'
    assert Decimal(row['cash']['paid_evaluation_fees'])==30
    assert Decimal(row['cash']['paid_activation_fees'])==40
    assert Decimal(row['cash']['cash_received'])==1500
    assert Decimal(row['cash']['pending_cash'])==0
    assert Decimal(row['cash']['gross_account_deductions'])==1500
    assert Decimal(row['cash']['net_trader_cash'])==1430
    assert row['evaluation']['ready_date']=='2026-02-02'
    assert row['funded_status']=='started'
    event,=row['funded']['payout_events']
    assert event['request_date']=='2026-02-06' and event['receipt_date']=='2026-02-08'
    assert row['continuation_binding']['estimand']=='remaining_horizon_chronological_continuation'
    assert len(report['native_backtests'])==2
    for phase,reference,original in [('evaluation',evaluation,evaluation_bytes),('funded',funded,funded_bytes)]:
        assert page.request.get(portal['url']+f'/api/research-campaigns/{reference["campaign_id"]}/exports/frozen_package.json').body()==original
        assert row['pair_binding']['policies'][phase]['package_sha256']==reference['package_sha256']
    playwright.expect(page.locator('#pair-cash-summary')).to_contain_text('1430')
    page.locator('#pair-cash-summary').screenshot(path=str(tmp_path/'pair-cash-summary.png'))
    page.locator('#pair-ledger-1').screenshot(path=str(tmp_path/'actual-pair-cash-ledger.png'))
    child=row['native_backtests']['funded']['id']
    page.locator('#pair-result-1').get_by_text('Fresh Funded continuation · actual strategy/account trace',exact=True).click()
    page.locator('#pair-result-1').get_by_role('link',name='Open actual controlled backtest',exact=True).last.click()
    playwright.expect(page.locator('#report-prop-setup')).to_be_visible()
    assert page.url.endswith('/'+child)
    page.goto(portal['url']+'/#backtests/prop/job/'+analysis_id)
    playwright.expect(page.locator('#pair-cash-summary')).to_be_visible()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#pair-cash-summary').screenshot(path=str(tmp_path/'pair-cash-narrow.png'))
    downloads={}
    for name,url in {'report.json':f'/api/prop-analyses/{analysis_id}/downloads/report.json',
        'analysis.zip':f'/api/prop-analyses/{analysis_id}/downloads/analysis.zip',
        'source-report.json':'/api/backtests/'+parent['id'],
        'ordinary-oos-report.json':'/api/backtests/'+oos['id'],
        'SYNTHETIC-frozen-pair.csv':'/api/datasets/'+parent['run_metadata']['dataset']['id']+'/csv',
        'evaluation-package.json':f'/api/research-campaigns/{evaluation["campaign_id"]}/exports/frozen_package.json',
        'funded-package.json':f'/api/research-campaigns/{funded["campaign_id"]}/exports/frozen_package.json'}.items():
        response=page.request.get(portal['url']+url);assert response.ok,response.text()
        (tmp_path/name).write_bytes(response.body());downloads[name]=sha256(response.body()).hexdigest()
    assert downloads['SYNTHETIC-frozen-pair.csv']==parent['run_metadata']['dataset']['sha256']
    with zipfile.ZipFile(io.BytesIO((tmp_path/'analysis.zip').read_bytes())) as archive:
        for name,entry in report['files'].items():assert sha256(archive.read(name)).hexdigest()==(entry['sha256'] if isinstance(entry,dict) else entry)
    posts=[];page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#pair-cash-summary')).to_contain_text('1430');assert not posts
    assert sha256(page.request.get(portal['url']+f'/api/prop-analyses/{analysis_id}/downloads/report.json').body()).hexdigest()==downloads['report.json']
    assert page.request.get(portal['url']+'/api/backtests/'+parent['id']+'/oos').json()['used']==access_before
    (tmp_path/'evidence.json').write_text(json.dumps(dict(source_id=parent['id'],oos_id=oos['id'],analysis_id=analysis_id,
        evaluation=evaluation,funded=funded,expected=dict(evaluation_fee=30,activation_fee=40,received=1500,pending=0,gross_deduction=1500,net_trader_cash=1430,ready_date='2026-02-02',request_date='2026-02-06',receipt_date='2026-02-08'),
        source_research=parent['run_metadata']['research'],downloads=downloads,reopen_posts=posts,no_new_oos_on_check_or_reopen=True,original_packages_unchanged=True,
        server='Owned temporary portal fixture stopped its server.'),indent=2))

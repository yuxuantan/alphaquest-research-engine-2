"""Milestone 2 normal-workflow product demonstration with inspectable saved outputs."""
from decimal import Decimal
import json

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright
from test_prop_phases import phase_history
from test_prop_cash import assert_conservation


def save_cash_source(client,phase):
    raw=phase_history(35).decode()
    lines=raw.splitlines()
    for index,line in enumerate(lines):
        if (phase=='evaluation' and line.startswith('01/05/2026,18:01,')):
            lines[index]=line.replace('100,250,100,250','-50,250,-50,250')
        if (phase=='funded' and line.startswith('01/15/2026,18:01,')):
            lines[index]=line.replace('100,250,100,250','-1400,250,-1400,250')
    raw=('\n'.join(lines)+'\n').encode()
    dataset=client.post('/api/datasets',params=dict(filename=f'SYNTHETIC-cash-{phase}.csv',name=f'SYNTHETIC cash {phase}; fee overrides $30/$40',
        source_timezone='UTC',tick_size='.25',point_value='20',symbol='NQ'),content=raw)
    assert dataset.status_code==201,dataset.text
    result=client.post('/api/backtests',json=dict(dataset_id=dataset.json()['id'],strategy_id='consecutive_green_hold',
        strategy_parameters=dict(green_bar_count=1,hold_minutes=1,contracts=1),
        execution_settings=dict(initial_capital='10000',tick_size='.25',point_value='20',slippage_ticks=0,commission_per_contract_per_side='0')))
    assert result.status_code==201,result.text
    return result.json()


def test_budget_configuration_cash_downloads_and_durable_report(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        evaluation=save_cash_source(client,'evaluation');funded=save_cash_source(client,'funded')
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.goto(portal['url']+'/#backtests/report/'+evaluation['id'])
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    page.locator('#prop-method').select_option('budgeted_lifecycle')
    timezone=page.locator('#prop-budget-timezone')
    assert timezone.evaluate('(node)=>node.tagName')=='SELECT'
    playwright.expect(timezone).to_have_value('America/Chicago')
    assert timezone.locator('option').evaluate_all('(nodes)=>nodes.map(n=>n.value)')==['America/Chicago','America/New_York','Asia/Singapore','UTC']
    page.locator('#prop-advanced > summary').click()
    page.locator('#prop-payout-preset').select_option('custom')
    page.locator('#prop-activation-preset').select_option('custom')
    page.locator('#prop-commission-mode').select_option('source')
    page.locator('#prop-funded-source').select_option(funded['id'])
    page.locator('#prop-evaluation-micros').fill('10');page.locator('#prop-funded-micros').fill('3')
    fields={'prop-eval-fee':'30','prop-activation':'40','prop-monthly-cap':'100',
        'prop-start-date':'2026-01-05','prop-horizon-end':'2026-01-31','prop-receipt-days':'30','prop-deadline-days':'7','prop-payment-days':'0',
        'prop-payout-assumption':'SYNTHETIC unverified model: receipt 30 calendar days after request, at same budget-local wall time.',
        'prop-activation-assumption':'SYNTHETIC unverified model: inclusive deadline 7 calendar days after eligibility, payment delay as saved; not provider policy.',
        'prop-fee-note':'SYNTHETIC explicit evaluation $30 / activation $40 overrides; not current provider prices.'}
    for field,value in fields.items():page.locator('#'+field).fill(value)
    page.locator('#prop-payout-assumption').fill('')
    page.locator('#prop-check').click();playwright.expect(page.locator('#prop-status')).to_contain_text('Describe when trader cash is received')
    playwright.expect(page.locator('#prop-run')).to_be_disabled()
    playwright.expect(page.locator('#prop-check-output [role=alert]')).to_contain_text('Describe when trader cash is received')
    playwright.expect(page.locator('#prop-payout-assumption')).to_be_focused()
    page.screenshot(path=str(tmp_path/'missing-assumption-rejected.png'),full_page=True)
    page.locator('#prop-payout-assumption').fill(fields['prop-payout-assumption'])
    outcomes={}
    cases=[('exact_100',{},'100.00','-100.00'),
           ('month_reset',{'prop-horizon-end':'2026-02-10'},'170.00','-170.00'),
           ('activation_expiry',{'prop-horizon-end':'2026-01-31','prop-payment-days':'8'},'60.00','-60.00'),
           ('pending_at_reset',{'prop-start-date':'2026-01-30','prop-horizon-end':'2026-02-05','prop-payment-days':'8'},'30.00','-30.00'),
           ('receipt_within_horizon',{'prop-start-date':'2026-01-05','prop-horizon-end':'2026-02-13','prop-payment-days':'0'},'170.00','1330.00')]
    for label,changes,fees,net in cases:
        if outcomes:
            page.get_by_role('link',name='Configure new analysis',exact=True).click()
            playwright.expect(page.locator('#prop-config')).to_be_visible()
            playwright.expect(page.locator('#prop-method')).to_have_value('budgeted_lifecycle')
        for field,value in changes.items():page.locator('#'+field).fill(value)
        with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as check:page.locator('#prop-check').click()
        assert check.value.status==200,check.value.text()
        assert check.value.json()['settings']['BUDGET_TIMEZONE']=='America/Chicago'
        if label=='exact_100':
            # A changed month-boundary timezone must invalidate the old check.
            playwright.expect(page.locator('#prop-run')).to_be_enabled()
            timezone.select_option('Asia/Singapore')
            playwright.expect(page.locator('#prop-run')).to_be_disabled()
            timezone.select_option('America/Chicago')
            page.locator('#prop-check').click()
            playwright.expect(page.locator('#prop-run')).to_be_enabled()
        (tmp_path/(label+'-check.json')).write_text(json.dumps(check.value.json(),indent=2))
        playwright.expect(page.locator('#prop-check-output')).to_contain_text('Both phase sources checked')
        page.screenshot(path=str(tmp_path/(label+'-checked.png')),full_page=True)
        with page.expect_request(lambda r:r.url.endswith('/api/prop-analyses') and r.method=='POST') as submitted:page.locator('#prop-run').click()
        request=submitted.value.post_data_json
        (tmp_path/(label+'-request.json')).write_text(json.dumps(request,indent=2))
        playwright.expect(page.locator('#prop-heading-title')).to_have_text('Budgeted cash ledger',timeout=30000)
        playwright.expect(page.locator('#prop-report')).to_be_visible()
        id=page.url.rsplit('/',1)[-1]
        report=page.request.get(portal['url']+f'/api/prop-analyses/{id}/downloads/report.json').json()
        c=report['calculations'];assert_conservation(c)
        assert c['cash_totals']['total_paid_fees']==fees and c['cash_totals']['net_cash_within_horizon']==net
        assert c['cash_totals']['paid_evaluation_fees'] in ('30.00','60.00','90.00')
        (tmp_path/(label+'-report.json')).write_text(json.dumps(report,indent=2))
        for name,kind in [('cash_ledger.csv','files'),('monthly_ledger.csv','files'),('cash_ledger.json','files'),('monthly_ledger.json','files'),('transition_trace.csv','files'),('pending_receipts.json','files'),('analysis.zip','downloads')]:
            response=page.request.get(portal['url']+f'/api/prop-analyses/{id}/{kind}/{name}');assert response.status==200
            (tmp_path/(label+'-'+name)).write_bytes(response.body())
        for text in ('Download cash ledger (CSV)','Download monthly ledger (CSV)'):
            playwright.expect(page.get_by_role('link',name=text,exact=True)).to_be_visible()
        page.screenshot(path=str(tmp_path/(label+'-report.png')),full_page=True)
        before=len(posts);page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible()
        assert len(posts)==before
        assert page.request.get(portal['url']+f'/api/prop-analyses/{id}/downloads/report.json').json()==report
        # Identical configuration reuses this durable result; no second calculation.
        response=page.request.post(portal['url']+'/api/prop-analyses',data=request)
        assert response.status==202 and response.json()['id']==id
        outcomes[label]=dict(analysis_id=id,url=f'/#backtests/prop/job/{id}',paid_fees=fees,net_cash=net)
    page.set_viewport_size(dict(width=390,height=900));page.screenshot(path=str(tmp_path/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    assert not any('/api/backtests' in p for p in posts)
    # Existing API reports may have another valid IANA zone. Copy it exactly,
    # rather than silently resetting the report's calendar-month boundaries.
    custom={**request,'settings':{**request['settings'],'BUDGET_TIMEZONE':'Australia/Sydney'}}
    response=page.request.post(portal['url']+'/api/prop-analyses',data=custom)
    assert response.status==202,response.text()
    from test_prop_analysis_api import wait
    with ResearchHTTPClient(base_url=portal['url']) as client:
        custom_id=response.json()['id'];assert wait(client,custom_id)['status']=='complete'
    page.goto(portal['url']+f'/#backtests/prop/new/{evaluation["id"]}/from/{custom_id}')
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    playwright.expect(timezone).to_have_value('Australia/Sydney')
    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as check:page.locator('#prop-check').click()
    assert check.value.status==200 and check.value.json()['settings']['BUDGET_TIMEZONE']=='Australia/Sydney'
    page.screenshot(path=str(tmp_path/'saved-custom-timezone.png'),full_page=True)
    page.goto(portal['url']+'/#backtests/prop/new/'+evaluation['id'])
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    page.locator('#prop-method').select_option('budgeted_lifecycle')
    playwright.expect(timezone).to_have_value('America/Chicago')
    page.screenshot(path=str(tmp_path/'timezone-dropdown-default.png'),full_page=True)
    # The routine path needs no manually authored timing descriptions or
    # advanced settings. Presets are explicit choices, not silent assumptions.
    playwright.expect(page.locator('#prop-advanced')).not_to_have_attribute('open','')
    page.locator('#prop-monthly-cap').fill('100')
    page.locator('#prop-eval-fee').fill('30');page.locator('#prop-activation').fill('40')
    page.locator('#prop-use-observed').click()
    playwright.expect(page.locator('#prop-start-date')).to_have_value('2026-01-05')
    playwright.expect(page.locator('#prop-horizon-end')).to_have_value('2026-02-20')
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-check-output [role=alert]')).to_contain_text('Choose a payout receipt modeling assumption')
    playwright.expect(page.locator('#prop-payout-preset')).to_be_focused()
    page.locator('#prop-payout-preset').select_option('30')
    page.locator('#prop-activation-preset').select_option('immediate7')
    playwright.expect(page.locator('#prop-payout-custom')).to_be_hidden()
    playwright.expect(page.locator('#prop-activation-custom')).to_be_hidden()
    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as check:page.locator('#prop-check').click()
    assert check.value.status==200,check.value.text()
    preset_settings=check.value.json()['settings']
    assert preset_settings['PAYOUT_RECEIPT_DAYS']=='30' and preset_settings['ACTIVATION_DEADLINE_DAYS']=='7'
    assert preset_settings['ACTIVATION_PAYMENT_DELAY_DAYS']=='0'
    assert 'Unverified modeling assumption' in preset_settings['PAYOUT_TIMING_ASSUMPTION']
    assert 'Unverified modeling assumption' in preset_settings['ACTIVATION_TIMING_ASSUMPTION']
    (tmp_path/'presets-check.json').write_text(json.dumps(check.value.json(),indent=2))
    page.set_viewport_size(dict(width=1440,height=1100))
    page.screenshot(path=str(tmp_path/'simplified-config-checked.png'),full_page=True)
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
    preset_id=page.url.rsplit('/',1)[-1]
    preset_report=page.request.get(portal['url']+f'/api/prop-analyses/{preset_id}/downloads/report.json').json()
    assert preset_report['settings']==preset_settings
    assert_conservation(preset_report['calculations'])
    (tmp_path/'presets-report.json').write_text(json.dumps(preset_report,indent=2))
    page.get_by_role('link',name='Configure new analysis',exact=True).click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    playwright.expect(page.locator('#prop-payout-preset')).to_have_value('custom')
    playwright.expect(page.locator('#prop-payout-assumption')).to_have_value(preset_settings['PAYOUT_TIMING_ASSUMPTION'])
    page.locator('#prop-check').click();playwright.expect(page.locator('#prop-run')).to_be_enabled()
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
    assert page.url.endswith('/'+preset_id)
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,evaluation_source=evaluation['id'],funded_source=funded['id'],
        outcomes=outcomes,presets_analysis_id=preset_id,custom_timezone_analysis_id=custom_id,temporary_server='Stopped by fixture cleanup; no persistent server.'),indent=2))

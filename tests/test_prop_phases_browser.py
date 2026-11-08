"""Retired method stays readable; configuration uses the normal budgeted flow."""
import json

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright
from test_prop_phases import save_source, save_vwap_source, phase_request, report_for


def test_phase_sources_configure_check_run_download_reopen(page,portal,tmp_path):
    # Existing API prepares real saved legacy reports, not mocked presentation
    # payloads. Creating them is no longer a selectable browser workflow.
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        a=save_source(client);b=save_source(client,green=2)
        recover=save_source(client,recovery=True);incompatible=save_source(client,days=1)
        vwap=save_vwap_source(client)
        reports={label:report_for(client,phase_request(source,funded)) for label,source,funded in
                 [('same',a,a),('different_parameters',a,b),('different_strategy',a,vwap),('recovering',recover,recover)]}
    source_originals={record['id']:(portal['app'].state.runs.root/record['id']/'report.json').read_bytes()
                      for record in (a,b,recover,incompatible,vwap)}
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    window_lookups=[]
    def configure_with_window_lookup(link):
        # Configure reads existing IS metadata; this is not an analysis launch.
        url=portal['url']+'/api/research-campaigns/source-window';before=len(posts)
        with page.expect_response(lambda response:response.url==url and response.request.method=='POST') as checked:
            link.click()
        response=checked.value
        assert response.status==200
        assert response.request.post_data_json=={'sources':[{'backtest_id':a['id'],'sizes':[1]}]}
        assert response.json()['is_window']=={'first_session':'2026-01-05','last_session':'2026-02-20'}
        assert posts[before:]==[url]
        window_lookups.append(dict(request=response.request.post_data_json,status=response.status,response=response.json()))
    page.goto(portal['url']+'/#backtests/report/'+a['id'])
    configure_with_window_lookup(page.locator('#report-prop-setup'))
    posts.clear()  # Subsequent saved report reads/reloads must make no POST.
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    methods=page.locator('#prop-method option').evaluate_all('(nodes)=>nodes.map(n=>({value:n.value,label:n.textContent}))')
    assert [m['value'] for m in methods]==['annualized','budgeted_lifecycle']
    playwright.expect(page.locator('#prop-method')).to_have_value('annualized')
    page.screenshot(path=str(tmp_path/'available-methods.png'),full_page=True)
    outcomes={};originals={}
    for label,report in reports.items():
        id=report['id'];c=report['calculations']
        if label=='recovering':
            assert c['outcome']=='account_breach' and c['trace'][0]['equity']==-3000
        else:
            expected={'same':13000,'different_parameters':7500,'different_strategy':0}[label]
            assert c['phase_metrics']['funded']['trader_payouts']==expected
            assert c['phase_metrics']['evaluation']['pass_date']=='2026-01-05'
            assert c['activation']['funded_start_session']=='2026-01-07'
        page.goto(portal['url']+f'/#backtests/prop/job/{id}')
        playwright.expect(page.locator('#prop-heading-title')).to_have_text('Dated phase lifecycle')
        playwright.expect(page.locator('#prop-report')).to_be_visible()
        for name,kind in [('report.json','downloads'),('transition_trace.csv','files'),('transition_trace.json','files'),('analysis.zip','downloads')]:
            response=page.request.get(portal['url']+f'/api/prop-analyses/{id}/{kind}/{name}')
            assert response.status==200
            originals[(id,kind,name)]=response.body()
            (tmp_path/(label+'-'+name)).write_bytes(response.body())
        page.screenshot(path=str(tmp_path/(label+'-report.png')),full_page=True)
        page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible()
        outcomes[label]=dict(analysis_id=id,source_id=report['source']['phase_sources']['funded']['backtest']['id'],url=f'/#backtests/prop/job/{id}')
    assert not posts

    # Copy a saved two-source report into the remaining fixed-size cash mode.
    legacy=reports['different_parameters']
    page.goto(portal['url']+f'/#backtests/prop/job/{legacy["id"]}')
    configure_with_window_lookup(page.get_by_role('link',name='Configure budgeted analysis',exact=True))
    posts.clear()  # Missing cash assumptions must not trigger a submission.
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    playwright.expect(page.locator('#prop-method')).to_have_value('budgeted_lifecycle')
    playwright.expect(page.locator('#prop-status')).to_contain_text('Set the monthly fee cap, dates and timing assumptions')
    playwright.expect(page.locator('#prop-funded-source')).to_have_value(b['id'])
    playwright.expect(page.locator('#prop-evaluation-micros')).to_have_value('10')
    playwright.expect(page.locator('#prop-funded-micros')).to_have_value('3')
    playwright.expect(page.locator('#prop-cash-fields')).to_be_visible()
    for field in ['prop-monthly-cap','prop-start-date','prop-horizon-end','prop-payout-preset','prop-activation-preset']:
        playwright.expect(page.locator('#'+field)).to_have_value('')
    assert json.loads(page.locator('#prop-overrides').input_value())['ANALYSIS_MODE']=='budgeted_lifecycle'
    page.screenshot(path=str(tmp_path/'legacy-copied-to-budgeted.png'),full_page=True)
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-check-output [role=alert]')).to_contain_text('Enter your monthly fee cap')
    playwright.expect(page.locator('#prop-run')).to_be_disabled()
    assert not posts  # No implicit cash assumptions or submissions on migration.

    for field,value in {'prop-monthly-cap':'100','prop-eval-fee':'30','prop-activation':'40',
                        'prop-start-date':'2026-01-05','prop-horizon-end':'2026-01-05'}.items():
        page.locator('#'+field).fill(value)
    page.locator('#prop-payout-preset').select_option('0')
    page.locator('#prop-activation-preset').select_option('immediate7')
    page.locator('#prop-funded-source').select_option(incompatible['id'])
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-status')).to_contain_text('Funded source incompatible')
    playwright.expect(page.locator('#prop-run')).to_be_disabled()
    page.locator('#prop-funded-source').select_option(b['id'])
    with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:
        page.locator('#prop-check').click()
    assert checked.value.status==200,checked.value.text()
    assert checked.value.json()['settings']['ANALYSIS_MODE']=='budgeted_lifecycle'
    (tmp_path/'budgeted-check.json').write_text(json.dumps(checked.value.json(),indent=2))
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    page.locator('#prop-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Budgeted cash ledger',timeout=30000)
    id=page.url.rsplit('/',1)[-1]
    report=page.request.get(portal['url']+f'/api/prop-analyses/{id}/downloads/report.json').json()
    totals=report['calculations']['cash_totals']
    # One observed day: $30 evaluation paid, $40 only reserved; activation
    # cannot happen before tomorrow, so receipts=0 and net cash=-$30.
    assert totals['paid_evaluation_fees']=='30.00'
    assert totals['paid_activation_fees']=='0.00'
    assert totals['received_trader_payouts']=='0.00'
    assert totals['net_cash_within_horizon']=='-30.00'
    assert totals['reserved_allowance']=='40.00'
    assert report['source']['phase_sources']['funded']['backtest']['id']==b['id']
    (tmp_path/'budgeted-report.json').write_text(json.dumps(report,indent=2))
    for name,kind in [('cash_ledger.csv','files'),('analysis.zip','downloads')]:
        response=page.request.get(portal['url']+f'/api/prop-analyses/{id}/{kind}/{name}')
        assert response.status==200
        (tmp_path/('budgeted-'+name)).write_bytes(response.body())
    page.screenshot(path=str(tmp_path/'budgeted-report.png'),full_page=True)
    before=len(posts);page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert len(posts)==before
    page.set_viewport_size(dict(width=390,height=900))
    configure_with_window_lookup(page.get_by_role('link',name='Configure new analysis',exact=True))
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    playwright.expect(page.locator('#prop-method')).to_have_value('budgeted_lifecycle')
    assert page.locator('#prop-method option').count()==2
    page.screenshot(path=str(tmp_path/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    for (old_id,kind,name),raw in originals.items():
        assert page.request.get(portal['url']+f'/api/prop-analyses/{old_id}/{kind}/{name}').body()==raw
    assert not any('/api/backtests' in p for p in posts)
    for source_id,raw in source_originals.items():
        assert (portal['app'].state.runs.root/source_id/'report.json').read_bytes()==raw
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,evaluation_source=a['id'],outcomes=outcomes,
        methods=methods,budgeted_analysis_id=id,expected_cash=totals,legacy_downloads_unchanged=len(originals),
        metadata_lookups=window_lookups,source_reports_unchanged=len(source_originals),
        temporary_server='Stopped by fixture cleanup; no persistent server.'),indent=2))

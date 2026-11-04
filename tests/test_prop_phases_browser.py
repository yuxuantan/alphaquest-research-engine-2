"""Actual product demonstration; fixture expectations stay in tests."""
import json
import time
from pathlib import Path

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright
from test_prop_phases import save_source, save_vwap_source


def test_phase_sources_configure_check_run_download_reopen(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        a=save_source(client);b=save_source(client,green=2)
        recover=save_source(client,recovery=True);incompatible=save_source(client,days=1)
        vwap=save_vwap_source(client)
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.goto(portal['url']+'/#backtests/report/'+a['id'])
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    page.locator('#prop-method').select_option('dated_lifecycle')
    page.locator('#prop-commission-mode').select_option('source')
    page.locator('#prop-evaluation-micros').fill('10');page.locator('#prop-funded-micros').fill('3')
    page.locator('#prop-funded-source').select_option(incompatible['id'])
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-status')).to_contain_text('Funded source incompatible')
    playwright.expect(page.locator('#prop-run')).to_be_disabled()
    page.screenshot(path=str(tmp_path/'01-incompatible-source.png'),full_page=True)
    outcomes={}
    for label,funded,expected in [('same',a,13000),('different_parameters',b,7500),('different_strategy',vwap,0)]:
        if label!='same':
            page.get_by_role('link',name='Configure new analysis',exact=True).click()
            playwright.expect(page.locator('#prop-config')).to_be_visible()
        page.locator('#prop-funded-source').select_option('' if funded['id']==a['id'] else funded['id'])
        with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as checked:page.locator('#prop-check').click()
        assert checked.value.status==200,checked.value.text()
        check=checked.value.json();assert check['settings']['EVALUATION_MICROS']=='10' and check['settings']['FUNDED_MICROS']=='3'
        (tmp_path/(label+'-check.json')).write_text(json.dumps(check,indent=2))
        playwright.expect(page.locator('#prop-check-output')).to_contain_text('Both phase sources checked')
        page.screenshot(path=str(tmp_path/(label+'-source-check.png')),full_page=True)
        page.locator('#prop-run').click()
        playwright.expect(page.locator('#prop-heading-title')).to_have_text('Dated phase lifecycle',timeout=30000)
        playwright.expect(page.locator('#prop-report')).to_be_visible()
        id=page.url.rsplit('/',1)[-1]
        report=page.request.get(portal['url']+f'/api/prop-analyses/{id}/downloads/report.json').json()
        c=report['calculations']
        assert c['phase_metrics']['funded']['trader_payouts']==expected
        assert c['phase_metrics']['evaluation']['pass_date']=='2026-01-05'
        assert c['activation']['funded_start_session']=='2026-01-07'
        assert c['trace'][2]['source_trade_ids']==[3]
        assert c['trace'][2]['source_id']==funded['id']
        (tmp_path/(label+'-report.json')).write_text(json.dumps(report,indent=2))
        for name,kind in [('transition_trace.csv','files'),('transition_trace.json','files'),('analysis.zip','downloads')]:
            raw=page.request.get(portal['url']+f'/api/prop-analyses/{id}/{kind}/{name}');assert raw.status==200
            (tmp_path/(label+'-'+name)).write_bytes(raw.body())
        page.screenshot(path=str(tmp_path/(label+'-report.png')),full_page=True)
        before=len(posts);page.reload();playwright.expect(page.locator('#prop-report')).to_be_visible()
        assert len(posts)==before
        assert page.request.get(portal['url']+f'/api/prop-analyses/{id}/downloads/report.json').json()==report
        outcomes[label]=dict(analysis_id=id,source_id=funded['id'],payouts=expected,url=f'/#backtests/prop/job/{id}')
    # Recovering source wins $3000 per source trade, but first observed opening
    # gap crosses -$2000 at evaluation 10 MNQ, before its positive close.
    page.goto(portal['url']+'/#backtests/report/'+recover['id']);page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    page.locator('#prop-method').select_option('dated_lifecycle');page.locator('#prop-commission-mode').select_option('source')
    page.locator('#prop-check').click();playwright.expect(page.locator('#prop-run')).to_be_enabled()
    page.locator('#prop-run').click();playwright.expect(page.locator('#prop-heading-title')).to_have_text('Dated phase lifecycle')
    id=page.url.rsplit('/',1)[-1];report=page.request.get(portal['url']+f'/api/prop-analyses/{id}/downloads/report.json').json()
    assert report['calculations']['outcome']=='account_breach' and report['calculations']['trace'][0]['equity']==-3000
    (tmp_path/'recovering-report.json').write_text(json.dumps(report,indent=2));page.screenshot(path=str(tmp_path/'recovering-breach.png'),full_page=True)
    outcomes['recovering']=dict(analysis_id=id,source_id=recover['id'],url=f'/#backtests/prop/job/{id}')
    page.set_viewport_size(dict(width=390,height=900));page.screenshot(path=str(tmp_path/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    assert not any('/api/backtests' in p for p in posts)
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,evaluation_source=a['id'],outcomes=outcomes,
        fixed_sizes=[10,3],incompatible_source=incompatible['id'],temporary_server='stopped by fixture cleanup'),indent=2))

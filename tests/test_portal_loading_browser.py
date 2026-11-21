"""Shared loading feedback through normal portal routes; no calculation jobs."""
import os
from pathlib import Path
import re
import shutil
import pytest
from test_backtests_browser import browser,page,playwright,portal


@pytest.fixture
def pause(page):
    gates=[]
    def hold(pattern):
        state={'open':False,'routes':[]};gates.append(state)
        def handler(route):
            if state['open']:route.continue_()
            else:state['routes'].append(route)
        page.route(re.compile(pattern),handler)
        def release(status=None,body=None):
            state['open']=True
            for route in state['routes']:
                try:
                    if status is None:route.continue_()
                    else:route.fulfill(status=status,json=body)
                except playwright.Error:pass  # Navigation can abort an old read.
            state['routes'].clear()
        state['release']=release
        return release
    yield hold
    for state in gates:state['release']()


@pytest.fixture
def evidence(tmp_path,request):
    yield tmp_path
    if folder:=os.environ.get('ALPHAQUEST_LOADING_EVIDENCE_DIR'):
        target=Path(folder)/request.node.name;target.mkdir(parents=True,exist_ok=True)
        for source in tmp_path.glob('*.png'):shutil.copyfile(source,target/source.name)


@pytest.mark.parametrize('route,api,host',[
    ('#datasets',r'/api/datasets$','#library-status'),
    ('#campaigns',r'/api/strategies/library$','#workflow-campaign-detail'),
    ('#jobs',r'/api/jobs(?:\?|$)','#jobs-list-status'),
    ('#backtests/new',r'/api/strategies$','#backtest-options-status'),
    ('#prop-sim',r'/api/prop-sim/candidates$','#prop-sim-source-loading'),
],ids=['datasets','campaigns','jobs','backtest-choices','prop-configurations'])
def test_section_loading_is_visible_and_clears_after_real_read(page,portal,pause,evidence,route,api,host):
    release=pause(api);page.goto(portal['url']+'/'+route,wait_until='domcontentloaded')
    section=page.locator(host)
    spinner=section if host!='#workflow-campaign-detail' else section.locator('.portal-loading')
    playwright.expect(spinner).to_be_visible(timeout=10000)
    playwright.expect(spinner).to_have_attribute('aria-busy','true')
    assert spinner.evaluate("el=>getComputedStyle(el,'::before').animationName")=='portal-spin'
    playwright.expect(page.get_by_role('navigation',name='Main navigation',exact=True)).to_be_visible()
    if route=='#prop-sim':
        page.locator('#prop-sim-profile').select_option('lucidflex-50k')
        playwright.expect(page.locator('#prop-sim-profile')).to_have_value('lucidflex-50k')
    page.locator('main').screenshot(path=str(evidence/'loading.png'))
    release()
    playwright.expect(section).not_to_have_attribute('aria-busy','true',timeout=15000)
    if route=='#campaigns':playwright.expect(section.locator('.portal-loading')).to_have_count(0)
    else:playwright.expect(section).not_to_have_class(re.compile('portal-loading'))
    playwright.expect(page.locator('#portal-network-loading')).to_be_hidden(timeout=10000)
    page.locator('main').screenshot(path=str(evidence/'loaded.png'))


def test_failed_section_read_stops_spinner_and_retry_keeps_configuration(page,portal,pause):
    release=pause(r'/api/prop-sim/candidates$')
    page.goto(portal['url']+'/#prop-sim')
    status=page.locator('#prop-sim-source-loading')
    playwright.expect(status).to_have_class(re.compile('portal-loading'))
    page.locator('#prop-sim-workers').select_option('2')
    release(503,{'detail':'SYNTHETIC temporary read failure'})
    playwright.expect(status).to_contain_text('temporary read failure')
    playwright.expect(status).not_to_have_class(re.compile('portal-loading'))
    playwright.expect(status).not_to_have_attribute('aria-busy','true')
    page.get_by_role('button',name='Retry loading configurations',exact=True).click()
    playwright.expect(page.locator('#prop-sim-source')).to_be_enabled(timeout=15000)
    playwright.expect(page.locator('#prop-sim-workers')).to_have_value('2')
    playwright.expect(status).not_to_have_class(re.compile('portal-loading'))


def test_phase_error_clears_loading_and_navigation_stays_available(page,portal,pause):
    id='a'*32;release=pause('/api/campaign-workflows/'+id+'$')
    page.goto(portal['url']+'/#campaigns/workflows/'+id+'/mechanic_validation')
    status=page.locator('#mechanic-status')
    playwright.expect(status).to_have_class(re.compile('portal-loading'))
    release(404,{'detail':'SYNTHETIC workflow not found'})
    playwright.expect(status).to_contain_text('workflow not found')
    playwright.expect(status).not_to_have_class(re.compile('portal-loading'))
    page.get_by_role('navigation',name='Main navigation',exact=True).get_by_role('link',name='Research',exact=True).click()
    playwright.expect(page.locator('#research-screen')).to_be_visible()
    playwright.expect(page.locator('#portal-network-loading')).to_be_hidden()


def test_newer_loading_state_survives_old_completion_and_restores_accessibility(page,portal):
    page.goto(portal['url']+'/#datasets')
    playwright.expect(page.locator('#library-status')).not_to_have_class(re.compile('portal-loading'))
    result=page.evaluate('''()=>{
      const target=document.getElementById('library-status');
      const old=portalLoading.begin(target),recent=portalLoading.begin(target);old();
      const stillBusy=target.getAttribute('aria-busy');recent();
      const after=target.getAttribute('aria-busy');
      const region=document.getElementById('workflow-campaign-detail');
      const first=portalLoading.region(region),second=portalLoading.region(region);first();
      const regionBusy=region.getAttribute('aria-busy');second();
      return {stillBusy,after,regionBusy,regionAfter:region.getAttribute('aria-busy')};
    }''')
    assert result==dict(stillBusy='true',after=None,regionBusy='true',regionAfter=None)


def test_reduced_motion_mobile_and_late_request_from_previous_page(page,portal,pause,evidence):
    page.emulate_media(reduced_motion='reduce');page.set_viewport_size(dict(width=390,height=844))
    release=pause(r'/api/prop-sim/candidates$');page.goto(portal['url']+'/#prop-sim')
    status=page.locator('#prop-sim-source-loading')
    playwright.expect(status).to_have_class(re.compile('portal-loading'))
    assert status.evaluate("el=>getComputedStyle(el,'::before').animationName")=='none'
    assert page.locator('body').evaluate('el=>el.scrollWidth<=window.innerWidth+1')
    page.screenshot(path=str(evidence/'mobile-reduced-motion.png'),full_page=True)
    page.get_by_role('navigation',name='Mobile navigation',exact=True).get_by_role('link',name='Research',exact=True).click()
    playwright.expect(page.locator('#research-screen')).to_be_visible()
    playwright.expect(page.locator('#portal-network-loading')).to_be_hidden()
    release()
    playwright.expect(page.locator('#research-screen .portal-loading')).to_have_count(0)


def test_slow_secondary_request_gets_header_feedback_and_clears_on_failure(page,portal,pause):
    page.goto(portal['url']+'/#datasets')
    playwright.expect(page.locator('#library-status')).not_to_have_class(re.compile('portal-loading'))
    release=pause('/api/loading-feedback-test$')
    page.evaluate("()=>{window.loadingProbe=portalLoading.fetch('/api/loading-feedback-test').then(r=>r.status)}")
    playwright.expect(page.locator('#portal-network-loading')).to_be_visible(timeout=5000)
    page.set_viewport_size(dict(width=390,height=844))
    assert page.locator('body').evaluate('el=>el.scrollWidth<=window.innerWidth+1')
    release(503,{'detail':'SYNTHETIC display-only failure'})
    playwright.expect(page.locator('#portal-network-loading')).to_be_hidden(timeout=5000)
    assert page.evaluate('window.loadingProbe')==503


def test_report_timing_section_loads_independently_of_completed_core_report(page,portal,pause,evidence):
    from research_fixtures import ResearchHTTPClient
    from test_backtest_api import body
    with ResearchHTTPClient(base_url=portal['url'],timeout=120) as client:
        response=client.post('/api/backtests',json=dict(body(portal['saved']['arithmetic_5m']['id']),report_detail='full'))
        assert response.status_code==201,response.text
        record=response.json()
    release=pause('/api/backtests/'+record['id']+'/performance$')
    page.goto(portal['url']+'/#backtests/report/'+record['id'])
    playwright.expect(page.locator('#backtest-completion')).to_be_visible(timeout=15000)
    page.locator('#report-performance > summary').click()
    status=page.locator('#report-performance-status')
    playwright.expect(status).to_have_class(re.compile('portal-loading'))
    playwright.expect(status).to_be_visible()
    # The core report and trades are usable while only timing evidence waits.
    playwright.expect(page.locator('#report-trades-count')).not_to_have_class(re.compile('portal-loading'))
    page.locator('#report-performance').screenshot(path=str(evidence/'independent-report-section.png'))
    release()
    playwright.expect(status).not_to_have_class(re.compile('portal-loading'),timeout=10000)
    playwright.expect(status).to_contain_text('Total elapsed')


def test_refreshing_unchanged_jobs_restores_status_after_loading(page,portal,pause):
    page.goto(portal['url']+'/#jobs')
    status=page.locator('#jobs-list-status')
    playwright.expect(status).to_contain_text('No jobs match')
    before=status.text_content();release=pause(r'/api/jobs(?:\?|$)')
    page.get_by_role('button',name='Refresh',exact=True).click()
    playwright.expect(status).to_have_class(re.compile('portal-loading'))
    release()
    playwright.expect(status).not_to_have_class(re.compile('portal-loading'))
    playwright.expect(status).to_have_text(before)

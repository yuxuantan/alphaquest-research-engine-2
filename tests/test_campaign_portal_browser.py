"""Portal charts, filters, frozen manual OOS and honest incomplete/error states."""
import json
from hashlib import sha256
from threading import Event
from uuid import uuid4

import pytest
from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright
from test_campaign_assessments import saved_is
from test_research_campaigns import create, declaration, run
from test_prop_analysis_api import wait
from test_prop_phases import save_source


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_campaign_portal_frozen_oos_and_charts(page,portal,tmp_path,phase):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        a=saved_is(client);b=saved_is(client,2)
    page.goto(portal['url']+'/#backtests/report/'+a['id'])
    page.locator('#report-prop-setup').click()
    page.locator('#campaign-new-'+phase).click()
    page.locator('#campaign-paths').fill('8');page.locator('#campaign-block').select_option('1')
    if phase=='evaluation':
        page.locator('#campaign-chains').fill('8');page.locator('.campaign-sizes').fill('3,10')
    else:
        page.locator('#campaign-horizon').fill('14');page.locator('#campaign-delay').fill('4')
    page.locator('#campaign-add-source').click()
    page.locator('.campaign-source-search').nth(1).fill(b['id'])
    playwright.expect(page.locator('.campaign-source-status').nth(1)).to_contain_text('1 of 1')
    page.locator('.campaign-reference').nth(1).select_option(b['id'])
    if phase=='evaluation':page.locator('.campaign-sizes').nth(1).fill('3,10')
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign',timeout=30000)
    id=page.url.rsplit('/',1)[-1];prefix=f'/api/research-campaigns/{id}'
    report=page.request.get(portal['url']+prefix+'/exports/results.json').json()
    playwright.expect(page.locator('#campaign-candidates tbody tr')).to_have_count(4)
    if phase=='evaluation':
        assert report['winner'] is None
        circles=page.locator('#campaign-chart circle')
        assert set(circles.evaluate_all('(nodes)=>nodes.map(n=>n.dataset.candidateId)'))=={r['candidate_id'] for r in report['candidates']}
        assert set(page.locator('#campaign-chart circle[data-frontier="true"]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.candidateId)'))==set(report['frontier'])
        selected=report['frontier']
        page.locator('#campaign-filter-size').select_option('3')
        playwright.expect(page.locator('#campaign-candidates tbody tr')).to_have_count(2)
        assert page.locator('#campaign-chart circle').count()==2
    else:
        selected=[r['candidate_id'] for r in report['candidates'] if r['manifest']['configuration']['source']['source_backtest_id']==a['id']]
        assert sum(map(int,page.locator('#campaign-chart rect').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.count)')))==8
        page.locator('#campaign-filter-size').select_option('1')
        playwright.expect(page.locator('#campaign-candidates tbody tr')).to_have_count(2)
    page.screenshot(path=str(tmp_path/'filtered-results.png'),full_page=True)
    page.locator('#campaign-filter-size').select_option('')
    for i,candidate in enumerate(selected):
        box=page.locator(f'.campaign-pick[value="{candidate}"]');box.check()
        box.locator('..').locator('.campaign-candidate-name').fill(f'{phase} frozen choice {i+1}')
    page.locator('#campaign-rationale').fill('Predeclared IS family; OOS cannot rerank it.')
    page.locator('#campaign-freeze').click()
    playwright.expect(page.get_by_role('heading',name='Frozen IS selection')).to_be_visible()
    snapshot=page.request.get(portal['url']+prefix+'/exports/frozen_package.json').body()
    is_bytes=page.request.get(portal['url']+prefix+'/exports/results.json').body()
    page.locator('#campaign-launch-oos').click()
    playwright.expect(page.locator('#campaign-assessments').get_by_role('link',name='Open frozen OOS assessment')).to_be_visible(timeout=60000)
    history=page.request.get(portal['url']+prefix+'/assessments').json()['items']
    assert len(history)==1 and history[0]['status']=='complete'
    assessment_id=history[0]['analysis_id']
    page.locator('#campaign-assessments').get_by_role('link',name='Open frozen OOS assessment').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Frozen OOS assessment')
    assert page.locator('#campaign-freeze').count()==0
    assert set(page.locator('.campaign-candidate-name').evaluate_all('(nodes)=>nodes.map(n=>n.value)'))=={f'{phase} frozen choice {i+1}' for i in range(len(selected))}
    oos=page.request.get(portal['url']+f'/api/prop-analyses/{assessment_id}/downloads/report.json').json()
    assert oos['calculations']['winner'] is None
    assert oos['calculations'].get('ranking',oos['calculations'].get('frontier'))==[]
    assert {r['manifest']['configuration']['micros'] for r in oos['calculations']['candidates']}==({10} if phase=='evaluation' else {1,3})
    assert [r['metrics']['cost_per_funded'] for r in oos['calculations']['candidates']]==[70] if phase=='evaluation' else sorted(r['metrics']['expected_payouts'] for r in oos['calculations']['candidates'])==[0,1500]
    page.screenshot(path=str(tmp_path/'frozen-oos-assessment.png'),full_page=True)
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#prop-heading-title')).to_have_text('Frozen OOS assessment')
    page.goto(portal['url']+'/#backtests/prop/campaign/'+id)
    playwright.expect(page.get_by_role('heading',name='Frozen IS selection')).to_be_visible()
    assert not posts
    assert page.request.get(portal['url']+prefix+'/exports/frozen_package.json').body()==snapshot
    assert page.request.get(portal['url']+prefix+'/exports/results.json').body()==is_bytes
    for kind in ['campaign.json','results.csv','results.json','analysis.zip','frozen_package.json']:
        response=page.request.get(portal['url']+prefix+'/exports/'+kind);assert response.ok
        (tmp_path/kind).write_bytes(response.body())
    for kind in ['report.json','analysis.zip']:
        response=page.request.get(portal['url']+f'/api/prop-analyses/{assessment_id}/downloads/'+kind);assert response.ok
        (tmp_path/('oos-'+kind)).write_bytes(response.body())
    (tmp_path/'portal-evidence.json').write_text(json.dumps(dict(phase=phase,campaign_id=id,source_ids=[a['id'],b['id']],assessment_id=assessment_id,
        expected_is_costs=[70]*4 if phase=='evaluation' else None,expected_is_calendar_days=[2,4,7,15] if phase=='evaluation' else None,
        expected_oos_cash=[0,1500] if phase=='funded' else None,freeze_sha256=sha256(snapshot).hexdigest(),reopen_posts=posts,server='Stopped by portal fixture.'),indent=2))


def test_campaign_censored_error_and_progress_states(page,portal,tmp_path,monkeypatch):
    from alphaquest.prop import funded_optimization
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        source=save_source(client,recovery=True,days=8)
        body=declaration(source);body['sources'][0]['sizes']=[10]
        campaign=run(client,create(client,body)['campaign_id'])
        page.goto(portal['url']+'/#backtests/prop/campaign/'+campaign['campaign_id'])
        playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign')
        playwright.expect(page.locator('#campaign-chart')).to_contain_text('No resolved cost/time points')
        assert not page.locator('.campaign-pick').is_enabled()
        playwright.expect(page.locator('#campaign-candidates')).to_contain_text('unresolved')
        page.screenshot(path=str(tmp_path/'censored-campaign.png'),full_page=True)
        request=declaration(source,phase='funded');c=create(client,request);id=c['campaign_id']
        original=funded_optimization.optimize_funded
        def fail(*args,**kwargs):raise RuntimeError('Deliberate test worker failure')
        monkeypatch.setattr(funded_optimization,'optimize_funded',fail)
        response=client.post(f'/api/research-campaigns/{id}/run');assert response.status_code==202
        assert wait(client,response.json()['analysis_id'])['status']=='error'
        page.goto(portal['url']+'/#backtests/prop/campaign/'+id)
        playwright.expect(page.locator('#prop-report-content')).to_contain_text('Deliberate test worker failure')
        page.screenshot(path=str(tmp_path/'failed-campaign.png'),full_page=True)
        entered,release=Event(),Event()
        def pause(*args,**kwargs):
            kwargs_progress=args[3];kwargs_progress('Completed 0 / 2 candidates · checking progress display')
            entered.set();assert release.wait(30)
            return original(*args,**kwargs)
        monkeypatch.setattr(funded_optimization,'optimize_funded',pause)
        try:
            page.locator('#campaign-resume').click();assert entered.wait(5)
            playwright.expect(page.locator('#prop-status')).to_contain_text('Completed 0 / 2 candidates')
            page.screenshot(path=str(tmp_path/'running-campaign.png'),full_page=True)
        finally:release.set()
        playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign',timeout=30000)
        playwright.expect(page.locator('#prop-status')).to_contain_text('2 / 2 completed candidates')
        assert len(client.get(f'/api/research-campaigns/{id}/attempts').json()['items'])==2


def test_pareto_plot_table_and_marginal_match_saved_report(page,portal,tmp_path):
    from test_evaluation_optimization import request_for
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        a=save_source(client,days=8);b=save_source(client,green=2,days=8)
        request=request_for(a,b)
        checked=client.post('/api/prop-analyses/check',json=request);assert checked.status_code==200
        response=client.post('/api/prop-analyses',json=request);assert response.status_code==202
        id=response.json()['id'];assert wait(client,id)['status']=='complete'
        report=client.get(f'/api/prop-analyses/{id}/downloads/report.json').json()
    page.goto(portal['url']+'/#backtests/prop/job/'+id)
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Independent phase analysis')
    calc=report['calculations']
    assert sorted((r['metrics']['cost_per_funded'],r['metrics']['expected_calendar_days_to_funded']) for r in calc['candidates'])==[(70,4),(90,9),(100,3),(140,2)]
    assert len(calc['frontier'])==3
    assert set(page.locator('#campaign-chart circle[data-frontier="true"]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.candidateId)'))==set(calc['frontier'])
    assert page.locator('#campaign-marginal tbody tr').count()==2
    assert page.locator('#campaign-marginal tbody tr').evaluate_all('(rows)=>rows.map(row=>row.lastElementChild.textContent)')==['30','40']
    assert page.locator('#campaign-candidates tbody tr').count()==4
    page.locator('#campaign-filter-profile').select_option('apex-50k-eod')
    page.locator('#campaign-filter-size').select_option('5')
    assert page.locator('#campaign-chart circle').count()==2
    assert page.locator('#campaign-chart circle[data-frontier="true"]').count()==1
    page.screenshot(path=str(tmp_path/'pareto-and-marginal.png'),full_page=True)
    page.set_viewport_size(dict(width=390,height=844));page.reload()
    playwright.expect(page.locator('#campaign-chart svg')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path/'mobile-pareto.png'),full_page=True)
    (tmp_path/'chart-verification.json').write_text(json.dumps(dict(report_id=id,expected_points=[[70,4],[90,9],[100,3],[140,2]],expected_marginal=[30,40]),indent=2))


def test_configuration_shows_chosen_local_account_rules(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        source=save_source(client,days=8)
    page.goto(portal['url']+'/#backtests/prop/new/'+source['id'])
    page.locator('#campaign-new-evaluation').click()
    playwright.expect(page.locator('#campaign-form')).to_contain_text('$3,000 profit target')
    playwright.expect(page.locator('#campaign-form')).to_contain_text('21-session expiry')
    page.locator('#campaign-phase').select_option('funded')
    playwright.expect(page.locator('#campaign-form')).to_contain_text('$2,100 safety net')
    page.locator('#campaign-profile').select_option('lucidflex-50k')
    playwright.expect(page.locator('#campaign-form')).to_contain_text('90% trader share')
    playwright.expect(page.locator('#campaign-form')).to_contain_text('no funded consistency requirement')
    playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    page.screenshot(path=str(tmp_path/'local-rules-before-check.png'),full_page=True)

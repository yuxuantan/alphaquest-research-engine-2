"""Actual backtest → prop campaign → check/run → durable selection/freeze."""
from prop_setup_helpers import open_prop_task
import json
from hashlib import sha256
from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright
from test_prop_phases import save_source


def test_campaign_configuration_results_freeze_download_reopen(page,portal,tmp_path,monkeypatch):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        a=save_source(client,days=8);b=save_source(client,green=2,days=8)
    def forbidden(*args,**kwargs):raise AssertionError('Unrelated companion/OOS exports must not be discovered')
    monkeypatch.setattr('alphaquest.prop_api.matching_exports',forbidden)
    page.goto(portal['url']+'/#backtests/report/'+a['id'])
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    open_prop_task(page, 'compare', close_outer=True)
    page.locator('#campaign-configure > summary').click()
    page.locator('#campaign-phase').select_option('funded')
    page.locator('#campaign-paths').fill('8')
    page.locator('#campaign-block').select_option('1')
    page.locator('#campaign-horizon').fill('14')
    page.locator('#campaign-delay').fill('4')
    page.locator('#campaign-breach').fill('0')
    page.locator('#campaign-add-source').click()
    playwright.expect(page.locator('.campaign-reference').first).to_have_value(a['id'])
    assert page.locator('.campaign-reference').nth(1).evaluate('(e)=>e.tagName')=='SELECT'
    page.locator('.campaign-kind').nth(1).select_option('optimization_id')
    playwright.expect(page.locator('.campaign-source-status').nth(1)).to_contain_text('No IS optimization jobs')
    assert page.locator('.campaign-reference').nth(1).evaluate('(e)=>e.validity.valueMissing')
    playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    page.screenshot(path=str(tmp_path/'empty-job-picker.png'),full_page=True)
    page.locator('.campaign-kind').nth(1).select_option('backtest_id')
    page.locator('.campaign-source-search').nth(1).fill(b['id'])
    playwright.expect(page.locator('.campaign-source-status').nth(1)).to_contain_text('1 of 1')
    page.locator('.campaign-reference').nth(1).select_option(b['id'])
    playwright.expect(page.locator('.campaign-source-info').nth(1)).to_contain_text('green_bar_count=2')
    page.locator('.campaign-source-search').nth(1).fill('no matching source')
    playwright.expect(page.locator('.campaign-source-status').nth(1)).to_contain_text('No matching sources')
    playwright.expect(page.locator('.campaign-reference').nth(1)).to_have_value(b['id'])
    page.locator('.campaign-source-search').nth(1).fill('')
    playwright.expect(page.locator('.campaign-source-status').nth(1)).to_contain_text('2 of 2')
    page.screenshot(path=str(tmp_path/'selected-backtest-dropdowns.png'),full_page=True)
    # The declared membership is counted automatically. A real 129-member
    # request crosses the 128-candidate confirmation threshold; declining
    # must not save or run a campaign. No retired manual budget is restored.
    playwright.expect(page.locator('#campaign-budget')).to_have_count(0)
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        c=save_source(client,contracts=2,days=8)
    page.locator('#campaign-add-source').click()
    page.locator('.campaign-source-search').nth(2).fill(c['id'])
    playwright.expect(page.locator('.campaign-source-status').nth(2)).to_contain_text('1 of 1')
    page.locator('.campaign-reference').nth(2).select_option(c['id'])
    for index in (0,1):page.locator('.campaign-sizes').nth(index).fill(','.join(map(str,range(1,61))))
    page.locator('.campaign-sizes').nth(2).fill(','.join(map(str,range(1,10))))
    confirmations=[]
    def decline(dialog):
        confirmations.append(dialog.message)
        dialog.dismiss()
    page.once('dialog',decline)
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-status')).to_contain_text('Cancelled: 129 candidates require confirmation. No campaign was saved.')
    assert len(confirmations)==1 and '128-candidate confirmation threshold' in confirmations[0]
    assert page.request.get(portal['url']+'/api/research-campaigns').json()['items']==[]
    playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    page.screenshot(path=str(tmp_path/'candidate-confirmation-declined.png'),full_page=True)
    page.locator('#campaign-sources > fieldset').nth(2).get_by_role('button',name='Remove source').click()
    for index in (0,1):page.locator('.campaign-sizes').nth(index).fill('1,3')
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    playwright.expect(page.locator('#campaign-status')).to_contain_text('4 compatible candidates')
    page.screenshot(path=str(tmp_path/'checked-campaign.png'),full_page=True)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign',timeout=30000)
    id=page.url.rsplit('/',1)[-1]
    saved=page.request.get(portal['url']+'/api/research-campaigns/'+id).json()
    result=page.request.get(portal['url']+f'/api/research-campaigns/{id}/exports/results.json').json()
    assert sorted(c['metrics']['expected_payouts'] for c in result['candidates'])==[0,0,0,1500]
    assert len(page.locator('.campaign-pick').all())==4
    page.locator(f'.campaign-pick[value="{result["winner"]}"]').check()
    page.locator('#campaign-rationale').fill('Synthetic monotone paths: only A at 3 MNQ receives $1500 within 14 days.')
    page.locator('#campaign-freeze').click()
    playwright.expect(page.get_by_role('heading',name='Frozen IS selection')).to_be_visible()
    page.screenshot(path=str(tmp_path/'frozen-campaign.png'),full_page=True)
    snapshots={}
    for kind in ('campaign.json','results.json','results.csv','source_checks.json','analysis.zip','frozen_package.json'):
        response=page.request.get(portal['url']+f'/api/research-campaigns/{id}/exports/{kind}')
        assert response.status==200
        snapshots[kind]=response.body()
        (tmp_path/kind).write_bytes(response.body())
    posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.reload()
    playwright.expect(page.get_by_role('heading',name='Frozen IS selection')).to_be_visible()
    assert not posts
    for kind,value in snapshots.items():
        assert page.request.get(portal['url']+f'/api/research-campaigns/{id}/exports/{kind}').body()==value
    # Normal saved phase report is also readable, not mistaken for legacy joint sizing.
    page.goto(portal['url']+'/#backtests/prop/job/'+saved['analysis_id'])
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Independent phase analysis')
    assert not posts
    (tmp_path/'browser-verification.json').write_text(json.dumps(dict(campaign_id=id,analysis_id=saved['analysis_id'],
        source_ids=[a['id'],b['id']],expected_cash=[0,0,0,1500],expected_pending_for_winner=1500,
        downloads={k:sha256(v).hexdigest() for k,v in snapshots.items()},reopen_posts=posts,
        temporary_server='Stopped by portal fixture cleanup.'),indent=2))

    # Independently configure Evaluation through the same product controls.
    page.goto(portal['url']+'/#backtests/prop/new/'+a['id'])
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    open_prop_task(page, 'compare', close_outer=True)
    page.locator('#campaign-configure > summary').click()
    page.locator('#campaign-paths').fill('8')
    page.locator('#campaign-chains').fill('8')
    page.locator('#campaign-block').select_option('1')
    page.locator('.campaign-sizes').fill('3,10')
    page.locator('#campaign-add-source').click()
    page.locator('.campaign-reference').nth(1).select_option(b['id'])
    page.locator('.campaign-sizes').nth(1).fill('3,10')
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign',timeout=30000)
    evaluation_id=page.url.rsplit('/',1)[-1]
    result=page.request.get(portal['url']+f'/api/research-campaigns/{evaluation_id}/exports/results.json').json()
    assert sorted(c['metrics']['expected_calendar_days_to_funded'] for c in result['candidates'])==[2,4,7,15]
    assert result['winner'] is None and len(result['frontier'])==1
    page.locator(f'.campaign-pick[value="{result["frontier"][0]}"]').check()
    page.locator('#campaign-rationale').fill('Freeze the fastest IS point at the common $70 acquisition cost.')
    page.locator('#campaign-freeze').click()
    playwright.expect(page.get_by_role('heading',name='Frozen IS selection')).to_be_visible()
    page.screenshot(path=str(tmp_path/'evaluation-frozen-campaign.png'),full_page=True)
    (tmp_path/'evaluation-browser-verification.json').write_text(json.dumps(dict(campaign_id=evaluation_id,
        expected_costs=[70]*4,expected_calendar_days=[2,4,7,15],frontier=result['frontier']),indent=2))
    # A binding risk constraint keeps the larger, higher-cash rows visible and
    # explicitly infeasible in the same saved phase report screen.
    from uuid import uuid4
    from test_prop_analysis_api import wait
    limited=json.loads(json.dumps(saved['declaration']))
    limited['campaign_id']=uuid4().hex
    limited['search_settings']['constraints']['maximum_position_size']=1
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        response=client.post('/api/research-campaigns',json=limited)
        assert response.status_code==201,response.text
        response=client.post(f'/api/research-campaigns/{limited["campaign_id"]}/run')
        assert response.status_code==202,response.text
        assert wait(client,response.json()['analysis_id'])['status']=='complete'
    page.goto(portal['url']+'/#backtests/prop/campaign/'+limited['campaign_id'])
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign')
    playwright.expect(page.get_by_text('infeasible',exact=True)).to_have_count(2)
    playwright.expect(page.get_by_text('Not ranked',exact=True)).to_have_count(2)
    page.screenshot(path=str(tmp_path/'risk-constraint-campaign.png'),full_page=True)
    (tmp_path/'constraint-browser-verification.json').write_text(json.dumps(dict(campaign_id=limited['campaign_id'],
        constraint=limited['search_settings']['constraints'],infeasible_candidates=2),indent=2))



def test_campaign_optimization_job_dropdown(page,portal,tmp_path):
    from test_research_campaigns import make_jobs
    from test_prop_analysis_api import wait
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        trials,jobs=make_jobs(client)
    page.goto(portal['url']+'/#backtests/prop/new/'+trials[0]['id'])
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    open_prop_task(page, 'compare', close_outer=True)
    page.locator('#campaign-configure > summary').click()
    page.locator('#campaign-phase').select_option('funded')
    page.locator('#campaign-paths').fill('8')
    page.locator('#campaign-block').select_option('1')
    page.locator('#campaign-horizon').fill('14')
    page.locator('#campaign-delay').fill('4')
    page.locator('#campaign-add-source').click()
    for i,job in enumerate(jobs):
        page.locator('.campaign-kind').nth(i).select_option('optimization_id')
        page.locator('.campaign-source-search').nth(i).fill(job)
        playwright.expect(page.locator('.campaign-source-status').nth(i)).to_contain_text('1 of 1')
        page.locator('.campaign-reference').nth(i).select_option(job)
        playwright.expect(page.locator('.campaign-source-info').nth(i).locator('a')).to_have_attribute('href','#backtests/batches/'+job)
    page.screenshot(path=str(tmp_path/'selected-optimization-dropdowns.png'),full_page=True)
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    playwright.expect(page.locator('#campaign-status')).to_contain_text('4 compatible candidates')
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign',timeout=30000)
    id=page.url.rsplit('/',1)[-1]
    report=page.request.get(portal['url']+f'/api/research-campaigns/{id}/exports/results.json').json()
    assert len(report['candidates'])==4
    assert {r['manifest']['strategy']['id'] for r in report['candidates']}=={'vwap_pullback_risk_sizing','consecutive_green_hold'}
    assert {o['optimization_id'] for r in report['candidates'] for o in r['origin_trials']}==set(jobs)
    assert [r['metrics']['expected_payouts'] for r in report['candidates']]==[0]*4
    for name in ('campaign.json','results.json','results.csv','analysis.zip'):
        response=page.request.get(portal['url']+f'/api/research-campaigns/{id}/exports/{name}')
        assert response.status==200
        (tmp_path/name).write_bytes(response.body())
    (tmp_path/'dropdown-job-verification.json').write_text(json.dumps(dict(campaign_id=id,job_ids=jobs,
        full_candidate_count=4,expected_cash=[0]*4,source_backtest_ids=[t['id'] for t in trials]),indent=2))

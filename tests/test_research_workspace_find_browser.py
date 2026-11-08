"""Find and understand saved work through the normal Research product page."""
from prop_setup_helpers import open_prop_task
from hashlib import sha256
import io
import json
import zipfile

import httpx
from test_backtests_browser import browser,page,playwright
from test_research_procedure_browser import portal
from test_robust_research_api import save_grid


def test_find_campaign_by_activity_backtest_and_link_then_review(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        dataset,job,records=save_grid(client)
    # Normal report -> configure -> source check -> phase run, using the whole grid.
    page.goto(portal['url']+'/#backtests/report/'+records[0]['id'])
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'compare', close_outer=True)
    page.locator('#campaign-configure > summary').click()
    page.locator('#campaign-phase').select_option('funded')
    page.locator('.campaign-kind').select_option('optimization_id')
    playwright.expect(page.locator('.campaign-reference option[value="'+job['id']+'"]')).to_have_count(1)
    page.locator('.campaign-reference').select_option(job['id'])
    page.locator('#campaign-paths').fill('8');page.locator('#campaign-block').select_option('1')
    page.locator('#campaign-horizon').fill('14');page.locator('#campaign-delay').fill('4')
    page.locator('#campaign-breach').fill('0');page.locator('.campaign-sizes').fill('1,3')
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#campaign-delete')).to_be_enabled(timeout=120000)
    cid=page.url.rsplit('/',1)[-1]
    campaign=page.request.get(portal['url']+'/api/research-campaigns/'+cid).json()
    aid=campaign['analysis_id'];downloads={}
    for name,path in [('report.json',f'/api/prop-analyses/{aid}/downloads/report.json'),
                      ('analysis.zip',f'/api/prop-analyses/{aid}/downloads/analysis.zip'),
                      ('SYNTHETIC-history.csv',f'/api/datasets/{dataset["id"]}/csv')]:
        response=page.request.get(portal['url']+path);assert response.ok,response.text()
        raw=response.body();(tmp_path/name).write_bytes(raw);downloads[name]=sha256(raw).hexdigest()
    result=json.loads((tmp_path/'report.json').read_bytes())
    cash=sorted(row['metrics']['expected_payouts'] for row in result['calculations']['candidates'])
    assert cash==[0,0,0,1500]
    with zipfile.ZipFile(io.BytesIO((tmp_path/'analysis.zip').read_bytes())) as archive:assert archive.testzip() is None
    writes=[];source_requests=[]
    page.on('request',lambda r:writes.append([r.method,r.url]) if r.method in ('POST','PUT','DELETE') else None)
    page.on('request',lambda r:source_requests.append(r.url) if '/api/research-campaigns/sources?' in r.url else None)
    page.goto(portal['url']+'/#backtests/research')
    playwright.expect(page.locator('#workspace-items article')).to_have_count(1)
    playwright.expect(page.get_by_role('heading',name='Research',exact=True)).to_be_visible()
    playwright.expect(page.locator('#workspace-query')).to_be_visible()
    playwright.expect(page.locator('#workspace-new')).to_be_hidden()
    playwright.expect(page.locator('#workspace-phase')).to_be_hidden()
    assert not source_requests
    page.locator('#workspace-help > summary').click()
    playwright.expect(page.locator('#workspace-help')).to_contain_text('saved research library')
    page.locator('#workspace-help > summary').click()
    card=page.locator('#workspace-items article')
    playwright.expect(card).to_contain_text(cid)
    playwright.expect(card).to_contain_text('Consecutive Green Hold')
    playwright.expect(card).to_contain_text('Linked backtests: 2 · Activities: 1')
    page.screenshot(path=str(tmp_path/'research-desktop.png'),full_page=True)
    # Search any linked source, including the non-representative one, plus IDs/links.
    found=[]
    for query in [job['id'],*[r['id'] for r in records],portal['url']+'/#backtests/prop/campaign/'+cid,'consecutive green hold']:
        with page.expect_response(lambda r:'/api/research-workspace?' in r.url):
            page.locator('#workspace-query').fill(query)
        playwright.expect(page.locator('#workspace-status')).to_contain_text('Showing 1 of 1')
        playwright.expect(card).to_have_attribute('data-id',cid)
        found.append(query)
    card.get_by_role('link',name='Manage campaign',exact=True).click()
    playwright.expect(page.locator('#campaign-delete')).to_be_enabled()
    assert not writes
    page.goto(portal['url']+'/#backtests/research')
    page.get_by_role('link',name='View results',exact=True).click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Independent phase analysis')
    assert page.request.get(portal['url']+f'/api/prop-analyses/{aid}/downloads/report.json').body()==(tmp_path/'report.json').read_bytes()
    page.goto(portal['url']+'/#backtests/research')
    page.locator('#workspace-show-phase').click()
    page.locator('#workspace-filters > summary').click()
    page.locator('#workspace-phase').select_option('evaluation')
    playwright.expect(page.locator('#workspace-items')).to_contain_text('No matching saved work')
    playwright.expect(page.locator('#workspace-active-filters')).to_contain_text('Evaluation')
    page.locator('#workspace-clear').click()
    playwright.expect(page.locator('#workspace-items article')).to_have_count(1)
    playwright.expect(page.locator('#workspace-phase')).to_be_hidden()
    # A failed metadata read is recoverable without a run or lost library.
    page.route('**/api/research-workspace?*',lambda route:route.fulfill(status=503,json=dict(detail='Temporary test outage')))
    page.locator('#workspace-refresh').click()
    playwright.expect(page.locator('#workspace-status')).to_contain_text('Use Refresh to try again')
    page.unroute('**/api/research-workspace?*');page.locator('#workspace-refresh').click()
    playwright.expect(page.locator('#workspace-items article')).to_have_count(1)
    page.set_viewport_size(dict(width=390,height=844))
    page.screenshot(path=str(tmp_path/'research-narrow.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
    page.locator('#workspace-start').click()
    playwright.expect(page.locator('#workspace-source-configure')).to_be_enabled()
    assert source_requests
    page.locator('#workspace-source').select_option(records[0]['id'])
    page.locator('#workspace-source-configure').click()
    playwright.expect(page.locator('#report-prop-setup')).to_be_visible()
    assert not writes
    (tmp_path/'evidence.json').write_text(json.dumps(dict(synthetic=True,campaign_id=cid,activity_id=job['id'],
        source_ids=[r['id'] for r in records],analysis_id=aid,expected_cash=cash,found_queries=found,
        downloads=downloads,browsing_writes=writes,temporary_server='Stopped and joined by portal fixture.'),indent=2)+'\n')

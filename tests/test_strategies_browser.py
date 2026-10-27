"""Real instrument -> saved backtest -> durable report navigation."""
import json,re,time
from test_backtests_browser import browser,page,portal,playwright,FIXTURES
from test_backtest_api import body
from test_optimization import optimization_body


def seed(page,portal,symbol='MNQ'):
    response=page.request.post(portal['url']+'/api/datasets',params=dict(filename='SYNTHETIC-navigation.csv',name='SYNTHETIC navigation '+symbol,symbol=symbol,source_timezone='UTC',tick_size='.25',point_value='10'),data=b'\xef\xbb\xbf'+(FIXTURES/'arithmetic_5m.csv').read_bytes())
    assert response.status==201,response.text()
    dataset=response.json()
    request=body(dataset['id']);request['strategy_parameters']['contracts']=1
    record=page.request.post(portal['url']+'/api/backtests',data=request).json()
    return dataset,record


def test_two_column_instrument_library_opens_saved_reports_and_survives_reload(page,portal,tmp_path):
    dataset,record=seed(page,portal)
    response=page.request.post(portal['url']+'/api/backtests',data=optimization_body(dataset['id']))
    assert response.status==202,response.text()
    batch=response.json()['id'];deadline=time.monotonic()+30
    while True:
        job=page.request.get(portal['url']+'/api/backtests/batches/'+batch).json()
        if job['status'] not in ('queued','running'):break
        assert time.monotonic()<deadline;time.sleep(.05)
    assert job['status']=='complete',job
    requests=[];page.on('request',lambda r:requests.append(r.url))
    page.goto(portal['url']+'/#strategies')
    nav=page.get_by_role('navigation',name='Main navigation')
    assert nav.get_by_role('link').evaluate_all('links => links.map(n=>n.getAttribute("aria-label"))')==['Datasets','Strategies']
    playwright.expect(page.locator('#strategy-groups a')).to_have_text(['MNQ'])
    playwright.expect(page.locator('#strategy-results')).to_be_empty()
    assert not any('/api/strategies/groups/' in url for url in requests)
    playwright.expect(page.locator('#strategy-results-status')).to_contain_text('Select an instrument')
    page.locator('#strategy-groups a').click()
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(4)
    left=page.locator('.strategies-instruments').bounding_box();right=page.locator('.strategies-backtests').bounding_box()
    assert abs(left['width']-right['width'])<2 and right['x']>left['x'] and left['y']==right['y']
    page.screenshot(path=str(tmp_path/'instrument-backtests-desktop.png'),full_page=True)
    selected=page.url
    page.reload();playwright.expect(page.locator('#strategy-results tr')).to_have_count(4)
    page.get_by_role('link',name='Open backtest report '+record['id'],exact=True).click()
    playwright.expect(page.locator('#backtest-completion')).to_be_visible()
    playwright.expect(page.locator('#report-summary')).to_contain_text('13.00')
    page.screenshot(path=str(tmp_path/'full-backtest-report.png'),full_page=True)
    page.locator('#backtest-completion').get_by_role('link',name='Back to Strategies',exact=False).click()
    playwright.expect(page.locator('#strategy-results')).to_be_empty()
    page.goto(selected);page.set_viewport_size(dict(width=390,height=844))
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(4)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(tmp_path/'instrument-backtests-mobile.png'),full_page=True)
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,dataset=dataset,standalone=record,batch=job,selected_url=selected,expected_net_pnl=[13,26,39],individual_backtests=4,lazy_selection=True,report_open_reload_mobile=True),indent=2))

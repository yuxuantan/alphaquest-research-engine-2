"""Real instrument -> saved backtest -> durable report navigation."""
import json,re,time
from test_backtests_browser import browser,page,portal,playwright,FIXTURES
from test_backtest_api import body
from test_optimization import optimization_body
from research_fixtures import reserved_source,register


def seed(page,portal,symbol='MNQ'):
    raw=(FIXTURES/'arithmetic_5m.csv').read_bytes()
    if symbol!='MNQ':raw=raw.replace(b',100,60,40',b',101,61,40',1)
    raw,split=reserved_source(raw)
    response=page.request.post(portal['url']+'/api/datasets',params=dict(filename='SYNTHETIC-navigation.csv',name='SYNTHETIC navigation '+symbol,symbol=symbol,source_timezone='UTC',tick_size='.25',point_value='10'),data=b'\xef\xbb\xbf'+raw)
    assert response.status==201,response.text()
    dataset=response.json();register(dataset,split)
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
    playwright.expect(page.locator('#strategy-groups a')).to_have_text(['Consecutive Green Hold','Vwap Pullback Risk Sizing'])
    playwright.expect(page.locator('#strategy-results')).to_be_empty()
    assert not any('/datasets/' in url and '/backtests' in url for url in requests)
    playwright.expect(page.locator('#strategy-datasets-status')).to_contain_text('Select a strategy')
    page.locator('#strategy-groups a').filter(has_text='Consecutive Green Hold').click()
    playwright.expect(page.locator('#strategy-datasets tr')).to_have_count(1)
    playwright.expect(page.locator('#strategy-datasets')).to_contain_text('2026-01-05 → 2026-01-06')
    playwright.expect(page.locator('#strategy-results')).to_be_empty()
    left=page.locator('.strategies-instruments').bounding_box();right=page.locator('.strategies-backtests').bounding_box()
    assert abs(left['width']-right['width'])<2 and right['x']>left['x'] and left['y']==right['y']
    page.screenshot(path=str(tmp_path/'strategy-datasets-desktop.png'),full_page=True)
    page.locator('#strategy-datasets a.instrument-link').click()
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(4)
    selected=page.url
    page.reload();playwright.expect(page.locator('#strategy-results tr')).to_have_count(4)
    page.get_by_role('link',name='Open IS backtest report '+record['id'],exact=True).click()
    playwright.expect(page.locator('#backtest-completion')).to_be_visible()
    playwright.expect(page.locator('#report-summary')).to_contain_text('13.00')
    page.screenshot(path=str(tmp_path/'full-backtest-report.png'),full_page=True)
    page.locator('#backtest-completion').get_by_role('link',name='Back to Strategies',exact=False).click()
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(4)
    assert page.url==selected
    page.goto(selected);page.set_viewport_size(dict(width=390,height=844))
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(4)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(tmp_path/'instrument-backtests-mobile.png'),full_page=True)
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,dataset=dataset,standalone=record,batch=job,selected_url=selected,expected_net_pnl=[13,26,39],individual_backtests=4,lazy_selection=True,report_open_reload_mobile=True),indent=2))


def test_one_form_and_endpoint_run_single_or_exhaustive_backtests(page,portal,tmp_path):
    dataset,baseline=seed(page,portal)
    posts=[]
    page.on('request',lambda r:posts.append(r.post_data_json) if r.method=='POST' and r.url.split('?')[0].endswith('/api/backtests') else None)
    page.goto(portal['url']+'/#strategies')
    page.get_by_role('link',name='New backtest →',exact=True).click()
    playwright.expect(page.locator('#backtest-mode')).to_have_value('single')
    page.locator('#backtest-dataset').select_option(dataset['id'])
    page.locator('#strategy-contracts').fill('1')
    page.locator('#backtest-slippage-ticks').fill('1');page.locator('#backtest-commission').fill('1')
    page.locator('#backtest-initial-capital').fill('12345.67')
    page.locator('#start-backtest').click()
    playwright.expect(page.locator('#backtest-completion')).to_be_visible()
    playwright.expect(page.locator('#report-net')).to_have_text('13.00')
    page.get_by_role('link',name='Back to Strategies',exact=False).click()
    page.get_by_role('link',name='New backtest →',exact=True).click()
    page.locator('#backtest-mode').select_option('exhaustive')
    playwright.expect(page.locator('#optimization-settings')).to_be_visible()
    playwright.expect(page.locator('#strategy-parameters')).to_be_hidden()
    page.get_by_label('Contracts end',exact=True).fill('3')
    playwright.expect(page.locator('#optimization-count')).to_have_text('Total combinations: 3 = 3 backtests')
    page.locator('#backtest-mode').select_option('single')
    playwright.expect(page.locator('#strategy-contracts')).to_have_value('1')
    page.locator('#backtest-mode').select_option('exhaustive')
    playwright.expect(page.get_by_label('Contracts end',exact=True)).to_have_value('3')
    playwright.expect(page.locator('#backtest-initial-capital')).to_have_value('12345.67')
    page.locator('#optimization-workers').select_option('1')
    page.screenshot(path=str(tmp_path/'one-form-parameter-sweep.png'),full_page=True)
    page.locator('#start-backtest').click()
    playwright.expect(page).to_have_url(re.compile('/#backtests/batches/[a-f0-9]{32}$'))
    playwright.expect(page.locator('#optimization-status')).to_contain_text('COMPLETE',timeout=30000)
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(3)
    assert len(posts)==2 and 'strategy_parameters' in posts[0] and 'parameter_ranges' in posts[1]
    assert posts[0]['execution_settings']==posts[1]['execution_settings']
    batch_id=page.url.rsplit('/',1)[1]
    rows=page.request.get(portal['url']+'/api/backtests/batches/'+batch_id+'/results').json()['items']
    assert [row['metrics']['total_net_pnl'] for row in rows]==['13.00','26.00','39.00']
    page.screenshot(path=str(tmp_path/'shared-backtest-batch-results.png'),full_page=True)
    # Existing stored links reopen the very same job through the compatibility URL.
    page.goto(portal['url']+'/#optimizations/'+batch_id)
    playwright.expect(page.locator('#optimization-results tbody tr')).to_have_count(3)
    (tmp_path/'shared-form-verification.json').write_text(json.dumps(dict(synthetic=True,batch_id=batch_id,requests=posts,rows=rows,expected_net=[13,26,39],same_endpoint=True,drafts_and_costs_preserved=True,legacy_link_opens_same_job=True),indent=2))


def test_selection_failure_clears_old_results_and_refresh_recovers(page,portal):
    seed(page,portal);seed(page,portal,'NQ')
    page.goto(portal['url']+'/#strategies')
    page.locator('#strategy-groups a').filter(has_text='Consecutive Green Hold').click()
    playwright.expect(page.locator('#strategy-datasets tr')).to_have_count(2)
    nq=page.locator('#strategy-datasets a.instrument-link').filter(has_text=re.compile('^NQ$')).get_attribute('href').split('/')[-1]
    page.locator('#strategy-datasets a.instrument-link').filter(has_text='MNQ').click()
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(1)
    page.locator('#strategy-back-datasets').click()
    endpoint='**/api/strategies/consecutive_green_hold/datasets/'+nq+'/backtests?*'
    page.route(endpoint,lambda route:route.fulfill(status=503,json=dict(detail='Controlled history outage')))
    page.locator('#strategy-datasets a.instrument-link').filter(has_text=re.compile('^NQ$')).click()
    playwright.expect(page.locator('#strategy-results-status')).to_contain_text('Controlled history outage')
    playwright.expect(page.locator('#strategy-results')).to_be_empty()
    playwright.expect(page.locator('#strategy-results-heading')).to_have_text('Saved runs')
    playwright.expect(page.locator('#strategy-full-period')).to_be_empty()
    page.unroute(endpoint);page.locator('#refresh-strategies').click()
    playwright.expect(page.locator('#strategy-results-heading')).to_have_text('Consecutive Green Hold · NQ')
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(1)

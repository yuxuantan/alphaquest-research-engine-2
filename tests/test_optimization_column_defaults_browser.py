"""Compact varying headers, automatic visibility and old-layout migration."""
import json

from test_backtests_browser import browser,page,portal,playwright
from test_optimization_browser import prepare,run
from test_optimization import optimization_body
from test_optimization_layout_browser import visible_keys
from test_optimization_columns_browser import frozen_keys


def test_default_visibility_tracks_each_batch_and_show_all_is_explicit(page,portal,tmp_path):
    prepare(page,portal);run(page)
    first_url=page.url;first_id=first_url.rsplit('/',1)[-1]
    job=page.request.get(portal['url']+'/api/backtests/batches/'+first_id).json()
    before=page.request.get(portal['url']+'/api/backtests/batches/'+first_id+'/results').json()
    mutations=[]
    page.on('request',lambda r:mutations.append(r.url) if r.method in ('POST','PUT','PATCH','DELETE') else None)
    expected={'trial','run_id','param.contracts',*job['metric_columns']}
    assert set(visible_keys(page))==expected
    assert page.locator('.optimization-varying-badge').count()==0
    playwright.expect(page.locator('#optimization-results th[data-column="param.green_bar_count"]')).to_be_hidden()
    playwright.expect(page.locator('#optimization-results th[data-column="param.hold_minutes"]')).to_be_hidden()
    playwright.expect(page.locator('#optimization-results th[data-column="param.contracts"]')).to_have_attribute('title','3 values in this optimization grid')
    page.locator('#optimization-freeze summary').click()
    page.get_by_label('Freeze Contracts',exact=True).check()
    # Save automatic defaults with a user-selected freeze; another grid for the
    # same strategy must derive visibility from that grid's varying axes.
    request=optimization_body(portal['saved']['arithmetic_5m']['id'])
    request['parameter_ranges']['contracts']=dict(start=1,end=1,step=0)
    request['parameter_ranges']['hold_minutes']=dict(start=1,end=2,step=1)
    response=page.request.post(portal['url']+'/api/backtests',data=request)
    assert response.status==202,response.text()
    second_url=portal['url']+'/#backtests/batches/'+response.json()['id']
    page.goto(second_url)
    playwright.expect(page.locator('#optimization-status')).to_contain_text('COMPLETE',timeout=30000)
    playwright.expect(page.locator('#optimization-results th[data-column="param.hold_minutes"]')).to_be_visible()
    assert set(visible_keys(page))=={'trial','run_id','param.hold_minutes',*job['metric_columns']}
    assert frozen_keys(page)==['trial']
    page.goto(first_url)
    playwright.expect(page.locator('#optimization-freeze .optimization-freeze-count')).to_have_text('2 frozen')
    assert set(visible_keys(page))==expected
    if page.locator('#optimization-freeze').get_attribute('open') is None:
        page.locator('#optimization-freeze summary').click()
    page.get_by_role('button',name='Show all',exact=True).click()
    playwright.expect(page.locator('#optimization-results th:not([hidden])')).to_have_count(len(job['axes'])+len(job['metric_columns'])+2)
    page.reload()
    playwright.expect(page.locator('#optimization-results th[data-column="param.green_bar_count"]')).to_be_visible()
    if page.locator('#optimization-freeze').get_attribute('open') is None:
        page.locator('#optimization-freeze summary').click()
    page.get_by_role('button',name='Reset layout',exact=True).click()
    playwright.expect(page.locator('#optimization-results th[data-column="param.green_bar_count"]')).to_be_hidden()
    assert set(visible_keys(page))==expected
    assert page.request.get(portal['url']+'/api/backtests/batches/'+first_id+'/results').json()==before
    # The only numerical mutation here was the deliberately requested second grid.
    assert mutations==[]
    page.screenshot(path=str(tmp_path/'compact-defaults.png'),full_page=True)
    (tmp_path/'verification.json').write_text(json.dumps(dict(expected_visible=sorted(expected),
        fixed_parameters_hidden=True,all_metrics_visible=True,no_varies_badges=True,
        defaults_follow_current_grid=True,explicit_show_all_persists=True,results_unchanged=True),indent=2))


def test_existing_v2_custom_visibility_and_order_are_preserved_until_reset(page,portal):
    page.add_init_script("""localStorage.setItem('alphaquest.optimization.column-layout.v2:consecutive_green_hold',
      JSON.stringify({visible:['trial','param.green_bar_count','total_net_pnl'],frozen:[],order:['total_net_pnl','trial','param.green_bar_count']}));""")
    prepare(page,portal);run(page)
    assert visible_keys(page)==['total_net_pnl','trial','param.green_bar_count']
    assert frozen_keys(page)==[]
    page.locator('#optimization-freeze summary').click()
    page.get_by_role('button',name='Reset layout',exact=True).click()
    playwright.expect(page.locator('#optimization-results th[data-column="param.green_bar_count"]')).to_be_hidden()
    assert 'param.contracts' in visible_keys(page)
    assert 'total_gross_pnl' in visible_keys(page)
    assert frozen_keys(page)==['trial']

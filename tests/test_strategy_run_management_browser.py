"""Actual IS/OOS table selection and narrowly scoped report deletion controls."""
from uuid import uuid4
from hashlib import sha256
import json
from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal,playwright
from test_strategies_browser import seed
from test_backtest_api import body
from test_prop_analysis_api import backtest


def open_runs(page,portal):
    page.goto(portal['url']+'/#strategies')
    page.locator('#strategy-groups a').filter(has_text='Consecutive Green Hold').click()
    playwright.expect(page.locator('#strategy-datasets tr')).to_have_count(1)
    page.locator('#strategy-datasets a.instrument-link').click()
    playwright.expect(page.locator('#strategy-results-wrap')).to_be_visible()


def test_is_oos_table_multiple_attempts_param_sort_and_selected_deletion(page,portal,tmp_path):
    dataset,first=seed(page,portal)
    request=body(dataset['id']);request['strategy_parameters']['contracts']=2
    response=page.request.post(portal['url']+'/api/backtests',data=request);assert response.status==201,response.text()
    second=response.json();oos=[]
    for _ in range(2):
        response=page.request.post(portal['url']+'/api/backtests/'+first['id']+'/oos',data=dict(request_id=str(uuid4())))
        assert response.status==201,response.text();oos.append(response.json())
    deletes=[];page.on('request',lambda r:deletes.append(r.url) if r.method=='DELETE' else None)
    open_runs(page,portal)
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(2)
    row=page.locator(f'#strategy-results tr[data-run-id="{first["id"]}"]')
    playwright.expect(row.locator('td[data-column="is.total_net_pnl"]')).to_have_text('13')
    playwright.expect(row.locator('td[data-column="oos.total_net_pnl"]')).to_have_text('0')
    choose=row.get_by_label('OOS report for run '+first['id']);playwright.expect(choose).to_have_value(oos[1]['id'])
    choose.select_option(oos[0]['id'])
    playwright.expect(row.get_by_role('link',name='Open OOS backtest report '+oos[0]['id'],exact=True)).to_be_visible()
    playwright.expect(row.locator('.strategy-parameter-varies')).to_contain_text('contracts = 1')
    page.locator('#strategy-run-sort').select_option('param.contracts')
    playwright.expect(page.locator('#strategy-results tr').first).to_have_attribute('data-run-id',second['id'])
    page.screenshot(path=str(tmp_path/'is-oos-parameter-table.png'),full_page=True)
    page.once('dialog',lambda d:d.dismiss())
    page.get_by_role('button',name='Delete backtest '+second['id'],exact=True).click();assert not deletes
    page.once('dialog',lambda d:d.accept())
    page.get_by_role('button',name='Delete backtest '+second['id'],exact=True).click()
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(1)
    playwright.expect(page.locator('#strategy-delete-status')).to_contain_text('Backtest report deleted')
    assert page.request.get(portal['url']+'/api/backtests/'+second['id']).status==404
    assert page.request.get(portal['url']+'/api/prop-analyses/'+second['run_metadata']['automatic_prop_analysis']['id']).status==200
    budget=page.request.get(portal['url']+'/api/backtests/'+first['id']+'/oos').json();assert budget['used']==2
    assert page.request.get(portal['url']+'/api/datasets/'+dataset['id']).status==200
    page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='Delete backtest '+first['id'],exact=True).click()
    playwright.expect(page.locator('#strategy-results tr')).to_have_count(2)
    playwright.expect(page.locator('#strategy-results')).to_contain_text('matching IS report unavailable')
    for r in oos:assert page.request.get(portal['url']+'/api/backtests/'+r['id']).status==200
    page.set_viewport_size(dict(width=390,height=844));assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(tmp_path/'orphan-oos-mobile.png'),full_page=True)
    (tmp_path/'verification.json').write_text(json.dumps(dict(dataset=dataset,first=first['id'],second=second['id'],oos=[r['id'] for r in oos],budget_used=2,cancel_sent_no_delete=True,specific_reports_only=True,orphan_oos_visible=True),indent=2))


def test_prop_report_delete_cancel_confirm_keeps_backtests_and_other_analysis(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=120) as client:
        source=backtest(client);other=backtest(client,quantity=3)
    id=source['run_metadata']['automatic_prop_analysis']['id'];other_id=other['run_metadata']['automatic_prop_analysis']['id']
    original=page.request.get(portal['url']+'/api/prop-analyses/'+other_id+'/downloads/report.json').body()
    deletes=[];page.on('request',lambda r:deletes.append(r.url) if r.method=='DELETE' else None)
    page.goto(portal['url']+'/#backtests/prop/job/'+id)
    playwright.expect(page.locator('#prop-delete')).to_be_visible()
    page.screenshot(path=str(tmp_path/'prop-delete-control.png'),full_page=True)
    page.once('dialog',lambda d:d.dismiss());page.locator('#prop-delete').click();assert not deletes
    page.once('dialog',lambda d:d.accept());page.locator('#prop-delete').click()
    playwright.expect(page).to_have_url(portal['url']+'/#strategies')
    playwright.expect(page.locator('#strategy-delete-status')).to_contain_text('Prop report deleted')
    assert page.request.get(portal['url']+'/api/prop-analyses/'+id).status==404
    assert page.request.get(portal['url']+'/api/backtests/'+source['id']).json()==source
    assert page.request.get(portal['url']+'/api/prop-analyses/'+other_id+'/downloads/report.json').body()==original
    page.goto(portal['url']+'/#backtests/prop/new/'+other['id'])
    button=page.get_by_role('button',name='Delete prop report '+other_id,exact=True)
    playwright.expect(button).to_be_enabled();page.once('dialog',lambda d:d.accept());button.click()
    playwright.expect(page.locator('#prop-delete-status')).to_contain_text('Prop report deleted')
    playwright.expect(page.locator('#prop-saved a')).to_have_count(0)
    assert page.request.get(portal['url']+'/api/backtests/'+other['id']).json()==other
    assert len(deletes)==2
    (tmp_path/'verification.json').write_text(json.dumps(dict(deleted_prop_ids=[id,other_id],backtests_preserved=[source['id'],other['id']],cancel_no_request=True,report_and_saved_list_deletion=True),indent=2))


def test_dataset_shortcut_resets_instrument_overrides_for_the_new_source(page,portal):
    first=portal['saved']['arithmetic_5m'];second=portal['saved']['gap_deadline']
    response=page.request.patch(portal['url']+'/api/datasets/'+second['id']+'/instrument-settings',data=dict(tick_size='0.5',point_value='25'))
    assert response.status==200,response.text()
    page.goto(portal['url']+'/#backtests/new')
    page.locator('#backtest-dataset').select_option(first['id'])
    page.locator('#backtest-tick-size').fill('9');page.locator('#backtest-point-value').fill('999')
    page.goto(portal['url']+'/#backtests/new?strategy=consecutive_green_hold&dataset='+second['id'])
    playwright.expect(page.locator('#backtest-dataset')).to_have_value(second['id'])
    playwright.expect(page.locator('#backtest-tick-size')).to_have_value('0.5')
    playwright.expect(page.locator('#backtest-point-value')).to_have_value('25')

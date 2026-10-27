"""Real portal deletion, cancellation, busy jobs and pagination."""
import json
import time

from test_backtests_browser import browser,page,portal,playwright
from test_backtest_api import body
from test_optimization import optimization_body


def seed(page,portal,count=1):
    dataset=portal['saved']['arithmetic_5m']
    records=[]
    for _ in range(count):
        response=page.request.post(portal['url']+'/api/backtests',data=body(dataset['id']))
        assert response.status==201,response.text()
        records.append(response.json())
    return dataset,records


def test_delete_from_list_and_report_confirm_cancel_and_preserve_dataset(page,portal,tmp_path):
    dataset,(first,second)=seed(page,portal,2)
    deletes=[];dialogs=[]
    page.on('request',lambda request:deletes.append(request.url) if request.method=='DELETE' else None)
    page.goto(portal['url']+'/#backtests')
    playwright.expect(page.locator('.completed-run-row')).to_have_count(2)
    def cancel(dialog):dialogs.append(dialog.message);dialog.dismiss()
    page.once('dialog',cancel)
    page.get_by_role('button',name='Delete backtest '+first['id'],exact=True).click()
    assert not deletes
    assert page.request.get(portal['url']+'/api/backtests/'+first['id']).status==200
    page.screenshot(path=str(tmp_path/'delete-controls-list.png'),full_page=True)
    page.goto(portal['url']+'/#backtests/report/'+first['id'])
    playwright.expect(page.locator('#backtest-completion')).to_be_visible()
    page.screenshot(path=str(tmp_path/'delete-control-report.png'),full_page=True)
    def accept(dialog):dialogs.append(dialog.message);dialog.accept()
    page.once('dialog',accept)
    page.locator('#report-delete').click()
    playwright.expect(page).to_have_url(portal['url']+'/#strategies')
    playwright.expect(page.locator('#strategy-groups tr')).to_have_count(1)
    page.goto(portal['url']+'/#backtests')
    playwright.expect(page.locator('#backtest-delete-status')).to_contain_text('Backtest deleted')
    assert page.request.get(portal['url']+'/api/backtests/'+first['id']).status==404
    assert page.request.get(portal['url']+'/api/backtests/'+second['id']).json()==second
    assert page.request.get(portal['url']+'/api/datasets/'+dataset['id']).status==200
    assert 'saved prop analyses and optimization metrics are kept' in dialogs[-1]
    page.screenshot(path=str(tmp_path/'selected-backtest-deleted.png'),full_page=True)
    page.reload();playwright.expect(page.locator('.completed-run-row')).to_have_count(1)
    page.once('dialog',accept)
    page.get_by_role('button',name='Delete backtest '+second['id'],exact=True).click()
    playwright.expect(page.locator('#completed-runs-status')).to_have_text('No completed reports yet.')
    assert len(deletes)==2
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic_fixture=True,deleted_ids=[first['id'],second['id']],confirmation_messages=dialogs,cancel_sent_no_delete=True,report_and_list_deletion=True,unselected_report_preserved_until_selected=True,dataset_preserved=True,reload_verified=True),indent=2))


def test_busy_analysis_error_and_last_page_deletion_return_to_previous_page(page,portal,tmp_path):
    dataset,records=seed(page,portal,26)
    oldest=records[0];pending='e'*32;analyses=portal['app'].state.prop_analyses
    with analyses.connect() as db:
        db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',(pending,'controlled-pending',oldest['id'],'2026-10-27','queued','Controlled pending source use',None))
    page.goto(portal['url']+'/#backtests')
    playwright.expect(page.locator('.completed-run-row')).to_have_count(25)
    page.locator('#runs-next').click()
    playwright.expect(page.locator('#completed-runs-count')).to_have_text('26–26 of 26 reports')
    button=page.get_by_role('button',name='Delete backtest '+oldest['id'],exact=True)
    page.once('dialog',lambda dialog:dialog.accept());button.click()
    playwright.expect(page.locator('#backtest-delete-status')).to_contain_text('A prop analysis is using this backtest')
    playwright.expect(button).to_be_enabled()
    assert page.request.get(portal['url']+'/api/backtests/'+oldest['id']).status==200
    with analyses.connect() as db:db.execute("UPDATE analyses SET status='error' WHERE id=?",(pending,))
    page.once('dialog',lambda dialog:dialog.accept());button.click()
    playwright.expect(page.locator('#completed-runs-count')).to_have_text('1–25 of 25 reports')
    playwright.expect(page.locator('#runs-previous')).to_be_disabled()
    playwright.expect(page.locator('#runs-next')).to_be_disabled()
    assert page.request.get(portal['url']+'/api/datasets/'+dataset['id']).status==200
    page.set_viewport_size(dict(width=390,height=844))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path/'delete-mobile-pagination.png'),full_page=True)


def test_deleted_trial_keeps_optimization_metrics_without_broken_report_link(page,portal,tmp_path):
    dataset=portal['saved']['arithmetic_5m'];request=optimization_body(dataset['id'])
    request.update(workers=1)
    request['parameter_ranges']=dict(green_bar_count=dict(start=1,end=1,step=0),hold_minutes=dict(start=1,end=1,step=0),contracts=dict(start=1,end=1,step=0))
    submitted=page.request.post(portal['url']+'/api/optimizations',data=request)
    assert submitted.status==202,submitted.text()
    id=submitted.json()['id'];until=time.monotonic()+30
    while time.monotonic()<until:
        job=page.request.get(portal['url']+'/api/optimizations/'+id).json()
        if job['status']=='complete':break
        assert job['status']!='failed',job
        time.sleep(.02)
    assert job['status']=='complete',job
    row=page.request.get(portal['url']+'/api/optimizations/'+id+'/results').json()['items'][0]
    page.goto(portal['url']+'/#backtests/report/'+row['run_id'])
    playwright.expect(page.locator('#report-delete')).to_be_visible()
    page.once('dialog',lambda dialog:dialog.accept());page.locator('#report-delete').click()
    playwright.expect(page).to_have_url(portal['url']+'/#strategies')
    page.goto(portal['url']+'/#optimizations/'+id)
    cell=page.locator('#optimization-results td[data-column="run_id"]')
    playwright.expect(cell).to_contain_text('Backtest deleted')
    assert cell.locator('a').count()==0
    playwright.expect(page.locator('#optimization-results td[data-column="total_net_pnl"]')).to_have_text(row['metrics']['total_net_pnl'])
    assert page.locator('#optimization-results td[data-column="historical_net"] a').count()==1
    page.screenshot(path=str(tmp_path/'optimization-keeps-metrics.png'),full_page=True)

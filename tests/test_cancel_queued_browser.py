"""Normal source/configuration -> queued activity -> cancel -> durable history."""
from hashlib import sha256
import json
from threading import Event
import time

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal,playwright
from test_optimization_browser import prepare
from test_optimization import optimization_body,wait_job
from test_backtest_api import FIXTURES
from alphaquest.strategies import consecutive_green_hold as sample


def test_cancel_details_and_history_preserves_active_and_next_job(page,portal,tmp_path,monkeypatch):
    entered,release=Event(),Event();original=sample.ConsecutiveGreenHold.on_bar
    def pause(self,bar,position):
        if not release.is_set():entered.set();assert release.wait(90)
        return original(self,bar,position)
    monkeypatch.setattr(sample.ConsecutiveGreenHold,'on_bar',pause)
    writes=[]
    page.on('request',lambda r:writes.append([r.method,r.url]) if r.method in ('POST','DELETE') else None)
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-queued-cancellation.csv',name='SYNTHETIC queued cancellation arithmetic',source_timezone='UTC',tick_size='0.25',point_value='10'),content=b'\xef\xbb\xbf'+(FIXTURES/'arithmetic_5m.csv').read_bytes())
        assert response.status_code==201,response.text
        dataset=response.json()
        portal['saved']['arithmetic_5m']=dataset
        r=client.post('/api/optimizations',json=optimization_body(dataset['id'])|dict(automatic_prop=False))
        assert r.status_code==202,r.text
        first=r.json()['id']
        try:
            assert entered.wait(10)
            def queue_from_form():
                prepare(page,portal);page.locator('#optimization-automatic-prop').uncheck()
                page.locator('#start-backtest').click()
                playwright.expect(page.locator('#optimization-status')).to_contain_text('QUEUED')
                return page.url.rsplit('/',1)[-1]
            second=queue_from_form()
            playwright.expect(page.locator('#optimization-cancel')).to_be_visible()
            playwright.expect(page.locator('#optimization-delete')).to_be_disabled()
            page.screenshot(path=str(tmp_path/'queued-details.png'),full_page=True)
            page.once('dialog',lambda dialog:dialog.dismiss());page.locator('#optimization-cancel').click()
            assert client.get(f'/api/optimizations/{second}').json()['status']=='queued'
            assert not [url for method,url in writes if url.endswith('/cancel')]
            page.once('dialog',lambda dialog:dialog.accept());page.locator('#optimization-cancel').click()
            playwright.expect(page.locator('#optimization-status')).to_contain_text('CANCELLED')
            playwright.expect(page.locator('#optimization-cancel')).to_be_hidden()
            playwright.expect(page.locator('#optimization-resume')).to_be_hidden()
            playwright.expect(page.locator('#optimization-delete')).to_be_enabled()
            page.reload();playwright.expect(page.locator('#optimization-status')).to_contain_text('CANCELLED')
            page.screenshot(path=str(tmp_path/'cancelled-details.png'),full_page=True)
            third=queue_from_form()
            last=client.post('/api/optimizations',json=optimization_body(dataset['id'])|dict(automatic_prop=False)).json()['id']
            page.goto(portal['url']+'/#backtests/batches')
            cancel=page.get_by_role('button',name='Cancel queued activity '+third,exact=True)
            playwright.expect(cancel).to_be_visible()
            page.once('dialog',lambda dialog:dialog.accept());cancel.click()
            row=page.locator('#optimization-results tbody tr').filter(has=page.locator(f'a[href="#backtests/batches/{third}"]'))
            playwright.expect(row).to_contain_text('cancelled')
            playwright.expect(page.get_by_role('button',name='Stop running backtest '+first,exact=True)).to_be_visible()
            assert client.get(f'/api/optimizations/{first}').json()['status']=='running'
            assert client.get(f'/api/optimizations/{last}').json()['status']=='queued'
            page.set_viewport_size(dict(width=390,height=844))
            page.screenshot(path=str(tmp_path/'cancelled-history-narrow.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
            page.locator('#optimization-results-scroll').evaluate('(node)=>{node.scrollLeft=node.scrollWidth;}')
            page.screenshot(path=str(tmp_path/'history-actions-narrow.png'),full_page=True)
        finally:release.set()
        snapshots={}
        for id in (first,last):
            done=wait_job(client,id);assert done['status']=='complete',done
            rows=client.get(f'/api/optimizations/{id}/results').json()['items']
            assert [float(row['metrics']['total_net_pnl']) for row in rows]==[13,26,39]
            snapshots[id]=dict(job=done,rows=rows)
        for id in (second,third):
            done=client.get(f'/api/optimizations/{id}').json()
            assert done['status']=='cancelled' and done['completed_trials']==0 and 'started_at_utc' not in done
            assert client.get(f'/api/optimizations/{id}/results').json()['items']==[]
            snapshots[id]=dict(job=done,rows=[])
        # Reopen normal completed product output, with unchanged source and downloadable report.
        report_id=snapshots[first]['rows'][0]['run_id']
        page.goto(portal['url']+'/#backtests/report/'+report_id)
        playwright.expect(page.locator('#report-summary')).to_contain_text('13.00')
        report=client.get('/api/backtests/'+report_id);assert report.status_code==200
        csv=client.get('/api/datasets/'+dataset['id']+'/csv');assert sha256(csv.content).hexdigest()==dataset['sha256']
        (tmp_path/'SYNTHETIC-arithmetic.csv').write_bytes(csv.content)
        (tmp_path/'retained-backtest.json').write_bytes(report.content)
        (tmp_path/'evidence.json').write_text(json.dumps(dict(synthetic=True,active_id=first,cancelled_ids=[second,third],next_id=last,
            expected_net_pnl=[13,26,39],snapshots=snapshots,cancel_requests=[url for method,url in writes if url.endswith('/cancel')],
            delete_requests=[url for method,url in writes if method=='DELETE'],confirmation_dismissal_preserved_queue=True,
            downloads={'SYNTHETIC-arithmetic.csv':sha256(csv.content).hexdigest(),'retained-backtest.json':sha256(report.content).hexdigest()},
            temporary_server='Stopped and joined by portal fixture.'),indent=2)+'\n')
        assert len([url for method,url in writes if url.endswith('/cancel')])==2
        assert not [url for method,url in writes if method=='DELETE']

"""Refresh one existing batch through the normal UI; preserve original reports."""
import argparse
import csv
import io
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright,expect


def review(url,batch_id,output):
    output.mkdir(parents=True,exist_ok=False)
    base='/api/backtests/batches/'+batch_id
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch()
        try:
            page=browser.new_page(viewport=dict(width=1440,height=1100))
            errors=[];posts=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
            def get(path):
                response=page.request.get(url+path)
                assert response.ok,response.text()
                return response.json()
            before=get(base+'/results?limit=1000&prop_revision=0')['items']
            (output/'original-trials.json').write_text(json.dumps(before,indent=2))
            page.goto(url+'/#backtests/batches/'+batch_id)
            expect(page.locator('#optimization-lucid-run')).to_be_enabled()
            page.locator('th[data-column="lucid_historical_net"]').scroll_into_view_if_needed()
            page.screenshot(path=str(output/'01-before-refresh.png'),full_page=True)
            with page.expect_response(lambda r:r.url.endswith('/lucid-refresh') and r.request.method=='POST',timeout=120000) as response:
                page.locator('#optimization-lucid-run').click()
            assert response.value.status==202,response.value.text()
            started=response.value.json()
            (output/'refresh-start.json').write_text(json.dumps(started,indent=2))
            print('Refresh started:',json.dumps(started),flush=True)
            end=time.monotonic()+3600;last=None
            while time.monotonic()<end:
                state=get(base+'/lucid-refresh')
                if state!=last:
                    print('Progress:',json.dumps(state),flush=True);last=state
                if not state['pending']:break
                page.wait_for_timeout(3000)
            assert not state['pending'],state
            # Sorting and downloads use the same saved projection/revision.
            page.reload()
            expect(page.locator('#optimization-lucid-status')).to_contain_text(f"{state['available']} / {state['total']} Lucid values available")
            page.locator('th[data-column="lucid_historical_net"] button').click()
            page.locator('th[data-column="lucid_historical_net"] button').click()
            expect(page.locator('th[data-column="lucid_historical_net"]')).to_have_attribute('aria-sort','descending')
            page.screenshot(path=str(output/'02-refreshed-table.png'),full_page=True)
            with page.expect_download() as download:page.locator('#optimization-download').click()
            download.value.save_as(output/'updated-results.csv')
            with page.expect_download() as download:page.locator('#optimization-original-download').click()
            download.value.save_as(output/'original-results.csv')
            after=get(base+'/results?limit=1000&sort=lucid_historical_net&direction=desc')['items']
            (output/'updated-trials.json').write_text(json.dumps(after,indent=2))
            values=[r['metrics']['lucid_historical_net'] for r in after if r['metrics'].get('lucid_historical_net') is not None]
            assert values==sorted(values,reverse=True)
            csv_rows=list(csv.DictReader(io.StringIO((output/'updated-results.csv').read_text())))
            assert {int(r['trial']):int(r['lucid_historical_net']) if r['lucid_historical_net'] else None for r in csv_rows}=={r['trial']:r['metrics'].get('lucid_historical_net') for r in after}
            verified=[]
            original_by_trial={r['trial']:r for r in before}
            for row in after:
                original=original_by_trial[row['trial']]
                assert {k:v for k,v in row['metrics'].items() if k!='lucid_historical_net'}=={k:v for k,v in original['metrics'].items() if k!='lucid_historical_net'}
                if not row.get('lucid_refresh'):continue
                item=row['prop_companions'][0]
                if item['status']!='complete':continue
                report=get('/api/prop-analyses/'+item['id']+'/downloads/report.json')
                old=get('/api/prop-analyses/'+original['prop_companions'][0]['id']+'/downloads/report.json')
                assert report['source']==old['source'] and report['settings']==old['settings']
                history=report['calculations'].get('history')
                assert row['metrics']['lucid_historical_net']==(history['totals']['net'] if history else None)
                verified.append(dict(trial=row['trial'],source_id=row['run_id'],analysis_id=item['id'],historical_net=row['metrics']['lucid_historical_net'],model_version=report['model_version']))
            assert get(base+'/results?limit=1000&prop_revision=0')['items']==before
            posts.clear();page.reload()
            expect(page.locator('#optimization-lucid-status')).to_contain_text(f"{state['available']} / {state['total']} Lucid values available")
            assert not posts and not errors,(posts,errors)
            result=dict(batch_id=batch_id,before_available=sum(r['metrics'].get('lucid_historical_net') is not None for r in before),
                final_status=state,verified_reports=verified,original_snapshot_preserved=True,apex_metrics_preserved=True,
                table_sort_matches_csv=True,reload_read_only=True,javascript_errors=errors,
                unresolved=[dict(trial=r['trial'],reason=r['prop_companions'][0].get('reason')) for r in after if r['metrics'].get('lucid_historical_net') is None])
            (output/'verification.json').write_text(json.dumps(result,indent=2))
            print('Finished:',json.dumps(state),flush=True)
        finally:browser.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://localhost:8000');p.add_argument('--batch-id',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();review(a.url.rstrip('/'),a.batch_id,a.output)

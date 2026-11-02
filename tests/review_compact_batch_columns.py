"""Read-only browser review of compact/default/unlimited batch column layouts."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect


def review(url,batch_id,output):
    output.mkdir(parents=True,exist_ok=False)
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch()
        try:
            page=browser.new_page(viewport=dict(width=1440,height=1100))
            errors=[];mutations=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:mutations.append(r.url) if r.method in ('POST','PUT','PATCH','DELETE') else None)
            endpoint=url+'/api/backtests/batches/'+batch_id
            job=page.request.get(endpoint).json()
            before=page.request.get(endpoint+'/results?limit=1000').body()
            csv_before=page.request.get(endpoint+'/exports/results').body()
            varied=['param.'+key for key,values in job['axes'].items() if len(values)>1]
            expected={'trial','run_id',*varied,*job['metric_columns']}
            def visible():return page.locator('#optimization-results thead th:not([hidden])').evaluate_all('cells=>cells.map(cell=>cell.dataset.column)')
            def frozen():return page.locator('#optimization-results thead .optimization-frozen-column').evaluate_all('cells=>cells.map(cell=>cell.dataset.column)')
            page.goto(url+'/#backtests/batches/'+batch_id)
            expect(page.locator('#optimization-status')).to_contain_text('COMPLETE',timeout=30000)
            expect(page.locator('#optimization-results thead th:not([hidden])')).to_have_count(len(expected))
            assert set(visible())==expected
            assert page.locator('.optimization-varying-badge').count()==0
            assert frozen()==['trial']
            # Restore only the prior header decoration/padding in this private
            # browser to measure the space removed. Source data never changes.
            widths=page.evaluate("""async () => {
                const table=document.querySelector('#optimization-results');
                const headers=[...table.querySelectorAll('th.optimization-varying-parameter')];
                const cells=[...table.querySelectorAll('.optimization-varying-parameter')];
                const compact=headers.map(h=>({key:h.dataset.column,width:h.getBoundingClientRect().width}));
                for(const cell of cells){cell.style.paddingLeft='24px';cell.style.paddingRight='24px';}
                for(const header of headers){const badge=document.createElement('span');badge.dataset.reviewBadge='true';badge.textContent='Varies';badge.style.cssText='display:inline-block;margin-left:8px;padding:2px 5px;border:1px solid #a5cbbb;border-radius:4px;font-size:10px;font-weight:600';header.querySelector('button').append(badge);}
                await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                const old=headers.map(h=>h.getBoundingClientRect().width);
                table.querySelectorAll('[data-review-badge]').forEach(el=>el.remove());
                for(const cell of cells){cell.style.removeProperty('padding-left');cell.style.removeProperty('padding-right');}
                await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                return compact.map((value,i)=>({...value,prior_style_width:old[i],saved_width:old[i]-value.width}));
            }""")
            assert all(item['saved_width']>0 for item in widths),widths
            page.screenshot(path=str(output/'01-default-compact-columns.png'),full_page=True)
            page.locator('#optimization-freeze summary').click()
            for key in varied:
                page.locator(f'.optimization-column-choice[data-column="{key}"] input[data-control=freeze]').check()
            expect(page.locator('#optimization-results thead .optimization-frozen-column')).to_have_count(len(varied)+1)
            page.locator('#optimization-freeze summary').click()
            page.screenshot(path=str(output/'02-varied-parameters-frozen.png'),full_page=True)
            page.locator('#optimization-freeze summary').click()
            page.get_by_role('button',name='Show all',exact=True).click()
            expect(page.locator('#optimization-results thead th:not([hidden])')).to_have_count(len(job['axes'])+len(job['metric_columns'])+2)
            all_keys=visible()
            for key in all_keys:
                page.locator(f'.optimization-column-choice[data-column="{key}"] input[data-control=freeze]').check()
            expect(page.locator('#optimization-results thead .optimization-frozen-column')).to_have_count(len(all_keys))
            assert set(frozen())==set(all_keys)
            page.locator('#optimization-freeze summary').click()
            region=page.locator('#optimization-results-scroll')
            region.evaluate('el=>el.scrollLeft=el.scrollWidth-el.clientWidth')
            page.wait_for_function("""() => {
                const region=document.querySelector('#optimization-results-scroll').getBoundingClientRect();
                const last=document.querySelector('#optimization-results thead .optimization-frozen-last').getBoundingClientRect();
                return last.left>=region.left-1&&last.right<=region.right+1;
            }""")
            page.screenshot(path=str(output/'03-all-columns-frozen-and-panned.png'),full_page=True)
            page.set_viewport_size(dict(width=390,height=844))
            expect(page.locator('#optimization-results thead .optimization-frozen-column')).to_have_count(len(all_keys))
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(output/'04-all-frozen-mobile.png'),full_page=True)
            page.reload()
            expect(page.locator('#optimization-results thead .optimization-frozen-column')).to_have_count(len(all_keys))
            page.locator('#optimization-freeze summary').click()
            page.get_by_role('button',name='Reset layout',exact=True).click()
            expect(page.locator('#optimization-results thead th:not([hidden])')).to_have_count(len(expected))
            assert set(visible())==expected and frozen()==['trial']
            assert page.request.get(endpoint+'/results?limit=1000').body()==before
            assert page.request.get(endpoint+'/exports/results').body()==csv_before
            assert not errors and not mutations,(errors,mutations)
            (output/'verification.json').write_text(json.dumps(dict(batch_id=batch_id,
                total_columns=len(all_keys),default_visible_count=len(expected),default_varied_parameters=varied,
                default_metrics=job['metric_columns'],fixed_parameters_hidden=len(job['axes'])-len(varied),
                all_columns_frozen=len(all_keys),pan_reaches_last_column=True,mobile_preserves_all_freezes=True,
                width_reference='Prior badge/padding styling reconstructed locally for measurement only',
                measured_header_widths=widths,reset_restores_defaults=True,
                saved_results_and_csv_byte_identical=True,mutating_requests=mutations,javascript_errors=errors),indent=2))
            print(json.dumps(dict(visible_defaults=len(expected),fixed_hidden=len(job['axes'])-len(varied),frozen_without_limit=len(all_keys),widths=widths,results_preserved=True),indent=2))
        finally:browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://localhost:8000');parser.add_argument('--batch-id',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();review(args.url.rstrip('/'),args.batch_id,args.output)

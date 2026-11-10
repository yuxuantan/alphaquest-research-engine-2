"""Normal portal journey through both measured Narrow branches and frozen OOS handoff."""
import json
import os
import shutil
from pathlib import Path

import httpx
from test_backtests_browser import browser,page,portal,playwright
from test_campaign_narrow import narrow_workflow,narrow_start


def test_narrow_portal_two_broad_branches_columns_and_oos_handoff(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=40) as client:
        dataset,workflow,broad=narrow_workflow(client)
    prefix=portal['url']+'/api/campaign-workflows/'+workflow['id']
    page.goto(portal['url']+f'/#campaigns/workflows/{workflow["id"]}/is_narrow')
    playwright.expect(page.locator('#narrow-chooser')).to_be_visible()
    playwright.expect(page.locator('#narrow-broad-trial option')).to_have_count(2)
    for item in page.locator('#narrow-config tr[data-parameter="contracts"] input').all():
        playwright.expect(item).to_be_disabled()
    playwright.expect(page.locator('#narrow-config tr[data-parameter="contracts"] input').first).to_have_value('1')
    page.get_by_label('Hold minutes end',exact=True).fill('21')
    page.get_by_label('Hold minutes step',exact=True).fill('1')
    page.locator('#narrow-preview').click()
    playwright.expect(page.locator('#narrow-count')).to_have_text('2 iterations · IS only')
    page.locator('#narrow-run').click()
    playwright.expect(page.locator('#narrow-progress')).to_contain_text('COMPLETE · 2 / 2 trials',timeout=30000)
    playwright.expect(page.locator('#narrow-results tbody tr')).to_have_count(2)
    playwright.expect(page.locator('#narrow-selected')).to_contain_text('0 / 2')
    assert page.request.get(prefix+'/narrow/results?broad_trial=1').json()['all_branches_complete'] is False
    with httpx.Client(base_url=portal['url'],timeout=40) as client:
        second=narrow_start(client,'/api/campaign-workflows/'+workflow['id'],2)
    page.reload()
    playwright.expect(page.locator('#narrow-results tbody tr')).to_have_count(2)
    playwright.expect(page.locator('#narrow-results thead th.optimization-frozen-column').first).to_be_visible()
    assert page.locator('#narrow-results thead th.optimization-frozen-column').evaluate_all('items => items.map(el=>el.dataset.column)')==['select','trial','param.hold_minutes']
    playwright.expect(page.locator('#narrow-results th[data-column="param.contracts"]')).to_be_hidden()
    playwright.expect(page.locator('#narrow-results td[data-column="total_net_pnl"]').first).to_have_text('9360.00')
    row=page.locator('#narrow-results tbody tr').first
    row.locator('.broad-row-criteria summary').click()
    playwright.expect(row.locator('.broad-row-criteria')).to_contain_text('Search-adjusted daily net lower bound')
    playwright.expect(row.locator('.broad-row-criteria')).to_contain_text('Bonferroni family of 6 attempted trials')
    playwright.expect(page.get_by_role('checkbox',name='Select Narrow trial 1')).to_be_enabled()
    with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/narrow/selection')):
        page.get_by_role('checkbox',name='Select Narrow trial 1').check()
    page.locator('#narrow-confirm').click()
    playwright.expect(page.locator('#narrow-confirm')).to_have_text('Narrow choices confirmed')
    playwright.expect(page.locator('#mechanic-phases [data-phase="oos"]')).to_be_disabled()
    page.locator('#narrow-broad-trial').select_option('2')
    playwright.expect(page.locator('#narrow-results tbody tr')).to_have_count(2)
    with page.expect_response(lambda r:r.request.method=='PATCH' and r.url.endswith('/narrow/selection')):
        page.get_by_role('checkbox',name='Select Narrow trial 1').check()
    page.locator('#narrow-confirm').click()
    playwright.expect(page.locator('#narrow-confirm')).to_have_text('Narrow choices confirmed')
    page.reload()
    playwright.expect(page.locator('#mechanic-phases [data-phase="oos"]')).to_be_enabled()
    with page.expect_download() as download:
        page.get_by_role('link',name='Saved IS Narrow package ↓').click()
    download.value.save_as(tmp_path/'is-narrow-package.json')
    package=json.loads((tmp_path/'is-narrow-package.json').read_text())
    assert package['state']['broad_trial']==2 and package['state']['selected_trials']==[1]
    assert package['state']['selection'][0]['admission']['family_size']==6
    assert page.request.get(portal['url']+'/api/jobs/backtest_batch/'+second['id']).json()['links'][0]['label']=='Open IS Narrow'
    (tmp_path/'SYNTHETIC-source.csv').write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset['id']+'/csv').body())
    (tmp_path/'narrow-results.json').write_text(json.dumps(page.request.get(prefix+'/narrow/results?broad_trial=2').json(),indent=2))
    (tmp_path/'journey.json').write_text(json.dumps({'workflow_id':workflow['id'],'dataset_id':dataset['id'],
        'broad_trials':[1,2],'narrow_trials_per_branch':2,'attempted_family_size':6,
        'chosen_narrow_trials':{'1':[1],'2':[1]},'expected_oos_navigation':'ready',
        'synthetic':True,'mc_parity':'Manual attestation in synthetic fixture; no external MultiCharts comparison',
        'server':'Stopped by fixture teardown.'},indent=2))
    page.screenshot(path=str(tmp_path/'is-narrow-portal.png'),full_page=True)
    if destination:=os.environ.get('ALPHAQUEST_NARROW_EVIDENCE_DIR'):
        folder=Path(destination);folder.mkdir(parents=True,exist_ok=True)
        for name in ('SYNTHETIC-source.csv','narrow-results.json','is-narrow-package.json','journey.json','is-narrow-portal.png'):
            shutil.copyfile(tmp_path/name,folder/name)

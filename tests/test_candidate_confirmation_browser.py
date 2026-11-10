"""Normal saved report → exact large-search confirmation → durable full results."""
from prop_setup_helpers import open_prop_task
from hashlib import sha256
import json

import httpx
import pytest

from test_backtests_browser import browser,page,portal,playwright
from test_candidate_confirmation import saved_large_grid


@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_large_campaign_confirmation_from_saved_report(page,portal,tmp_path,phase):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        source,job,rows=saved_large_grid(client)
    page.goto(portal['url']+'/#backtests/report/'+source['id'])
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'compare', close_outer=True)
    page.locator('#campaign-new-'+phase).click()
    assert page.locator('#campaign-budget').count() == 0
    page.locator('#campaign-paths').fill('8')
    page.locator('#campaign-block').select_option('1')
    if phase=='evaluation':page.locator('#campaign-chains').fill('8')
    else:
        page.locator('#campaign-horizon').fill('14')
        page.locator('#campaign-delay').fill('4')
    page.locator('.campaign-kind').select_option('optimization_id')
    page.locator('.campaign-source-search').fill(job['id'])
    playwright.expect(page.locator('.campaign-source-status')).to_contain_text('1 of 1')
    page.locator('.campaign-reference').select_option(job['id'])
    sizes=[10,11,12] if phase=='evaluation' else [3,4,5]
    page.locator('.campaign-sizes').fill(','.join(map(str,sizes)))
    dialogs=[]
    def cancel(dialog):
        dialogs.append(dict(type=dialog.type,message=dialog.message,accepted=False))
        dialog.dismiss()
    page.once('dialog',cancel)
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-status')).to_contain_text('Cancelled: 129 candidates')
    playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    assert len(dialogs)==1 and '129 candidates' in dialogs[0]['message']
    assert page.request.get(portal['url']+'/api/research-campaigns').json()['items']==[]
    page.screenshot(path=str(tmp_path/'confirmation-cancelled.png'),full_page=True)
    # Configuration changes discard any earlier acknowledgement. Below threshold
    # needs no dialog; restoring the large set asks again for this declaration.
    page.locator('.campaign-sizes').fill(','.join(map(str,sizes[:2])))
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=60000)
    playwright.expect(page.locator('#campaign-count')).to_have_text('86 candidates selected.')
    page.locator('.campaign-sizes').fill(','.join(map(str,sizes)))
    playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    def accept(dialog):
        dialogs.append(dict(type=dialog.type,message=dialog.message,accepted=True))
        dialog.accept()
    page.once('dialog',accept)
    with page.expect_request(lambda r:r.method=='POST' and r.url.endswith('/api/research-campaigns')
            and r.post_data_json.get('confirmed_candidate_count')==129,timeout=60000) as sent:
        page.locator('#campaign-check').click()
    assert 'maximum_candidates' not in sent.value.post_data_json
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=60000)
    playwright.expect(page.locator('#campaign-count')).to_have_text('129 candidates selected · confirmed.')
    assert len(dialogs)==2 and dialogs[1]['accepted']
    page.screenshot(path=str(tmp_path/'confirmed-source-check.png'),full_page=True)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign',timeout=60000)
    campaign_id=page.url.rsplit('/',1)[-1]
    prefix=portal['url']+'/api/research-campaigns/'+campaign_id
    campaign=page.request.get(prefix).json()
    assert campaign['manifest']['candidate_confirmation']['confirmed_count']==129
    result=page.request.get(prefix+'/exports/results.json').json()
    assert len(result['candidates'])==129
    actual={(c['manifest']['configuration']['source']['source_backtest_id'],c['manifest']['configuration']['micros']) for c in result['candidates']}
    assert actual=={(r['run_id'],size) for r in rows for size in sizes}
    for c in result['candidates']:
        if phase=='evaluation':
            assert c['metrics']['cost_per_funded']==70 and c['metrics']['expected_calendar_days_to_funded']==2
        else:
            assert c['metrics']['expected_payouts']==c['metrics']['expected_pending_cash']==1500
    page.screenshot(path=str(tmp_path/'full-campaign-results.png'),full_page=True)
    snapshots={}
    for kind in ('campaign.json','source_checks.json','results.json','results.csv','report.json','analysis.zip'):
        response=page.request.get(prefix+'/exports/'+kind)
        assert response.ok
        snapshots[kind]=response.body()
        (tmp_path/kind).write_bytes(response.body())
    posts=[]
    page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    page.reload()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign')
    for kind,data in snapshots.items():
        assert page.request.get(prefix+'/exports/'+kind).body()==data
    assert posts==[]
    (tmp_path/'workflow.json').write_text(json.dumps(dict(synthetic=True,phase=phase,grid_id=job['id'],
        source_ids=[r['run_id'] for r in rows],sizes=sizes,campaign_id=campaign_id,analysis_id=campaign['analysis_id'],
        candidate_count=129,dialogs=dialogs,reopen_posts=posts,
        downloads={name:sha256(data).hexdigest() for name,data in snapshots.items()},
        server='Stopped by portal fixture cleanup.'),indent=2))

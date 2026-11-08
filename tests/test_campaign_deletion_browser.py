"""Actual report → phase campaign → deletion → released backtest and retained report."""
from hashlib import sha256
import json
from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal,playwright
from test_prop_phases import save_source


def test_campaign_delete_confirmation_release_and_durable_report(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        source=save_source(client,days=8)
    sid=source['id'];deletes=[]
    source_json=page.request.get(portal['url']+'/api/backtests/'+sid).body()
    dataset_csv=page.request.get(portal['url']+'/api/datasets/'+source['run_metadata']['dataset']['id']+'/csv').body()
    page.on('request',lambda request:deletes.append(request.url) if request.method=='DELETE' else None)
    page.goto(portal['url']+'/#backtests/report/'+sid)
    page.locator('#report-prop-setup').click()
    page.locator('#campaign-configure > summary').click()
    page.locator('#campaign-phase').select_option('funded')
    page.locator('#campaign-paths').fill('8');page.locator('#campaign-block').select_option('1')
    page.locator('#campaign-horizon').fill('14');page.locator('#campaign-delay').fill('4')
    page.locator('#campaign-breach').fill('0');page.locator('.campaign-sizes').fill('1,3')
    page.locator('#campaign-check').click();playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#campaign-delete')).to_be_enabled(timeout=120000)
    cid=page.url.rsplit('/',1)[-1]
    c=page.request.get(portal['url']+'/api/research-campaigns/'+cid).json();aid=c['analysis_id']
    normal=page.request.get(portal['url']+'/api/prop-analyses/'+aid+'/downloads/report.json').body()
    result=json.loads(normal);assert sorted(r['metrics']['expected_payouts'] for r in result['calculations']['candidates'])==[0,1500]
    archive=page.request.get(portal['url']+'/api/prop-analyses/'+aid+'/downloads/analysis.zip').body()
    page.screenshot(path=str(tmp_path/'campaign-delete-preview.png'),full_page=True)
    confirmations=[]
    def cancel(dialog):confirmations.append(dialog.message);dialog.dismiss()
    page.once('dialog',cancel)
    with page.expect_event('dialog'):
        page.locator('#campaign-delete').click()
    assert not deletes and 'Keep all backtests, 1 calculation record and research-access history' in confirmations[-1]
    assert page.request.get(portal['url']+'/api/research-campaigns/'+cid).status==200
    # Reach campaign management through the actual Research catalogue.
    page.goto(portal['url']+'/#backtests/research')
    page.get_by_role('link',name='Manage campaign',exact=True).click()
    playwright.expect(page.locator('#campaign-delete')).to_be_enabled()
    page.set_viewport_size(dict(width=390,height=844))
    page.screenshot(path=str(tmp_path/'campaign-delete-narrow.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
    page.once('dialog',lambda dialog:dialog.accept());page.locator('#campaign-delete').click()
    playwright.expect(page.locator('#campaign-deletion-result')).to_contain_text('1 campaign source reference released')
    assert len(deletes)==1 and deletes[0].endswith('/api/research-campaigns/'+cid)
    audit=page.request.get(portal['url']+f'/api/research-campaigns/{cid}/exports/deletion_record.json').body()
    receipt=json.loads(audit)['receipt'];assert receipt['source_ids']==[sid]
    page.screenshot(path=str(tmp_path/'campaign-deleted.png'),full_page=True)
    posts=[];page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#campaign-deletion-result')).to_be_visible()
    assert not posts and len(deletes)==1
    assert page.request.get(portal['url']+'/api/backtests/'+sid).status==200
    page.goto(portal['url']+'/#backtests/prop/job/'+aid)
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Independent phase analysis')
    assert page.request.get(portal['url']+'/api/prop-analyses/'+aid+'/downloads/report.json').body()==normal
    page.screenshot(path=str(tmp_path/'retained-phase-report.png'),full_page=True)
    page.goto(portal['url']+'/#backtests/report/'+sid)
    playwright.expect(page.locator('#report-delete')).to_be_visible()
    page.once('dialog',lambda dialog:dialog.accept());page.locator('#report-delete').click()
    playwright.expect(page).to_have_url(portal['url']+'/#strategies')
    assert page.request.get(portal['url']+'/api/backtests/'+sid).status==404
    assert page.request.get(portal['url']+'/api/prop-analyses/'+aid+'/downloads/report.json').body()==normal
    assert page.request.get(portal['url']+'/api/prop-analyses/'+aid+'/downloads/analysis.zip').body()==archive
    page.goto(portal['url']+'/#backtests/research')
    playwright.expect(page.get_by_role('link',name='Manage campaign',exact=True)).to_have_count(0)
    for name,raw in [('retained-report.json',normal),('retained-analysis.zip',archive),('deletion-record.json',audit),('original-source-report.json',source_json),('SYNTHETIC-source.csv',dataset_csv)]:
        (tmp_path/name).write_bytes(raw)
    (tmp_path/'evidence.json').write_text(json.dumps(dict(synthetic=True,source_id=sid,campaign_id=cid,analysis_id=aid,
        expected_cash=[0,1500],cancel_preserved_campaign=True,source_deleted_only_after_separate_confirmation=True,
        deleted_campaign_reload_posts=posts,delete_requests=deletes,
        downloads={name:sha256(raw).hexdigest() for name,raw in [('retained-report.json',normal),('retained-analysis.zip',archive),('deletion-record.json',audit),('original-source-report.json',source_json),('SYNTHETIC-source.csv',dataset_csv)]},
        temporary_server='Stopped and joined by portal fixture.'),indent=2))

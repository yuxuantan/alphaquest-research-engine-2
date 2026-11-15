"""Actual Campaigns removal, cancellation, Undo and durable restoration."""
from pathlib import Path
from hashlib import sha256
import json
import os
import shutil

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal,playwright
from test_campaign_mechanics import create_workflow,run_validation
from test_research_workflow import save,start_is


def evidence(tmp_path,name,data):
    (tmp_path/(name+'.json')).write_text(json.dumps(data,indent=2))
    if destination:=os.environ.get('ALPHAQUEST_LINK_EVIDENCE_DIR'):
        target=Path(destination)/name;target.mkdir(parents=True,exist_ok=True)
        for p in tmp_path.iterdir():
            if p.is_file():shutil.copyfile(p,target/p.name)


def test_remove_workflow_link_cancel_undo_reload_and_restore(page,portal,tmp_path):
    base=portal['url'];campaign=base+'/#campaigns/consecutive_green_hold'
    with ResearchHTTPClient(base_url=base,timeout=120) as client:
        dataset,body,workflow=create_workflow(client);result=run_validation(client,workflow)
        before_campaigns=client.get('/api/strategies/library').json()
        before_dataset=client.get('/api/datasets/'+dataset['id']).json()
        report_dir=portal['app'].state.runs.root/result['run_id']
        hashes={p.name:sha256(p.read_bytes()).hexdigest() for p in report_dir.iterdir() if p.is_file()}
        page.goto(campaign);card=page.locator('.workflow-real-dataset').filter(has_text=dataset['name'])
        playwright.expect(card).to_have_count(1)
        assert page.get_by_role('button',name='Delete campaign',exact=True).count()==0
        deletions=[];page.on('request',lambda r:deletions.append(r.url) if r.method=='DELETE' else None)
        remove=card.get_by_role('button',name=f'Remove {dataset["name"]} from campaign',exact=True)
        page.once('dialog',lambda d:d.dismiss());remove.click()
        playwright.expect(remove).to_be_enabled()
        assert not deletions
        playwright.expect(card).to_have_count(1)
        page.once('dialog',lambda d:d.accept());remove.click()
        playwright.expect(card).to_have_count(0)
        notice=page.locator('.workflow-link-notice')
        playwright.expect(notice).to_contain_text('Dataset and saved results kept')
        notice.get_by_role('button',name='Undo',exact=True).click()
        playwright.expect(card).to_have_count(1)
        page.once('dialog',lambda d:d.accept());remove.click()
        playwright.expect(card).to_have_count(0)
        page.reload();playwright.expect(card).to_have_count(0)
        playwright.expect(page.locator('#workflow-campaign-detail')).to_contain_text('No saved datasets for this campaign')
        removed=page.locator('.workflow-removed-datasets');removed.get_by_text('Removed datasets · 1',exact=True).click()
        playwright.expect(removed).to_contain_text(dataset['name'])
        page.locator('#workflow-campaign-detail').screenshot(path=str(tmp_path/'removed.png'))
        page.set_viewport_size(dict(width=390,height=844))
        assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
        page.locator('#workflow-campaign-detail').screenshot(path=str(tmp_path/'removed-mobile.png'))
        assert client.get('/api/datasets/'+dataset['id']).json()==before_dataset
        assert client.get('/api/campaign-workflows/'+workflow['id']).json()==result
        assert client.get('/api/strategies/library').json()==before_campaigns
        assert {p.name:sha256(p.read_bytes()).hexdigest() for p in report_dir.iterdir() if p.is_file()}==hashes
        removed.get_by_role('button',name=f'Restore {dataset["name"]} to campaign',exact=True).click()
        playwright.expect(card).to_have_count(1)
        playwright.expect(card.get_by_role('link',name=dataset['name'],exact=True)).to_have_attribute('href',f'#campaigns/workflows/{workflow["id"]}/mechanic_validation')
        page.locator('#workflow-campaign-detail').screenshot(path=str(tmp_path/'restored-mobile.png'))
        evidence(tmp_path,'workflow-link',dict(synthetic=True,workflow_id=workflow['id'],dataset_id=dataset['id'],
            cancel_no_delete=True,undo=True,durable_removed_state=True,restore=True,campaign_preserved=True,source_and_report_hashes_unchanged=hashes,temporary_server='Stopped by fixture teardown'))


def test_remove_legacy_link_does_not_reappear_from_saved_runs(page,portal,tmp_path):
    base=portal['url']
    with ResearchHTTPClient(base_url=base,timeout=120) as client:
        dataset=save(client);record=start_is(client,dataset)
        page.goto(base+'/#campaigns/consecutive_green_hold')
        card=page.locator('.workflow-real-dataset').filter(has_text=dataset['name'])
        playwright.expect(card).to_have_count(1)
        playwright.expect(card).to_contain_text('Mechanic validation · not started')
        page.once('dialog',lambda d:d.accept())
        card.get_by_role('button',name=f'Remove {dataset["name"]} from campaign',exact=True).click()
        playwright.expect(card).to_have_count(0)
        page.reload();playwright.expect(card).to_have_count(0)
        assert client.get('/api/strategies/consecutive_green_hold/datasets').json()['total']==1
        assert client.get('/api/backtests/'+record['id']).status_code==200
        assert any(s['id']=='consecutive_green_hold' for s in client.get('/api/strategies/library').json()['items'])
        page.locator('#workflow-campaign-detail').screenshot(path=str(tmp_path/'legacy-removed.png'))
        config=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',sample_split=dict(mode='percentage',is_percent=50),execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'))
        created=client.post('/api/campaign-workflows',json=config);assert created.status_code==201,created.text
        page.reload();playwright.expect(card).to_have_count(1)
        evidence(tmp_path,'legacy-link',dict(synthetic=True,dataset_id=dataset['id'],run_id=record['id'],legacy_fallback_stays_removed=True,new_explicit_workflow_relinks=True,results_retained=True))

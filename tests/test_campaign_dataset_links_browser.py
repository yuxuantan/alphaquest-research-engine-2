"""Real Campaigns permanent-delete preview and destructive confirmation journeys."""
from pathlib import Path
import json
import os
import shutil

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal,playwright
from test_campaign_mechanics import create_workflow,run_validation
from test_research_workflow import save,start_is
from test_campaign_dataset_links import seed_family,seed_nested_study


def evidence(tmp_path,name,data):
    (tmp_path/(name+'.json')).write_text(json.dumps(data,indent=2))
    if destination:=os.environ.get('ALPHAQUEST_LINK_EVIDENCE_DIR'):
        target=Path(destination)/name;target.mkdir(parents=True,exist_ok=True)
        for p in tmp_path.iterdir():
            if p.is_file() and p.suffix in ('.json','.png'):shutil.copyfile(p,target/p.name)


def test_permanent_workflow_preview_cancel_delete_and_reload(page,portal,tmp_path):
    base=portal['url'];campaign=base+'/#campaigns/consecutive_green_hold'
    with ResearchHTTPClient(base_url=base,timeout=120) as client:
        dataset,config,workflow=create_workflow(client);result=run_validation(client,workflow)
        folder=portal['app'].state.runs.root/result['run_id']
        other=client.post('/api/campaign-workflows',json=dict(config,execution_settings=dict(config['execution_settings'],slippage_ticks=2))).json()
        second=run_validation(client,other)
        from hashlib import sha256
        other_folder=portal['app'].state.runs.root/second['run_id']
        before={p.name:sha256(p.read_bytes()).hexdigest() for p in other_folder.iterdir() if p.is_file()}
        page.goto(campaign)
        card=page.locator(f'.workflow-real-dataset[data-workflow-id="{workflow["id"]}"]')
        other_card=page.locator(f'.workflow-real-dataset[data-workflow-id="{other["id"]}"]')
        playwright.expect(other_card).to_have_count(1)
        playwright.expect(card).to_contain_text('Created')
        button=card.get_by_role('button',name=f'Delete workflow {workflow["id"][:8]} for {dataset["name"]}',exact=True)
        button.click();dialog=page.get_by_role('dialog',name='Permanently delete workflow and results')
        playwright.expect(dialog).to_be_visible()
        playwright.expect(dialog).to_contain_text('1 workflow(s)')
        playwright.expect(dialog.get_by_role('button',name='Permanently delete',exact=True)).to_be_disabled()
        dialog.get_by_text('Backtest reports',exact=True).click()
        playwright.expect(dialog.get_by_role('link',name=result['run_id'],exact=True)).to_have_attribute('href',f'#backtests/report/{result["run_id"]}')
        dialog.get_by_text('Files to delete',exact=True).click();playwright.expect(dialog).to_contain_text('trades.csv')
        dialog.screenshot(path=str(tmp_path/'delete-preview.png'))
        dialog.get_by_role('button',name='Cancel',exact=True).click();assert folder.exists()
        playwright.expect(card).to_have_count(1)
        button.click();dialog.get_by_role('checkbox').check()
        dialog.get_by_role('button',name='Permanently delete',exact=True).click()
        playwright.expect(dialog).to_have_count(0);playwright.expect(card).to_have_count(0)
        assert not folder.exists() and client.get('/api/backtests/'+result['run_id']).status_code==404
        assert client.get('/api/campaign-workflows/'+workflow['id']).status_code==404
        assert client.get('/api/datasets/'+dataset['id']).status_code==200
        playwright.expect(other_card).to_have_count(1)
        assert client.get('/api/campaign-workflows/'+other['id']).json()==second
        assert before=={p.name:sha256(p.read_bytes()).hexdigest() for p in other_folder.iterdir() if p.is_file()}
        playwright.expect(page.locator('#workflow-campaign-detail')).to_contain_text('permanently deleted')
        assert page.get_by_role('button',name='Undo',exact=True).count()==0
        page.reload();playwright.expect(card).to_have_count(0)
        assert any(s['id']==config['strategy_id'] for s in client.get('/api/strategies/library').json()['items'])
        page.set_viewport_size(dict(width=390,height=844));page.locator('#workflow-campaign-detail').screenshot(path=str(tmp_path/'deleted-mobile.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        evidence(tmp_path,'permanent-workflow',dict(synthetic=True,dataset_id=dataset['id'],workflow_id=workflow['id'],run_id=result['run_id'],
            real_mechanics_run=True,preview_lists_files=True,cancel_preserves_all=True,unchecked_confirmation_disabled=True,
            files_and_results_deleted=True,durable_after_reload=True,campaign_and_dataset_preserved=True,other_same_dataset_workflow_id=other['id'],other_workflow_and_all_files_unchanged=True,temporary_server='Stopped by fixture teardown'))


def test_legacy_run_permanent_delete_and_busy_preview(page,portal,tmp_path):
    base=portal['url']
    with ResearchHTTPClient(base_url=base,timeout=120) as client:
        dataset=save(client);record=start_is(client,dataset)
        page.goto(base+'/#campaigns/consecutive_green_hold')
        card=page.locator('.workflow-real-dataset').filter(has_text=dataset['name'])
        card.get_by_role('button',name=f'Delete saved results for {dataset["name"]}',exact=True).click()
        dialog=page.get_by_role('dialog');playwright.expect(dialog).to_contain_text('0 workflow(s)')
        dialog.get_by_role('checkbox').check();dialog.get_by_role('button',name='Permanently delete',exact=True).click()
        playwright.expect(card).to_have_count(0)
        page.reload();playwright.expect(card).to_have_count(0)
        assert client.get('/api/backtests/'+record['id']).status_code==404
        assert client.get('/api/datasets/'+dataset['id']).status_code==200
        # A real workflow with synthetic running metadata is visibly protected.
        dataset,_,workflow=create_workflow(client)
        from uuid import uuid4
        with portal['app'].state.runs.connect() as db:
            db.execute("INSERT INTO mechanic_job_attempts VALUES (?,?,?,NULL,NULL,'running',NULL,NULL)",(uuid4().hex,workflow['id'],'2026-11-15'))
        page.reload();card=page.locator('.workflow-real-dataset').filter(has_text=dataset['name'])
        card.get_by_role('button',name=f'Delete workflow {workflow["id"][:8]} for {dataset["name"]}',exact=True).click()
        dialog=page.get_by_role('dialog');playwright.expect(dialog).to_contain_text('Deletion is blocked')
        dialog.get_by_role('checkbox').check();playwright.expect(dialog.get_by_role('button',name='Permanently delete',exact=True)).to_be_disabled()
        dialog.screenshot(path=str(tmp_path/'blocked-running-job.png'));dialog.get_by_role('button',name='Cancel',exact=True).click()
        evidence(tmp_path,'legacy-and-busy',dict(synthetic=True,legacy_run_deleted=True,dataset_kept=True,running_job_blocks_delete=True,temporary_server='Stopped by fixture teardown'))


def test_downstream_simulations_explicit_in_preview_and_cascade(page,portal,tmp_path):
    # Report membership is a labelled metadata graph fixture; no numerical claims.
    # Use the running app's actual store; seed uses normal mechanics execution and
    # explicit fixture-only phase files (not a duplicate product endpoint).
    with ResearchHTTPClient(base_url=portal['url'],timeout=120) as client:
        client.app=portal['app']
        dataset,config,w,result,batches,sim,analyses=seed_family(client)
        page.goto(portal['url']+'/#campaigns/consecutive_green_hold')
        page.get_by_role('button',name=f'Delete workflow {w["id"][:8]} for {dataset["name"]}',exact=True).click()
        dialog=page.get_by_role('dialog');playwright.expect(dialog).to_contain_text('1 downstream Prop Sim / portfolio simulation(s)')
        dialog.get_by_text('Downstream simulations that will also be deleted',exact=True).click()
        playwright.expect(dialog.get_by_role('link',name=sim['id'],exact=True)).to_have_attribute('href',f'#prop-sim?analysis={sim["id"]}')
        dialog.screenshot(path=str(tmp_path/'downstream-preview.png'))
        dialog.get_by_role('checkbox').check();dialog.get_by_role('button',name='Permanently delete',exact=True).click()
        playwright.expect(dialog).to_have_count(0)
        assert client.get('/api/prop-sim/'+sim['id']).status_code==404
        assert all(not (portal['app'].state.prop_analyses.root/aid).exists() for aid in analyses.values())
        evidence(tmp_path,'downstream-cascade',dict(synthetic=True,metadata_graph_only=True,real_mechanics_run=True,workflow_id=w['id'],simulation_id=sim['id'],analysis_ids=analyses,downstream_listed_before_confirmation=True,unshared_files_removed=True))


def test_dependent_nested_study_preview_cancel_confirm_and_reload(page,portal,tmp_path):
    with ResearchHTTPClient(base_url=portal['url'],timeout=120) as client:
        client.app=portal['app']
        dataset,config,w=create_workflow(client);result=run_validation(client,w)
        id,aid=seed_nested_study(client,w,result)
        folder=portal['app'].state.prop_analyses.root/aid
        page.goto(portal['url']+'/#campaigns/'+config['strategy_id'])
        button=page.get_by_role('button',name=f'Delete workflow {w["id"][:8]} for {dataset["name"]}',exact=True)
        button.click();dialog=page.get_by_role('dialog',name='Permanently delete workflow and results')
        playwright.expect(dialog).to_contain_text('1 dependent research study')
        dialog.get_by_text('Dependent research studies that will also be deleted',exact=True).click()
        playwright.expect(dialog).to_contain_text('SYNTHETIC dependent nested study')
        playwright.expect(dialog.get_by_role('link').filter(has_text=id)).to_have_attribute('href','#backtests/prop/job/'+aid)
        playwright.expect(dialog.get_by_role('button',name='Permanently delete',exact=True)).to_be_disabled()
        dialog.screenshot(path=str(tmp_path/'nested-study-preview.png'))
        dialog.get_by_role('button',name='Cancel',exact=True).click()
        assert folder.exists()
        with portal['app'].state.prop_analyses.connect() as db:assert db.execute('SELECT 1 FROM robust_research WHERE id=?',(id,)).fetchone()
        button.click();dialog.get_by_role('checkbox').check()
        dialog.get_by_role('button',name='Permanently delete',exact=True).click()
        playwright.expect(dialog).to_have_count(0)
        assert not folder.exists() and client.get('/api/research-campaigns/robust/'+id).status_code==404
        assert client.get('/api/datasets/'+dataset['id']).status_code==200
        assert any(c['id']==config['strategy_id'] for c in client.get('/api/strategies/library').json()['items'])
        page.reload();playwright.expect(page.locator(f'[data-workflow-id="{w["id"]}"]')).to_have_count(0)
        page.set_viewport_size(dict(width=390,height=844))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        evidence(tmp_path,'nested-study-cascade',dict(synthetic=True,metadata_graph_only=True,real_mechanics_run=True,
            workflow_id=w['id'],research_study_id=id,analysis_id=aid,study_name_and_report_link_visible=True,
            cancel_preserves_study=True,confirmation_required=True,study_checkpoints_and_unshared_files_removed=True,
            dataset_and_campaign_preserved=True,reload_persistent=True,temporary_server='Stopped by fixture teardown'))

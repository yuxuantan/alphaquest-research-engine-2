"""Existing portal drafts/templates preserve declarations before real research."""
from hashlib import sha256
import io
import json
import re
import zipfile

import httpx
from test_backtests_browser import browser, page, playwright
from test_research_procedure_browser import configure_research, portal, source_grid
from test_robust_research_api import save_grid


def open_controls(page):
    page.locator('#robust-workspace-controls > summary').click()


def save_draft(page, portal, name):
    page.locator('#workspace-save-name').fill(name)
    page.locator('#workspace-draft-save').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('revision 1 saved', timeout=15000)
    docs=page.request.get(portal['url']+'/api/research-workspace/drafts').json()['items']
    return next(row for row in docs if row['name']==name)


def test_draft_revision_template_fresh_preview_and_saved_research(page, portal, tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        dataset,job,records=save_grid(client)
    configure_research(page,portal,records);open_controls(page)
    draft=save_draft(page,portal,'SYNTHETIC editable research draft')
    assert 'campaign_id' not in draft['declaration']
    assert page.request.get(portal['url']+'/api/research-campaigns/robust').json()['items']==[]
    assert page.request.get(portal['url']+'/api/backtests').json()['total']==2
    # Another tab saves revision 2. The visible stale tab must retain its edits.
    body={key:draft[key] for key in ['kind','name','revision','declaration']}
    response=page.request.put(portal['url']+'/api/research-workspace/drafts/'+draft['id'],data=body)
    assert response.ok,response.text()
    page.locator('#robust-qualification-bootstrap_replicates').fill('800')
    page.locator('#workspace-draft-save').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('Your form edits remain here')
    playwright.expect(page.locator('#robust-qualification-bootstrap_replicates')).to_have_value('800')
    page.locator('#workspace-form-status').screenshot(path=str(tmp_path/'revision-conflict.png'))
    page.locator('#workspace-save-name').fill('SYNTHETIC preserved independent draft')
    page.locator('#workspace-draft-copy').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('revision 1 saved')
    drafts=page.request.get(portal['url']+'/api/research-workspace/drafts').json()['items']
    copy=next(row for row in drafts if row['name']=='SYNTHETIC preserved independent draft')
    assert copy['declaration']['qualification']['bootstrap_replicates']==800
    page.goto(portal['url']+'/#backtests/research')
    page.locator('#workspace-kind').select_option('draft')
    playwright.expect(page.locator('#workspace-items article')).to_have_count(2)
    page.locator('#workspace-items').screenshot(path=str(tmp_path/'draft-catalogue.png'))
    page.locator(f'#workspace-items article[data-id="{copy["id"]}"]').get_by_role('link',name='Continue draft').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('revision 1 loaded',timeout=15000)
    playwright.expect(page.locator('#robust-run')).to_be_disabled()
    playwright.expect(page.locator('#robust-qualification-bootstrap_replicates')).to_have_value('800')
    page.locator('#workspace-save-name').fill('SYNTHETIC reusable declaration settings')
    page.locator('#workspace-template-save').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('Settings template saved')
    template,=page.request.get(portal['url']+'/api/research-workspace/templates').json()['items']
    assert not {'sources','source_backtest_id','campaign_id','baselines','confirmed_backtest_count'} & template['settings'].keys()
    # Reuse settings on a different chosen source, then explicitly add its neighbor.
    page.goto(portal['url']+'/#backtests/prop/new/'+records[1]['id'])
    page.locator('#robust-configure > summary').click();open_controls(page)
    page.locator('#workspace-template-select').select_option(template['id'])
    page.locator('#workspace-template-apply').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('Template applied')
    assert page.locator('#robust-source-choices input:checked').count()==1
    page.locator('#robust-source-search').fill(records[0]['id'][:8])
    page.get_by_role('checkbox',name=re.compile(records[0]['id'][:8])).check()
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-run')).to_be_enabled(timeout=60000)
    page.locator('#robust-plan .research-timeline').screenshot(path=str(tmp_path/'checked-fold-timeline.png'))
    page.locator('#robust-run').click()
    playwright.expect(page.locator('#robust-result')).to_contain_text('Readiness:',timeout=180000)
    row,=page.request.get(portal['url']+'/api/research-campaigns/robust?source_id='+records[1]['id']).json()['items']
    record=page.request.get(portal['url']+'/api/research-campaigns/robust/'+row['campaign_id']).json()
    assert record['status']=='complete'
    assert record['declaration']['qualification']['bootstrap_replicates']==800
    assert len(record['plan']['candidates'])==2
    for fold in record['result']['folds']:
        assert sorted(float(candidate['metrics']['mean_session_net']) for candidate in fold['qualification']['candidates'])==[100,300]
    page.goto(portal['url']+'/#backtests/research')
    page.locator('#workspace-kind').select_option('nested')
    playwright.expect(page.locator('#workspace-items article')).to_have_count(1)
    page.locator('#workspace-items').screenshot(path=str(tmp_path/'saved-research-catalogue.png'))
    page.get_by_role('link',name='Open saved report',exact=True).click()
    playwright.expect(page.locator('#prop-heading-title')).to_contain_text('Nested research')
    page.locator('#prop-report-content').get_by_text('Outer fold 1 · parameter qualification plot',exact=True).click()
    page.locator('#prop-report-content .research-parameter-controls').first.screenshot(path=str(tmp_path/'saved-parameter-evidence.png'))
    page.locator('#prop-report-content').get_by_text('Forecast and actual receipt plots',exact=True).click()
    page.locator('#prop-report-content .research-scatter').first.screenshot(path=str(tmp_path/'saved-forecast-actual.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#prop-report-content .research-parameter-controls').first.screenshot(path=str(tmp_path/'parameter-evidence-narrow.png'))
    downloads={}
    for name,url in {'report.json':f'/api/prop-analyses/{record["analysis_id"]}/downloads/report.json',
        'analysis.zip':f'/api/prop-analyses/{record["analysis_id"]}/downloads/analysis.zip',
        'draft.json':'/api/research-workspace/drafts/'+copy['id'],
        'template.json':'/api/research-workspace/templates/'+template['id'],
        'SYNTHETIC-workspace-history.csv':'/api/datasets/'+dataset['id']+'/csv'}.items():
        response=page.request.get(portal['url']+url);assert response.ok,response.text()
        (tmp_path/name).write_bytes(response.body());downloads[name]=sha256(response.body()).hexdigest()
    assert downloads['SYNTHETIC-workspace-history.csv']==dataset['sha256']
    report=json.loads((tmp_path/'report.json').read_bytes())
    display_bounds=page.evaluate('''([plan,fold]) => {
      const container=document.createElement('div');document.body.append(container);
      const many={...plan,folds:Array.from({length:17},(_,index)=>({...plan.folds[0],index:index+1}))};
      researchVisuals.timeline(container,many);
      const timeline={disclosed:container.textContent.includes('first 16 of 17'),rows:container.querySelectorAll('tbody tr').length};
      container.replaceChildren();const config=plan.candidates[0],quality=fold.qualification.candidates[0];
      const candidates=Array.from({length:301},(_,index)=>({...config,id:'display-boundary-'+index,parameters:{...config.parameters,display_coordinate:index,boolean_control:index%2===0}}));
      researchVisuals.parameterEvidence(container,{candidates},{...fold,qualification:{candidates:candidates.map(candidate=>({...quality,candidate_id:candidate.id}))}});
      const choice=container.querySelector('select');choice.value=JSON.stringify([config.strategy_id,'display_coordinate']);choice.dispatchEvent(new Event('change'));
      const parameter={disclosed:container.textContent.includes('first 300 saved observations'),rows:container.querySelectorAll('tbody tr').length,booleanExcluded:![...choice.options].some(option=>option.value.includes('boolean_control'))};
      container.remove();return {timeline,parameter};
    }''',[record['plan'],record['result']['folds'][0]])
    assert display_bounds=={'timeline':{'disclosed':True,'rows':17},'parameter':{'disclosed':True,'rows':301,'booleanExcluded':True}}
    with zipfile.ZipFile(io.BytesIO((tmp_path/'analysis.zip').read_bytes())) as archive:
        for name,entry in report['files'].items():assert sha256(archive.read(name)).hexdigest()==entry['sha256']
    posts=[];page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
    page.reload();playwright.expect(page.locator('#prop-heading-title')).to_contain_text('Nested research');assert not posts
    page.goto(portal['url']+'/#backtests/research');playwright.expect(page.locator('#workspace-items article')).to_have_count(3);assert not posts
    (tmp_path/'evidence.json').write_text(json.dumps(dict(source_ids=[row['id'] for row in records],campaign_id=record['campaign_id'],analysis_id=record['analysis_id'],draft_id=copy['id'],template_id=template['id'],expected_inner_means=[100,300],engine_identity=record['plan']['engine_identity'],display_boundaries=display_bounds,downloads=downloads,reopen_posts=posts,source_research=records[0]['run_metadata']['research'],server='Owned portal fixture stopped temporary server.'),indent=2))


def test_baseline_draft_missing_source_and_explicit_rebind(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        dataset,job,records=save_grid(client)
    configure_research(page,portal,records)
    page.locator('#robust-preview').click();playwright.expect(page.locator('#robust-run')).to_be_enabled(timeout=60000)
    page.locator('#robust-baselines-configure > summary').click()
    page.locator('#robust-baseline-add').click()
    page.locator('#robust-baseline-1-id').fill('SYNTHETIC preserved one MNQ reference')
    open_controls(page);draft=save_draft(page,portal,'SYNTHETIC source-bound baseline draft')
    baseline,=draft['declaration']['baselines']
    page.locator('#workspace-template-save').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('source-bound baselines')
    assert page.request.get(portal['url']+'/api/research-workspace/templates').json()['items']==[]
    response=page.request.delete(portal['url']+'/api/backtests/batches/'+job['id']);assert response.ok,response.text()
    page.goto(portal['url']+'/#backtests/research?draft='+draft['id'])
    playwright.expect(page.get_by_role('heading',name='Rebind the unavailable anchor in a new draft')).to_be_visible()
    page.locator('#research-workspace-screen').screenshot(path=str(tmp_path/'missing-source-draft.png'))
    saved=page.request.get(portal['url']+'/api/research-workspace/drafts/'+draft['id']).json()
    assert saved['missing_sources'] and saved['declaration']['baselines']==[baseline]
    with httpx.Client(base_url=portal['url'],timeout=300) as client:
        replacement_job,replacements=source_grid(client,dataset)
    page.locator('#workspace-rebind-search').fill(replacements[0]['id'])
    playwright.expect(page.locator('#workspace-rebind-open')).to_be_enabled(timeout=15000)
    page.locator('#workspace-rebind-open').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('revision 1 loaded',timeout=15000)
    for original in records:page.get_by_role('checkbox',name=re.compile(original['id'][:8])).uncheck()
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-status')).to_contain_text('Plan needs attention')
    playwright.expect(page.locator('#robust-run')).to_be_disabled()
    page.locator('#robust-baselines-configure > summary').click()
    page.get_by_role('button',name='Remove saved reference').click()
    page.locator('#robust-preview').click();playwright.expect(page.locator('#robust-run')).to_be_enabled(timeout=60000)
    assert page.request.get(portal['url']+'/api/research-workspace/drafts/'+draft['id']).json()['declaration']['baselines']==[baseline]
    page.locator('#robust-plan').screenshot(path=str(tmp_path/'explicit-reference-rebind-check.png'))
    downloads={}
    for name,doc in [('original-draft.json',page.request.get(portal['url']+'/api/research-workspace/drafts/'+draft['id']).json()),('missing-source-draft.json',saved)]:
        raw=json.dumps(doc,indent=2).encode();(tmp_path/name).write_bytes(raw);downloads[name]=sha256(raw).hexdigest()
    (tmp_path/'evidence.json').write_text(json.dumps(dict(downloads=downloads,original_draft_id=draft['id'],preserved_baseline=baseline,removed_source_ids=[row['id'] for row in records],replacement_source_ids=[row['id'] for row in replacements],missing_sources_visible=True,source_bound_template_rejected=True,original_draft_unchanged=True,server='Owned temporary server stopped.'),indent=2))


def test_native_policy_draft_roundtrip_and_unsupported_membership_block(page,portal,tmp_path):
    from research_fixtures import ResearchHTTPClient
    from test_native_replay_api import source
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:
        original=source(client,days=7,payout=True)
    page.goto(portal['url']+'/#backtests/report/'+original['id'])
    page.locator('#report-prop-setup').click()
    page.locator('#robust-configure > summary').click()
    for key,value in dict(outer_train_sessions=4,outer_test_sessions=1,inner_train_sessions=1,
            inner_validation_sessions=1,purge_sessions=0,embargo_sessions=0,
            minimum_inner_folds=2,minimum_outer_folds=2).items():
        page.locator('#robust-'+key).fill(str(value))
    page.locator('#robust-economic-configure > summary').click()
    page.locator('#robust-economic-funded').check()
    page.locator('#robust-economic-funded-execution').select_option('native')
    page.locator('#robust-economic-funded-quantities').fill('1,3')
    prefix='robust-economic-funded-risk-'
    page.locator('.'+prefix+'sizing-mode').select_option('policies')
    page.locator('#robust-economic-funded-risk-caps').fill('20,40')
    page.locator('.'+prefix+'planning-commission').fill('0')
    page.locator('.'+prefix+'policy-dollars').fill('100')
    page.locator('.'+prefix+'add-policy').click()
    second=page.locator('.'+prefix+'sizing-policy').nth(1)
    second.locator('.'+prefix+'policy-kind').select_option('percentage_risk')
    second.locator('.'+prefix+'policy-percent').fill('0.2')
    second.locator('.'+prefix+'policy-reference').select_option('current_account_balance')
    page.locator('#robust-economic-funded-fields').get_by_text('Forecast sampling, seeds and model guards',exact=True).click()
    page.locator('#robust-economic-funded-simulations').fill('2')
    open_controls(page);draft=save_draft(page,portal,'SYNTHETIC native fixed and risk settings')
    policies=draft['declaration']['economic_studies'][0]['policies']
    assert [p['micros'] for p in policies]==[1,3,20,20,40,40]
    assert [p['sizing']['policy']['kind'] for p in policies[2:]]==['fixed_dollar_risk','percentage_risk']*2
    page.goto(portal['url']+'/#backtests/research?draft='+draft['id'])
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('revision 1 loaded',timeout=15000)
    playwright.expect(page.locator('#robust-run')).to_be_disabled()
    playwright.expect(second.locator('.'+prefix+'policy-reference')).to_have_value('current_account_balance')
    page.locator('#workspace-draft-save').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('revision 2 saved')
    saved=page.request.get(portal['url']+'/api/research-workspace/drafts/'+draft['id']).json()
    assert saved['declaration']==draft['declaration']
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-run')).to_be_enabled(timeout=60000)
    page.locator('#robust-economic-configure > summary').click()
    page.locator('#robust-economic-funded-native-fields').screenshot(path=str(tmp_path/'native-policy-grid-restored.png'))
    # A supported API declaration may be more expressive than this grid form.
    # Retain it unchanged and block conversion instead of expanding membership.
    noncart=json.loads(json.dumps(saved['declaration']))
    noncart['economic_studies'][0]['policies'].pop()
    response=page.request.post(portal['url']+'/api/research-workspace/drafts',data=dict(kind='nested',name='SYNTHETIC explicit non-Cartesian policies',declaration=noncart))
    assert response.ok,response.text()
    unsupported=response.json()
    page.goto(portal['url']+'/#backtests/research?draft='+unsupported['id'])
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('No combinations were added or removed',timeout=15000)
    playwright.expect(page.locator('#robust-preview')).to_be_disabled()
    playwright.expect(page.locator('#robust-run')).to_be_disabled()
    assert page.request.get(portal['url']+'/api/research-workspace/drafts/'+unsupported['id']).json()['declaration']==unsupported['declaration']
    page.locator('#workspace-form-status').screenshot(path=str(tmp_path/'unsupported-membership-preserved.png'))
    downloads={}
    for name,doc in [('native-draft.json',saved),('unsupported-membership-draft.json',unsupported)]:
        raw=json.dumps(doc,indent=2).encode();(tmp_path/name).write_bytes(raw);downloads[name]=sha256(raw).hexdigest()
    (tmp_path/'evidence.json').write_text(json.dumps(dict(downloads=downloads,source_id=original['id'],native_draft_id=draft['id'],unsupported_draft_id=unsupported['id'],native_policies=policies,exact_roundtrip=True,unsupported_membership_preserved=True,no_campaign_run=not page.request.get(portal['url']+'/api/research-campaigns/robust').json()['items'],server='Owned temporary server stopped.'),indent=2))

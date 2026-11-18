"""New percentage controls and one-click native journey in the existing portal."""
import json,time,os,shutil
import pytest
from test_backtests_browser import browser,page,playwright,portal
from research_fixtures import ResearchHTTPClient
from test_percentage_automatic import native_source_pair,install_admission_fixture


def test_percentage_form_one_run_progress_and_complete_oos(page,portal,monkeypatch,tmp_path):
 base=portal['url']
 progress=[];store=portal['app'].state.prop_analyses;original_update=store._update
 def observe(*args,**kwargs):
  if (details:=kwargs.get('progress_details')) and details.get('stage')=='native_execution':progress.append(dict(details))
  return original_update(*args,**kwargs)
 monkeypatch.setattr(store,'_update',observe)
 with ResearchHTTPClient(base_url=base,timeout=180) as client:source=native_source_pair(client)
 install_admission_fixture(monkeypatch,source)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'/#prop-sim?source='+source['source_backtest_id'])
 playwright.expect(page.locator('#prop-sim-source')).to_have_value('0',timeout=30000)
 page.locator('#prop-sim-search-kind').select_option('percentage_risk')
 assert page.locator('#prop-sim-evaluation_maximum_micros').is_disabled()
 assert page.locator('#prop-sim-evaluation-risk-maximum_contracts').input_value()=='60'
 page.locator('#prop-sim-profile').select_option('lucidflex-50k')
 assert page.locator('#prop-sim-evaluation-risk-maximum_contracts').input_value()=='40'
 page.locator('#prop-sim-profile').select_option('apex-50k-eod')
 for phase in ('evaluation','funded'):
  page.locator(f'#prop-sim-{phase}-risk-minimum').fill('.2')
  page.locator(f'#prop-sim-{phase}-risk-maximum').fill('.3')
  page.locator(f'#prop-sim-{phase}-risk-step').fill('.1')
 page.locator('#prop-sim-simulations').fill('8');page.locator('#prop-sim-block_weekdays').select_option('1');page.locator('#prop-sim-funded_horizon_calendar_days').fill('9')
 page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
 page.locator('#prop-sim-start_date').fill('2026-01-12');page.locator('#prop-sim-commission_per_mnq_side').fill('0')
 playwright.expect(page.locator('#prop-sim-preflight')).to_contain_text('Evaluation: 0.2, 0.3%')
 page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'percentage-config.png'))
 with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/prop-sim'),timeout=180000) as response:page.locator('#prop-sim-run').click()
 assert response.value.status==202,response.value.text();saved=response.value.json();id=saved['id']
 assert saved['configuration']['automatic'] and 'evaluation_maximum_micros' not in saved['configuration']
 page.goto(base+'/#jobs')
 with ResearchHTTPClient(base_url=base,timeout=180) as client:
  deadline=time.monotonic()+180
  while True:
   saved=client.get('/api/prop-sim/'+id).json()
   if all(s['stage'] in ('complete','error','no_eligible_candidates') for s in saved['automation']['phases'].values()):break
   assert time.monotonic()<deadline,saved
   time.sleep(.1)
 assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
 page.goto(base+'/#prop-sim?analysis='+id)
 for phase in ('evaluation','funded'):
  playwright.expect(page.locator(f'#prop-sim-{phase}-validation .prop-sim-auto-status')).to_contain_text('Workflow: complete',timeout=30000)
  playwright.expect(page.locator(f'#prop-sim-{phase}-validation .prop-sim-current-assessment .prop-evidence-candidate').first).to_contain_text('0.2%')
  playwright.expect(page.locator(f'#prop-sim-{phase}-conclusion')).to_contain_text('evidence gaps',ignore_case=True)
  playwright.expect(page.locator(f'#prop-sim-{phase}-validation .observed-bar-diagnostics').first).to_contain_text('Observed-bar replay · gaps accepted')
 playwright.expect(page.locator('#prop-sim-evaluation-conclusion')).to_contain_text('0.2%')
 assert 'undefined' not in page.locator('#prop-sim-evaluation-results').inner_text()
 page.locator('#prop-sim-evaluation-results').screenshot(path=str(tmp_path/'percentage-evaluation.png'))
 page.set_viewport_size(dict(width=390,height=844));assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
 assert not errors,errors
 assert progress and all(p['eta_basis']=='completed-worker-paths-v1' for p in progress)
 assert all(type(p['completed']) is int and p['completed']<=p['total'] for p in progress)
 assert any(p['eta_status']=='warming_up' and p['eta_seconds'] is None for p in progress)
 assert any(p['completed']==p['total'] and p['eta_seconds']==0 and p['active_workers']==0 for p in progress)
 (tmp_path/'simulation.json').write_text(json.dumps(saved,indent=2))
 (tmp_path/'actual-path-progress.json').write_text(json.dumps(progress,indent=2))
 with ResearchHTTPClient(base_url=base,timeout=180) as client:
  for phase,campaign in saved['campaign_ids'].items():
   response=client.get(f'/api/research-campaigns/{campaign}/exports/analysis.zip')
   assert response.status_code==200
   (tmp_path/(phase+'-is.zip')).write_bytes(response.content)
 if destination:=os.environ.get('ALPHAQUEST_NATIVE_PROGRESS_EVIDENCE_DIR'):
  target=__import__('pathlib').Path(destination);target.mkdir(parents=True,exist_ok=True)
  for p in tmp_path.iterdir():
   if p.is_file() and p.suffix in ('.json','.png','.zip'):shutil.copyfile(p,target/p.name)


def test_shared_progress_labels_percentage_paths_and_refits(page,portal):
 page.goto(portal['url']+'/#prop-sim')
 page.wait_for_function('typeof window.renderPropProgress==="function"')
 page.evaluate("""()=>{const p=document.createElement('div');p.id='progress-example';document.body.append(p);window.renderPropProgress(p,{stage:'native_execution',sizing_label:'0.2% · initial configured capital',completed:500,total:1000,unit:'account paths',worker_count:4,active_workers:4,elapsed_seconds:10,eta_seconds:10},'running');}""")
 playwright.expect(page.locator('#progress-example')).to_contain_text('Native account execution · 0.2%')
 playwright.expect(page.locator('#progress-example')).to_contain_text('500 / 1,000 account paths')
 assert 'undefined MNQ' not in page.locator('#progress-example').inner_text()

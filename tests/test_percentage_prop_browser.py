"""New percentage controls and one-click native journey in the existing portal."""
import json,time,os,shutil
from threading import Event
import pytest
from test_backtests_browser import browser,page,playwright,portal
from research_fixtures import ResearchHTTPClient
from test_percentage_automatic import native_source_pair,install_admission_fixture


def test_run_button_names_the_blocker_and_recovers_after_correction(page,portal,monkeypatch,tmp_path):
 # Real synthetic backtest source; prior qualification is the labeled fixture.
 # This form-only journey starts no prop calculation; the next test runs both phases.
 with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:source=native_source_pair(client)
 install_admission_fixture(monkeypatch,source)
 page.goto(portal['url']+'/#prop-sim')
 run=page.locator('#prop-sim-run');check=page.locator('#prop-sim-check');notice=page.locator('#prop-sim-status')
 playwright.expect(notice).to_contain_text('Cannot run: Choose a qualified campaign configuration.')
 page.locator('#prop-sim-simulations').fill('32')
 playwright.expect(run).to_be_disabled()
 playwright.expect(notice).to_contain_text('Choose a qualified campaign configuration.')
 page.locator('#prop-sim-source').select_option('0')
 playwright.expect(run).to_be_enabled()
 page.locator('#prop-sim-search-kind').select_option('percentage_risk')
 page.locator('#prop-sim-funded-risk-minimum').fill('0')
 playwright.expect(run).to_be_disabled();playwright.expect(check).to_be_disabled()
 playwright.expect(notice).to_contain_text('Cannot run: Funded sizing: Declare positive, aligned minimum, maximum and step')
 page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'funded-grid-blocker.png'))
 for key,value in [('minimum','.25'),('maximum','.5'),('step','.25')]:
  page.locator('#prop-sim-funded-risk-'+key).fill(value)
 playwright.expect(run).to_be_enabled()
 page.locator('#prop-sim-funded-risk-maximum_contracts').fill('2.5')
 playwright.expect(notice).to_contain_text('Funded sizing · Whole-MNQ ceiling:')
 playwright.expect(run).to_be_disabled()
 page.locator('#prop-sim-funded-risk-maximum_contracts').fill('40')
 page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
 page.locator('#prop-sim-seed').fill('')
 playwright.expect(notice).to_contain_text('Cannot run: Random seed:')
 playwright.expect(run).to_be_disabled()
 page.locator('#prop-sim-seed').fill('42')
 playwright.expect(run).to_be_enabled()
 page.locator('#prop-sim-commission_per_mnq_side').fill('')
 playwright.expect(notice).to_contain_text('MNQ commission per contract per side · USD:')
 page.locator('#prop-sim-commission_per_mnq_side').fill('0.51')
 page.locator('#prop-sim-evaluation-risk-minimum').fill('0')
 playwright.expect(notice).to_contain_text('Cannot run: Evaluation sizing:')
 # Unused hidden percentage fields must not block a fixed-contract search.
 page.locator('#prop-sim-search-kind').select_option('fixed_contracts')
 playwright.expect(run).to_be_enabled()
 page.locator('#prop-sim-evaluation_minimum_micros').fill('11')
 playwright.expect(notice).to_contain_text('Evaluation sizing: Maximum MNQ must be at least Minimum MNQ.')
 playwright.expect(run).to_be_disabled()
 page.locator('#prop-sim-evaluation_minimum_micros').fill('1')
 playwright.expect(run).to_be_enabled();playwright.expect(check).to_be_enabled()
 playwright.expect(notice).not_to_contain_text('Cannot run:')
 page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'corrected-form-ready.png'))
 with portal['app'].state.prop_analyses.connect() as db:assert db.execute('SELECT count(*) FROM analyses').fetchone()[0]==0
 if destination:=os.environ.get('ALPHAQUEST_PROP_FORM_EVIDENCE_DIR'):
  target=__import__('pathlib').Path(destination);target.mkdir(parents=True,exist_ok=True)
  for name in ('funded-grid-blocker.png','corrected-form-ready.png'):shutil.copyfile(tmp_path/name,target/name)
  (target/'form-verification.json').write_text(json.dumps(dict(synthetic=True,source_backtest_id=source['source_backtest_id'],
   missing_source_explained=True,funded_grid_error_explained=True,integer_ceiling_error_explained=True,
   required_seed_and_commission_explained=True,unused_risk_fields_ignored=True,inverted_fixed_range_explained=True,
   corrected_form_enabled=True,prop_simulation_launched=False),indent=2))


def test_percentage_form_one_run_progress_and_complete_oos(page,portal,monkeypatch,tmp_path):
 base=portal['url']
 progress=[];store=portal['app'].state.prop_analyses;original_update=store._update
 entered,release=Event(),Event()
 def observe(*args,**kwargs):
  if (details:=kwargs.get('progress_details')) and details.get('stage')=='native_execution':progress.append(dict(details))
  result=original_update(*args,**kwargs)
  if details and details.get('stage')=='native_execution' and not entered.is_set():
   entered.set()
   assert release.wait(40),'Browser did not release the actual first native path'
  return result
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
 try:
  live=page.locator('#prop-sim-evaluation-live-progress')
  playwright.expect(live).to_contain_text('remaining for this size Estimating…',timeout=30000)
  playwright.expect(live.get_by_role('progressbar')).to_be_visible()
  assert page.locator('#prop-sim-evaluation-progress').is_hidden()
  live.screenshot(path=str(tmp_path/'actual-prop-sim-startup-progress.png'))
  with ResearchHTTPClient(base_url=base,timeout=30) as client:
   job=client.get('/api/prop-sim/'+id).json()['phases']['evaluation']['analysis_id']
  page.goto(base+'/#jobs/prop_analysis/'+job)
  live=page.locator('#jobs-detail-content .prop-confidence-progress')
  playwright.expect(live).to_contain_text('remaining for this size Estimating…')
  live.screenshot(path=str(tmp_path/'actual-job-startup-progress.png'))
 finally:release.set()
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

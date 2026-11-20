"""New percentage controls and one-click native journey in the existing portal."""
import json,time,os,shutil
from threading import Event
import pytest
from test_backtests_browser import browser,page,playwright,portal
from research_fixtures import ResearchHTTPClient
from test_percentage_automatic import native_source_pair,install_admission_fixture


@pytest.mark.parametrize('profile_id',['apex-50k-eod','lucidflex-50k'])
def test_saved_trade_percentage_product_journey(page,portal,monkeypatch,tmp_path,profile_id):
 from test_saved_trade_simulation import saved_source_pair
 # Scale the actual synthetic input prices, not recorded trade outcomes. The
 # normal strategy/backtest captures a $200/MNQ stop and $40 adverse excursion.
 from decimal import Decimal
 import native_replay_fixtures as prices
 original_prices=prices.source_bytes
 def wide_prices(**kwargs):
  raw=original_prices(**kwargs).decode().splitlines();rows=[raw[0]]
  for line in raw[1:]:
   cells=line.split(',');cells[2:6]=[str(Decimal(100)+(Decimal(v)-100)*20) for v in cells[2:6]];rows.append(','.join(cells))
  return ('\n'.join(rows)+'\n').encode()
 with monkeypatch.context() as m:
  m.setattr(prices,'source_bytes',wide_prices)
  with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:source=saved_source_pair(client)
 install_admission_fixture(monkeypatch,source,app=portal['app'])
 entered,release=Event(),Event();store=portal['app'].state.prop_analyses;original=store._update
 def hold(*a,**kw):
  result=original(*a,**kw)
  if (kw.get('progress_details') or {}).get('stage')=='saved_trade_execution' and not entered.is_set():
   entered.set();assert release.wait(40)
  return result
 monkeypatch.setattr(store,'_update',hold)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(portal['url']+'/#prop-sim?source='+source['source_backtest_id'])
 playwright.expect(page.locator('#prop-sim-source')).to_have_value('0',timeout=30000)
 page.get_by_role('link',name='Open IS source backtest',exact=True).click()
 playwright.expect(page).to_have_url(portal['url']+'/#backtests/report/'+source['source_backtest_id'])
 playwright.expect(page.locator('#report-prop-setup')).to_be_visible()
 page.get_by_role('navigation',name='Main navigation',exact=True).get_by_role('link',name='Prop Sim',exact=True).click()
 page.locator('#prop-sim-source').select_option('0')
 page.locator('#prop-sim-profile').select_option(profile_id)
 if profile_id=='lucidflex-50k':
  playwright.expect(page.locator('#prop-sim-form')).to_contain_text('Inactivity expiry is disabled; manual maintenance activity is assumed and its small costs are omitted.')
 page.locator('#prop-sim-search-kind').select_option('percentage_risk')
 for phase in ('evaluation','funded'):
  for key,value in [('minimum','.01'),('maximum','20.01'),('step','20')]:page.locator(f'#prop-sim-{phase}-risk-{key}').fill(value)
  page.locator(f'#prop-sim-{phase}-account-limit-action').select_option('exit_at_limit' if phase=='evaluation' else 'skip')
  page.locator(f'#prop-sim-{phase}-minimum-one-contract').check()
 assert page.locator('[id$="risk-constrain_to_account_cushion"]').count()==0
 page.locator('#prop-sim-simulations').fill('8');page.locator('#prop-sim-block_weekdays').select_option('1')
 page.locator('#prop-sim-funded_horizon_calendar_days').fill('9')
 page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
 page.locator('#prop-sim-start_date').fill('2026-01-12');page.locator('#prop-sim-commission_per_mnq_side').fill('0')
 page.locator('#prop-sim-check').click()
 playwright.expect(page.locator('#prop-sim-status')).to_contain_text('Source compatible',timeout=30000)
 page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'saved-trade-configuration.png'))
 with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/prop-sim'),timeout=180000) as response:page.locator('#prop-sim-run').click()
 assert response.value.status==202,response.value.text();id=response.value.json()['id']
 try:
  live=page.locator('#prop-sim-evaluation-live-progress')
  playwright.expect(live).to_contain_text('Saved-trade account simulation',timeout=30000)
  live.screenshot(path=str(tmp_path/'saved-trade-live-progress.png'))
 finally:release.set()
 with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:
  deadline=time.monotonic()+180
  while True:
   saved=client.get('/api/prop-sim/'+id).json()
   if all(s['stage'] in ('complete','error','no_eligible_candidates') for s in saved['automation']['phases'].values()):break
   assert time.monotonic()<deadline,saved
   time.sleep(.1)
  assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
  for phase in ('evaluation','funded'):
   dataset=client.get('/api/datasets/'+source['dataset']['id']+'/csv');assert dataset.status_code==200
   (tmp_path/'SYNTHETIC-trade-handling-bars.csv').write_bytes(dataset.content)
   job=saved['phases'][phase]['analysis_id']
   for name in ('report.json','analysis.zip','saved_trade_model.json','sizing_decisions.csv'):
    r=client.get(f'/api/prop-analyses/{job}/downloads/{name}');assert r.status_code==200,r.text
    (tmp_path/(phase+'-'+name)).write_bytes(r.content)
   results=json.loads((tmp_path/(phase+'-report.json')).read_text())['calculations']['candidates']
   small=next(r for r in results if r['manifest']['configuration']['sizing']['policy']['risk_percent']=='0.01')
   assert small['quantity_summary']['risk_budget_override_rate']==1
   assert Decimal(small['quantity_summary']['mean_actual_risk_percent'])==Decimal('.4')
   large=next(r for r in results if r['manifest']['configuration']['sizing']['policy']['risk_percent']=='20.01')
   if phase=='evaluation':assert large['quantity_summary']['account_limit_exit_rate']==1
   else:assert large['quantity_summary']['skipped_rate']==1
   state=saved['automation']['phases'][phase]
   r=client.get(f"/api/prop-sim/{id}/validation/{phase}/{state['oos_request_id']}")
   assert r.status_code==200,r.text;(tmp_path/(phase+'-oos.json')).write_text(r.text)
   expected=dict(account_limit_action='exit_at_limit' if phase=='evaluation' else 'skip',minimum_one_contract=True)
   assert saved['configuration'][phase+'_trade_handling']==expected
   for row in r.json()['calculations']['candidates']:
    assert row['configuration']['sizing']['trade_handling']==expected
    assert 'risk_budget_override_rate' in row['quantity_summary']
 page.goto(portal['url']+'/#prop-sim?analysis='+id)
 for phase in ('evaluation','funded'):
  playwright.expect(page.locator('#prop-sim-'+phase+'-conclusion')).to_contain_text('evidence gaps',ignore_case=True,timeout=30000)
  playwright.expect(page.locator('#prop-sim-'+phase+'-results [data-trade-behavior="IS"]')).to_contain_text('Skipped opportunities')
  playwright.expect(page.locator(f'[data-trade-handling-warning={phase}]')).to_contain_text('risk-budget overrides')
  page.locator('#prop-sim-'+phase+'-insight').get_by_role('button',name='Review trade-handling impact').click()
  page.locator('#prop-sim-'+phase+'-results [data-trade-behavior="IS"]').screenshot(path=str(tmp_path/(phase+'-trade-handling.png')))
  playwright.expect(page.locator('#prop-sim-'+phase+'-results [data-trade-behavior="OOS / assessment"]')).to_contain_text('Account-limit exits')
 playwright.expect(page.locator('#prop-sim-results')).not_to_contain_text('NaN')
 page.locator('#prop-sim-results').screenshot(path=str(tmp_path/'saved-trade-results.png'))
 page.set_viewport_size(dict(width=390,height=844));assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
 assert not errors,errors
 if destination:=os.environ.get('ALPHAQUEST_SAVED_TRADE_EVIDENCE_DIR'):
  target=__import__('pathlib').Path(destination);target.mkdir(parents=True,exist_ok=True)
  for p in tmp_path.iterdir():
   if p.is_file():shutil.copyfile(p,target/p.name)
  (target/'journey.json').write_text(json.dumps(dict(synthetic=True,source=source,simulation=saved,expected='Both phases complete; seven OOS sessions produce evidence gaps, not a false GO.'),indent=2))


def test_run_button_names_the_blocker_and_recovers_after_correction(page,portal,monkeypatch,tmp_path):
 # Real synthetic backtest source; prior qualification is the labeled fixture.
 # This form-only journey starts no prop calculation; the next test runs both phases.
 with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:source=native_source_pair(client)
 install_admission_fixture(monkeypatch,source,app=portal['app'])
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



def test_shared_progress_labels_percentage_paths_and_refits(page,portal):
 page.goto(portal['url']+'/#prop-sim')
 page.wait_for_function('typeof window.renderPropProgress==="function"')
 page.evaluate("""()=>{const p=document.createElement('div');p.id='progress-example';document.body.append(p);window.renderPropProgress(p,{stage:'native_execution',sizing_label:'0.2% · initial configured capital',completed:500,total:1000,unit:'account paths',worker_count:4,active_workers:4,elapsed_seconds:10,eta_seconds:10},'running');}""")
 playwright.expect(page.locator('#progress-example')).to_contain_text('Native account execution · 0.2%')
 playwright.expect(page.locator('#progress-example')).to_contain_text('500 / 1,000 account paths')
 assert 'undefined MNQ' not in page.locator('#progress-example').inner_text()

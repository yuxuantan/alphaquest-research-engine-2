"""Main one-click orchestration with real native source/phase math.

Only prior campaign admission is a labeled test fixture. Provider simulations,
immutable freezes, OOS execution and inadequate-history verdicts are actual.
"""
from copy import deepcopy
from datetime import datetime,timedelta
from uuid import uuid4
import json,time
import pytest
from alphaquest.app import create_app
from research_fixtures import ResearchClient
from native_replay_fixtures import source_bytes,parameter_values
from test_optimization import wait_job
from test_prop_sim_automatic import wait_automatic


def native_source_pair(client):
 raw=source_bytes(days=7,payout=True).decode().splitlines();later=[]
 for line in raw[1:]:
  cells=line.split(',');cells[0]=(datetime.strptime(cells[0],'%m/%d/%Y')+timedelta(days=21)).strftime('%m/%d/%Y');later.append(','.join(cells))
 upload=client.post('/api/datasets',params=dict(filename='SYNTHETIC-native-percentage-automatic.csv',name='SYNTHETIC native percentage orchestration',symbol='MNQ',source_timezone='UTC',tick_size='.25',point_value='2'),content=('\n'.join(raw+later)+'\n').encode());assert upload.status_code==201,upload.text
 values=parameter_values();request=dict(dataset_id=upload.json()['id'],method='exhaustive',workers=1,automatic_prop=False,strategy_id='vwap_pullback_risk_sizing',parameter_ranges={k:dict(start=v,end=v,step='0' if isinstance(v,str) else 0) for k,v in values.items()},execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'),sample_split=dict(mode='dates',is_start='2026-01-04',is_end='2026-01-13',oos_start='2026-01-25',oos_end='2026-02-03'))
 response=client.post('/api/optimizations',json=request);assert response.status_code==202,response.text
 job=wait_job(client,response.json()['id']);assert job['status']=='complete',job
 row,=client.get('/api/optimizations/'+job['id']+'/results').json()['items'];source=client.get('/api/backtests/'+row['run_id']).json()
 oos=client.post('/api/backtests/'+source['id']+'/oos',json=dict(request_id=uuid4().hex));assert oos.status_code==201,oos.text
 selection=dict(workflow_id=uuid4().hex,oos_job_id=uuid4().hex,monte_carlo_id=uuid4().hex,candidate=1)
 return dict(selection=selection,source_backtest_id=source['id'],oos_report_id=oos.json()['id'],strategy_id=source['run_metadata']['strategy']['id'],dataset=upload.json(),parameters=values,plan=source['run_metadata']['research']['plan'],broad_trial=1,narrow_trial=1,qualification='SYNTHETIC prior-admission test fixture; phase calculations are actual')


def install_admission_fixture(monkeypatch,source):
 import alphaquest.prop_sim as module
 def qualified(request,selection):
  assert selection.model_dump(mode='json')==module.Selection.model_validate(source['selection']).model_dump(mode='json')
  return deepcopy(source)
 monkeypatch.setattr(module,'qualified',qualified)
 monkeypatch.setattr(module,'candidates',lambda request:dict(items=[deepcopy(source)],unavailable=[],maximum_selected_configurations=1))


def configuration(source,profile):
 return dict(request_id=uuid4().hex,automatic=True,selections=[source['selection']],profile_id=profile,
  search_kind='percentage_risk',evaluation_percentage_grid=dict(minimum='0.2',maximum='0.3',step='0.1',maximum_contracts=60 if profile=='apex-50k-eod' else 40),funded_percentage_grid=dict(minimum='0.2',maximum='0.3',step='0.1',maximum_contracts=40),simulations=8,block_weekdays=1,seed=42,start_date='2026-01-12',funded_horizon_calendar_days=9,commission_per_mnq_side='0')

@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_one_run_percentage_both_phases_frozen_oos_and_durable_reopen(tmp_path,monkeypatch,profile):
 with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
  source=native_source_pair(client);install_admission_fixture(monkeypatch,source);body=configuration(source,profile)
  response=client.post('/api/prop-sim',json=body);assert response.status_code==202,response.text
  saved=wait_automatic(client,response.json()['id'],timeout=180)
  assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
  assert saved['configuration']['search_kind']=='percentage_risk' and 'evaluation_maximum_micros' not in saved['configuration']
  for phase in ('evaluation','funded'):
   state=saved['automation']['phases'][phase];assert state['selection']['candidates']
   assert all(c['sizing_axis']['kind']=='percentage_risk' for c in state['selection']['candidates'])
   campaign=client.app.state.campaigns.get(saved['campaign_ids'][phase]);frozen=campaign['frozen']
   result=client.get(f"/api/prop-sim/{saved['id']}/validation/{phase}/{state['oos_request_id']}?summary=true");assert result.status_code==200,result.text
   calc=result.json()['calculations'];assert calc['winner'] is None and not calc['ranking']
   assert {r['frozen_candidate_id'] for r in calc['candidates']}==set(frozen['candidate_ids'])
   assert all(r['prop_qualification']['status']=='INSUFFICIENT_EVIDENCE' for r in calc['candidates']) # Seven OOS sessions cannot qualify.
   assert all(r['configuration']['sizing']['policy']['kind']=='percentage_risk' and r['quantity_summary'] for r in calc['candidates'])
   id=client.app.state.campaigns.assessments(campaign['campaign_id'])[0]['analysis_id']
   assert client.app.state.prop_analyses.native_children_unchanged(client.app.state.runs,id)
   assert client.get(f'/api/prop-analyses/{id}/downloads/analysis.zip').status_code==200
  again=client.post('/api/prop-sim',json=body);assert again.status_code==202 and again.json()['id']==saved['id']
  (tmp_path/'automatic.json').write_text(json.dumps(saved,indent=2))


def test_full_native_confidence_branch_publishes_all_10000_refits(tmp_path,monkeypatch):
 # Explicit numerical-branch fixture only. The preceding product tests retain
 # the real 12-month/100-trade evidence rejection for this same short history.
 import alphaquest.prop.oos_qualification as qualification
 monkeypatch.setattr(qualification,'evidence',lambda *args:[dict(label='SYNTHETIC numerical-branch exercise; production evidence minima tested separately',actual=7,required=7,passed=True)])
 with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
  source=native_source_pair(client);install_admission_fixture(monkeypatch,source)
  response=client.post('/api/prop-sim',json=configuration(source,'apex-50k-eod'));assert response.status_code==202,response.text
  saved=wait_automatic(client,response.json()['id'],timeout=240)
  assert all(s['stage']=='complete' for s in saved['automation']['phases'].values()),saved
  for phase in ('evaluation','funded'):
   state=saved['automation']['phases'][phase]
   report=client.get(f"/api/prop-sim/{saved['id']}/validation/{phase}/{state['oos_request_id']}").json()
   calc=report['calculations'];assert calc['qualification_native_model']=='native-percentage-two-history-v1'
   assert all(row['prop_qualification']['historical_replicates']==10000 for row in calc['candidates'])
   assert all(row['prop_qualification']['status']=='GO' for row in calc['candidates'])
   assert all(len(family['replicates'])==10000 for family in calc['qualification_bootstrap'])
   assert all(len(family['execution']['inner_path_counts'])==2 and family['execution']['inner_path_counts']==[8,8] for family in calc['qualification_bootstrap'])
   for family in calc['qualification_bootstrap']:
    assert all(v==1 for row in family['replicates'] for v in row['ratios'].values())
   assert client.app.state.prop_analyses.fingerprint(report['id'])

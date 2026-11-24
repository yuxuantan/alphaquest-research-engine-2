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


def install_admission_fixture(monkeypatch,source,app=None):
 import alphaquest.prop_sim as module
 def qualified(request,selection):
  assert selection.model_dump(mode='json')==module.Selection.model_validate(source['selection']).model_dump(mode='json')
  return deepcopy(source)
 monkeypatch.setattr(module,'qualified',qualified)
 monkeypatch.setattr(module,'candidates',lambda request:dict(items=[deepcopy(source)],unavailable=[],maximum_selected_configurations=1))
 # Explicit prior-qualification fixtures cannot be reconstructed in a spawned
 # production reader. Only these tests substitute the process boundary; real
 # process/qualification coverage is in test_prop_sim_preparation.py.
 from alphaquest.prop_sim_preparation import PropSimPreparation,evidence_identity
 def fixture_process(owner,operation,payload,checkpoint=lambda:None):
  checkpoint()
  if operation=='candidates':return dict(result=module.candidates(owner.request))
  if operation=='qualified':return dict(result=qualified(owner.request,module.Selection.model_validate(payload)))
  checked,definitions=module._check(owner.request,module.Configuration.model_validate(payload))
  checkpoint()
  return dict(checked=checked,definitions={k:v.model_dump(mode='json') for k,v in definitions.items()},token=evidence_identity(owner.request))
 monkeypatch.setattr(PropSimPreparation,'_execute',fixture_process)
 if app is not None:
  declaration=dict(dataset=source['dataset'])
  with app.state.runs.connect() as db:
   db.execute('INSERT OR IGNORE INTO campaign_workflows VALUES (?,?,?,?,?)',(source['selection']['workflow_id'],source['selection']['workflow_id'],source['strategy_id'],source['dataset']['id'],json.dumps(dict(declaration=declaration))))



def configuration(source,profile):
 return dict(request_id=uuid4().hex,automatic=True,selections=[source['selection']],profile_id=profile,
  search_kind='percentage_risk',evaluation_percentage_grid=dict(minimum='0.2',maximum='0.3',step='0.1',maximum_contracts=60 if profile=='apex-50k-eod' else 40),funded_percentage_grid=dict(minimum='0.2',maximum='0.3',step='0.1',maximum_contracts=40),simulations=8,block_weekdays=1,seed=42,start_date='2026-01-12',funded_horizon_calendar_days=9,commission_per_mnq_side='0')

# Main-portal percentage execution is now exercised by
# test_saved_trade_simulation.py and the saved-trade browser journey.
# Keep these source/configuration fixtures for standalone native API regressions.

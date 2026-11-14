"""Percentage policies through ordinary source/check/run/report/freeze routes."""
from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4
import pytest
from alphaquest.app import create_app
from research_fixtures import ResearchClient
from test_native_replay_api import source,wait
from test_native_phase_campaigns import declaration,source_with_complete_oos
from alphaquest.prop.sizing_search import PercentageGrid

@pytest.mark.parametrize('phase',['evaluation','funded'])
@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_percentage_native_phase_normal_product(tmp_path,phase,profile):
 with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
  original=source(client,days=7,payout=True)
  request=declaration(client,original,phase)
  request['profile'].update(profile_id=profile,rule_version=__import__('alphaquest.prop.phase_profiles',fromlist=['rule_version']).rule_version(profile))
  if profile=='lucidflex-50k' and phase=='evaluation':request['profile']['activation_fee']='0'
  request['simulation'].update(simulations=8)
  if phase=='evaluation':request['sampling'].update(chain_simulations=8,chain_seed=1732)
  request['search_settings']['native_execution']['model']='native_percentage_observed_blocks_v2'
  request['costs']=dict(mode='override',broker='test',per_side='0',instrument='auto')
  grid=PercentageGrid(minimum='0.1',maximum='0.2',step='0.1',maximum_contracts=40)
  request['sources'][0].update(sizes=[40],sizing_policies=[asdict(p) for p in grid.policies(dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))])
  response=client.post('/api/research-campaigns',json=request);assert response.status_code==201,response.text
  id=response.json()['campaign_id']
  run=client.post(f'/api/research-campaigns/{id}/run');assert run.status_code==202,run.text
  wait(client,run.json()['analysis_id'])
  report=client.get(f"/api/prop-analyses/{run.json()['analysis_id']}/downloads/report.json").json()
  rows=report['calculations']['candidates'];assert len(rows)==2
  assert {r['manifest']['configuration']['sizing']['policy']['risk_percent'] for r in rows}=={'0.1','0.2'}
  assert all(len(r['native_forecast']['paths'])==8 for r in rows)
  assert all(r['quantity_summary']['opportunities']>0 for r in rows)
  assert all(r['quantity_summary']['admitted_entries']>0 and r['quantity_summary']['mean_requested_risk_budget'] is not None for r in rows)
  assert all(len(r['native_forecast']['captures'])==1 for r in rows)
  assert all(r['manifest']['configuration']['micros']==40 for r in rows)
  selected=report['calculations']['frontier' if phase=='evaluation' else 'ranking']
  if selected:
   freeze=client.post(f'/api/research-campaigns/{id}/freeze',json=dict(candidate_ids=selected[:2],rationale='Synthetic percentage policy, not a fixed cap.'))
   assert freeze.status_code==200,freeze.text
  assert client.get(f'/api/research-campaigns/{id}/exports/analysis.zip').status_code==200

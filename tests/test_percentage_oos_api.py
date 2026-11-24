"""Frozen percentage OOS point forecasts and actual chronological reports."""
from dataclasses import asdict
from uuid import uuid4
import pytest
from alphaquest.app import create_app
from research_fixtures import ResearchClient
from test_native_replay_api import wait
from test_native_phase_campaigns import declaration,source_with_complete_oos
from alphaquest.prop.sizing_search import PercentageGrid

@pytest.mark.parametrize('phase,legacy_extra_coverage',[('evaluation',False),('funded',False),('funded',True)])
def test_frozen_percentage_oos_keeps_policy_and_produces_both_models(tmp_path,phase,legacy_extra_coverage,monkeypatch):
 with ResearchClient(create_app(tmp_path/'datasets.sqlite3')) as client:
  source=source_with_complete_oos(client);body=declaration(client,source,phase)
  if legacy_extra_coverage:
   # Legacy coverage metadata can overstate the last saved CME session beyond
   # the frozen split. The real in-window source data remains unchanged.
   from copy import deepcopy
   original=client.app.state.runs.get
   def legacy(id):
    record=original(id)
    if record and (record.get('run_metadata',{}).get('research') or {}).get('phase')=='oos':
     record=deepcopy(record);record['period_end_utc']='2026-02-02T23:00:00+00:00'
    return record
   monkeypatch.setattr(client.app.state.runs,'get',legacy)
  body['is_window']['last_session']='2026-01-09'
  body['simulation']['simulations']=8
  body['search_settings']['native_execution'].update(model='native_percentage_observed_blocks_v2',horizon_calendar_days=7)
  body['search_settings']['calendar'].update(start_dates=['2026-01-12'],coverage_end='2026-01-19')
  if phase=='evaluation':body['sampling'].update(chain_simulations=8,chain_seed=1732)
  else:body['search_settings']['horizon_calendar_days']=7
  body['costs']=dict(mode='override',broker='test',per_side='0',instrument='auto')
  grid=PercentageGrid(minimum='0.1',maximum='0.1',step='0.1',maximum_contracts=40)
  body['sources'][0].update(sizes=[40],sizing_policies=[asdict(p) for p in grid.policies(dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0'))])
  result=client.post('/api/research-campaigns',json=body);assert result.status_code==201,result.text
  id=result.json()['campaign_id'];run=client.post(f'/api/research-campaigns/{id}/run');assert run.status_code==202,run.text;wait(client,run.json()['analysis_id'])
  report=client.get(f"/api/prop-analyses/{run.json()['analysis_id']}/downloads/report.json").json()
  selected=report['calculations']['frontier' if phase=='evaluation' else 'ranking'];assert selected
  freeze=client.post(f'/api/research-campaigns/{id}/freeze',json=dict(candidate_ids=selected,rationale='Native percentage fixed before OOS.'));assert freeze.status_code==200,freeze.text
  result=client.post(f'/api/research-campaigns/{id}/assessments',json=dict(request_id=uuid4().hex));assert result.status_code==202,result.text
  wait(client,result.json()['analysis_id']);oos=client.get(f"/api/prop-analyses/{result.json()['analysis_id']}/downloads/report.json").json()
  row,=oos['calculations']['candidates'];assert row['frozen_candidate_id']==selected[0]
  assert row['configuration']['period']['last_session']=='2026-01-30'
  assert row['manifest']['configuration']['sizing']==report['calculations']['candidates'][0]['manifest']['configuration']['sizing']
  assert len(row['native_forecast']['paths'])==8 and row['native_chronological_replay']['historical_paths']==1
  assert oos['calculations']['winner'] is None and not oos['calculations']['ranking'] and not oos['calculations']['frontier']
  assert row['is_comparison'] and row['quantity_summary']['opportunities']>0

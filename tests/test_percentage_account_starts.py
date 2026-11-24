"""Actual observed-clock sensitivity, not the modeled source sampler."""
from dataclasses import replace
from decimal import Decimal
from test_percentage_native_bootstrap import inputs_and_candidate
from alphaquest.prop.native_account_starts import run
import pytest

@pytest.mark.parametrize('phase',['evaluation','funded'])
def test_native_start_replays_original_source_day_and_preserves_quantity(phase):
 inputs,candidate,search=inputs_and_candidate(phase)
 policy=dict(start_plan=dict(horizon_calendar_days=1,starts=['2026-01-05']))
 result=run(inputs,candidate,search,policy,lambda:None,lambda v:None)
 path,=result['paths'];actual=path['result']
 assert path['start_date']=='2026-01-05' and path['cutoff_exclusive']=='2026-01-06'
 assert actual['historical_paths']==1 and actual['execution_counts']['completed_trades']==1
 assert actual['sizing_decisions'][0]['quantity']==10
 assert Decimal(actual['trading_profit'])==3000
 assert actual['sizing_decisions'][0]['sizing_decision_time_utc'].startswith('2026-01-05')
 if phase=='funded':assert actual['cash_received']==0 and Decimal(actual['equity'])==3000
 else:assert actual['pass_date']=='2026-01-05' and Decimal(actual['paid_evaluation_fees'])==30

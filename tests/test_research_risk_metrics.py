from copy import deepcopy
from decimal import Decimal
import pytest
from alphaquest.risk_metrics import planned_unit_loss,trade_diagnostic,summarize

EXEC=dict(tick_size='.25',point_value='2',slippage_ticks=0,commission_per_contract_per_side='.5')
TRADE=dict(trade_id=1,side='long',quantity=2,entry_time_utc='2026-01-05T16:01:00Z',exit_time_utc='2026-01-05T16:10:00Z',entry_fill_price='100',net_pnl='123',
 sizing_decision=dict(timestamp_utc='2026-01-05T16:00:00Z',reference_price='100',execution_timing='next_open'),
 initial_stop=dict(price='80',known_at_utc='2026-01-05T16:00:00Z',basis='strategy_decision'))

@pytest.mark.parametrize('point,expected',[('2','41.0'),('20','401.0'),('50','1001.0')])
def test_instrument_units_and_net_costs_once(point,expected):
 row=trade_diagnostic(TRADE,dict(EXEC,point_value=point));assert Decimal(row['planned_risk_per_contract'])==Decimal(expected)
 assert row['available']
 if point=='2':assert Decimal(row['planned_net_r'])==Decimal('1.5')
 assert row['net_pnl']=='123'

def test_short_slippage_and_invalid_stop_timing():
 assert planned_unit_loss('100','110','short',tick_size='.25',point_value='2',entry_slippage_ticks=1,stop_exit_slippage_ticks=1,commission_per_side='.5')==22
 bad=deepcopy(TRADE);bad['initial_stop']['known_at_utc']='2026-01-05T16:00:01Z'
 assert trade_diagnostic(bad,EXEC)['reason']=='invalid_initial_risk'
 missing=deepcopy(TRADE);missing['initial_stop']=None
 assert trade_diagnostic(missing,EXEC)['reason']=='initial_stop_unavailable'
 for stop in ('100','101','79.9'):
  bad=deepcopy(TRADE);bad['initial_stop']['price']=stop
  assert not trade_diagnostic(bad,EXEC)['available']

def test_gapped_fill_is_diagnostic_and_does_not_change_pre_entry_risk():
 trade=dict(TRADE,entry_fill_price='79')
 row=trade_diagnostic(trade,EXEC);assert Decimal(row['planned_risk_per_contract'])==Decimal(41)
 assert row['initial_stop_adverse_to_actual_fill'] is False

def source(trades):
 return dict(source=dict(native_manifest=dict(execution_settings=EXEC,run_metadata=dict(dataset=dict(source_timezone='UTC')),
  period_start_utc='2026-01-01T00:00:00Z',period_end_utc='2026-03-31T23:59:00Z')),trades=trades)

def test_complete_months_include_zero_trades_and_missing_coverage_is_not_hidden():
 row=summarize(source([TRADE]));assert row['coverage']['complete']
 assert row['summary']['mean_planned_net_r']=='1.5'
 assert [r['trades'] for r in row['complete_months']]==[1,0,0]
 bad=deepcopy(TRADE);bad.update(trade_id=2,initial_stop=None)
 result=summarize(source([TRADE,bad]));assert result['status']=='partial'
 assert result['summary']['mean_planned_net_r'] is None
 assert result['complete_months'][0]['total_planned_net_r'] is None
 assert result['coverage']['missing_reasons']=={'initial_stop_unavailable':1}

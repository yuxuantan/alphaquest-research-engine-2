"""Source-based calendar boundaries and causal streaming qualifications."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import csv
import io
from pathlib import Path
import pytest

from alphaquest.session_calendar import CT, calendar_path, load_calendar, session_date
from alphaquest.execution import Trade, execute
from alphaquest.strategies.vwap_pullback_risk_sizing import VwapPullbackRiskSizing, source_fingerprint
from test_vwap_pullback import CONFIG, bar, parameters, scenario
from test_inferred_session_close import retime


@pytest.mark.parametrize('day,close,cutoff',[
 ('2021-01-18','12:00','11:55'),('2021-09-06','12:00','11:55'),
 ('2024-01-15','12:00','11:55'),('2024-09-02','12:00','11:55'),
 ('2024-07-03','12:15','12:10'),('2024-11-29','12:15','12:10'),
 ('2021-04-02','08:15','08:10'),('2023-04-07','08:15','08:10'),
 ('2018-12-05','08:30','08:25'),('2025-01-09','08:30','08:25'),
 ('2026-04-03','08:15','08:10'),('2021-12-31','16:00','15:55')])
def test_reviewed_notice_expectations(day,close,cutoff):
 plan=load_calendar().plan(date.fromisoformat(day))
 assert plan.close.strftime('%H:%M')==close
 assert plan.cutoff.strftime('%H:%M')==cutoff


def test_configured_cutoff_caps_calendar_and_chicago_dst_is_not_a_fixed_offset():
 calendar=load_calendar()
 for day in ('2024-01-15','2024-09-02'):
  assert calendar.plan(date.fromisoformat(day),1130).cutoff.strftime('%H:%M')=='11:30'
 assert calendar.plan(date(2024,1,15)).cutoff.astimezone(timezone.utc).hour==17
 assert calendar.plan(date(2024,9,2)).cutoff.astimezone(timezone.utc).hour==16


def test_holiday_evening_uses_next_session_and_weekends_are_closed():
 calendar=load_calendar()
 assert calendar.plan(date(2024,12,25)).cutoff is None
 stamp=datetime(2024,12,25,17,1,tzinfo=CT)
 assert session_date(stamp)==date(2024,12,26)
 assert calendar.plan(session_date(stamp)).allows(stamp)
 assert not calendar.plan(date(2024,12,28)).allows(datetime(2024,12,28,9,tzinfo=CT))


@pytest.mark.parametrize('day',[date(2015,12,31),date(2026,11,3),date(2027,1,4)])
def test_unknown_coverage_rejects(day):
 with pytest.raises(ValueError,match='does not cover'):
  load_calendar().plan(day)


def test_calendar_blocks_a_morning_signal_on_a_full_closure():
 rows=[retime(row,date(2024,3,29)) for row in scenario()]
 events=list(execute(rows,VwapPullbackRiskSizing(parameters(use_eod_flat=True),execution_config=CONFIG),CONFIG))
 assert not [event for event in events if isinstance(event,Trade)]


def test_no_future_bar_is_pulled_before_current_decision_and_suffix_does_not_move_cutoff():
 p=parameters(use_eod_flat=True)
 rows=scenario()
 decisions=[]
 strategy=VwapPullbackRiskSizing(p,execution_config=CONFIG)
 original=strategy.on_bar
 def observed(current,position):
  result=original(current,position);decisions.append((current.bar_number,result));return result
 strategy.on_bar=observed
 def guarded():
  for index,row in enumerate(rows):
   if index:assert decisions[-1][0]==rows[index-1].bar_number
   yield row
 list(execute(guarded(),strategy,CONFIG))
 first_cutoff=strategy.session_flattening['examples'][0]['order_cutoff']
 shortened=VwapPullbackRiskSizing(p,execution_config=CONFIG)
 list(execute(rows[:123],shortened,CONFIG))
 assert shortened.session_flattening['examples'][0]['order_cutoff']==first_cutoff
 assert shortened.session_flattening['lookahead'] is False


def test_pending_entry_does_not_jump_into_a_later_session():
 from test_inferred_session_close import session_rows
 rows=session_rows()[:122]
 rows.append(retime(bar(123,17,1),date(2024,1,15)))
 events=list(execute(rows,VwapPullbackRiskSizing(parameters(use_eod_flat=True),execution_config=CONFIG),CONFIG))
 assert not [event for event in events if isinstance(event,Trade)]


@pytest.mark.parametrize('change',[
 {'closure_type':'full_close','close_time_local':'12:00'},
 {'close_time_local':'25:00'}, {'timezone':'CST'}, {'coverage_end':'2026-12-31'},
 {'source_url':''}, {'verified_on':'11/02/2026'},])
def test_invalid_file_rejected_instead_of_silent_regular_hours(tmp_path,change):
 rows=list(csv.DictReader(calendar_path().open()))
 rows[1].update(change)
 p=tmp_path/'bad.csv'
 with p.open('w',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
 with pytest.raises(ValueError,match='Invalid NQ session calendar'):load_calendar(p)


def test_csv_snapshot_is_immutable_and_calendar_edits_change_strategy_identity(tmp_path,monkeypatch):
 import alphaquest.session_calendar as module
 import alphaquest.strategies.vwap_pullback_risk_sizing as strategy_module
 raw=calendar_path().read_bytes()
 p=tmp_path/'calendar.csv';p.write_bytes(raw)
 snapshot=load_calendar(p)
 original=source_fingerprint()
 p.write_bytes(raw.replace(b'No session ending',b'Reviewed session ending',1))
 assert snapshot.sha256!=load_calendar(p).sha256
 monkeypatch.setattr(strategy_module,'calendar_path',lambda:p)
 assert source_fingerprint()!=original
 p.unlink()
 assert snapshot.plan(date(2024,1,15)).cutoff.hour==11
 with pytest.raises(ValueError,match='Invalid NQ session calendar'):load_calendar(p)

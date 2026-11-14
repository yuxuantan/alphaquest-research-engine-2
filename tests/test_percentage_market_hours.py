from datetime import date,datetime,time,timezone
from dataclasses import asdict,replace
from test_native_forecast_profiles import catalogue,CONFIG,targets,request
from native_replay_fixtures import parameters
from alphaquest.prop.native_market_hours import required_holding_minutes
from alphaquest.prop.native_draws import _encoded_bar,_json
from alphaquest.session_calendar import CT,load_calendar


def test_observed_bar_encoding_is_byte_identical_to_legacy():
 for b in catalogue.__wrapped__().bars[::37]:assert _encoded_bar(b)==(_json(asdict(b))+'\n').encode()


def test_reviewed_halt_ends_on_20210628_and_only_flat_tail_is_exempt():
 p=replace(parameters(),entry_start_time=900,eod_flat_time=1540)
 for day,paused in [(date(2021,6,25),True),(date(2021,6,28),False)]:
  close=datetime.combine(day,time(16),CT).astimezone(timezone.utc);required=required_holding_minutes(day,p,close)
  stamp=lambda h,m:datetime.combine(day,time(h,m),CT).astimezone(timezone.utc)
  assert (stamp(15,16) not in required)==paused
  assert stamp(15,15) in required and stamp(15,31) in required
  assert stamp(15,41) in required and stamp(15,42) not in required

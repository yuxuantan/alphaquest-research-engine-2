"""Reviewed NQ/MNQ minute coverage for native observed-source admission.

Close-labelled bars during a venue pause are not missing observations. This
module neither inserts prices nor changes strategy callbacks/calendar closes.
"""
from datetime import date,datetime,time,timedelta,timezone
from ..session_calendar import CT

VERSION='nq-observed-holding-minute-coverage-v1'
SOURCE='https://www.cmegroup.com/notices/electronic-trading/2021/06/20210614.html'
PAUSE_REMOVED=date(2021,6,28)


def required_holding_minutes(day,parameters,scheduled_close):
    start=datetime.combine(day,time(parameters.entry_start_time//100,parameters.entry_start_time%100),CT).astimezone(timezone.utc)
    configured=datetime.combine(day,time(parameters.eod_flat_time//100,parameters.eod_flat_time%100),CT).astimezone(timezone.utc)
    cutoff=min(configured,scheduled_close-timedelta(minutes=parameters.close_buffer_minutes))
    # Require the cutoff and actual next-open execution bar. Every later source
    # row is retained; flat post-liquidation rows are not invented requirements.
    end=min(cutoff+timedelta(minutes=1),scheduled_close)
    result=set()
    while start<=end:
        local=start.astimezone(CT).time()
        paused=day<PAUSE_REMOVED and time(15,15)<local<=time(15,30)
        if not paused:result.add(start)
        start+=timedelta(minutes=1)
    # If flattening falls in the reviewed halt, require the first resumed bar.
    if day<PAUSE_REMOVED and time(15,15)<=cutoff.astimezone(CT).time()<=time(15,30):
        resumed=datetime.combine(day,time(15,31),CT).astimezone(timezone.utc)
        if resumed<=scheduled_close:result.add(resumed)
    return result

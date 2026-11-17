"""Reviewed NQ/MNQ minute coverage, checked against actual replay exposure.

Close-labelled bars during a venue pause are not missing observations. This
module neither inserts prices nor changes strategy callbacks/calendar closes.
"""
from datetime import date,datetime,time,timedelta,timezone
from ..session_calendar import CT

VERSION='nq-observed-exposure-minute-coverage-v2'
SOURCE='https://www.cmegroup.com/notices/electronic-trading/2021/06/20210614.html'
PAUSE_REMOVED=date(2021,6,28)


def missing_minute_ranges(day, stamps, scheduled_close):
    """Compact original-source holes; no prices, sessions or bars are inserted."""
    seen=set(stamps)
    minute=datetime.combine(day-timedelta(days=1),time(17,1),CT).astimezone(timezone.utc)
    result=[]
    while minute<=scheduled_close:
        local=minute.astimezone(CT).time()
        paused=day<PAUSE_REMOVED and time(15,15)<local<=time(15,30)
        if not paused and minute not in seen:
            if result and minute==result[-1][1]+timedelta(minutes=1):
                result[-1]=(result[-1][0],minute)
            else:result.append((minute,minute))
        minute+=timedelta(minutes=1)
    return tuple(result)


class ObservedExposureCoverage:
    """Check only real missing minutes, even when acceleration skips known bars.

    Calls precede order fills. Exposure describes the position/working stop
    entries left by the previous actual execution event, never a saved trade.
    """
    def __init__(self, ranges):
        self.ranges=tuple(sorted(ranges));self.previous=None;self.cursor=0

    def check(self, stamp, exposure):
        previous=self.previous
        self.previous=stamp
        if previous is None:return
        while self.cursor<len(self.ranges) and self.ranges[self.cursor][1]<=previous:
            self.cursor+=1
        if self.cursor>=len(self.ranges):return
        first,_=self.ranges[self.cursor]
        if first<=stamp and exposure:
            missing=max(first,previous+timedelta(minutes=1))
            local=missing.astimezone(CT)
            raise ValueError(f'Native replay cannot cross missing one-minute prices while {exposure}: '
                f'{local.isoformat()} America/Chicago ({missing.isoformat()} UTC). '
                'Restore the missing source bars or use a complete source window; no interpolation, '
                'silent session removal or replacement path is allowed.')


def required_holding_minutes(day,parameters,scheduled_close):
    from ..strategy_sizing import definition_for_parameters, native_settings
    support=definition_for_parameters(parameters).sizing
    flat_time,buffer=native_settings(parameters)
    entry_start,prior_day=support.holding_start(parameters)
    start=datetime.combine(day-timedelta(days=int(prior_day)),time(entry_start//100,entry_start%100),CT).astimezone(timezone.utc)
    configured=datetime.combine(day,time(flat_time//100,flat_time%100),CT).astimezone(timezone.utc)
    cutoff=min(configured,scheduled_close-timedelta(minutes=buffer))
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

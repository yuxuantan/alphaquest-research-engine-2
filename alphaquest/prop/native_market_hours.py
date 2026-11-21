"""Reviewed NQ/MNQ minute gaps, diagnosed against actual replay exposure.

Close-labelled bars during a venue pause are not missing observations. This
module neither inserts prices nor changes strategy callbacks/calendar closes.
"""
from datetime import date,datetime,time,timedelta,timezone
from ..session_calendar import CT

VERSION='nq-observed-bars-gap-diagnostics-v3'
ASSUMPTION='Replay original observed bars only. No fills, excursions or price-driven account-rule events are reconstructed inside missing minutes; execution resumes at the next observed Open/OHLC. Gaps may understate risk.'
SOURCE='https://www.cmegroup.com/notices/electronic-trading/2021/06/20210614.html'
PAUSE_REMOVED=date(2021,6,28)


def scheduled_pause_bar_labels(day):
    """UTC close labels within the historical CME equity-index pause."""
    if day >= PAUSE_REMOVED:
        return frozenset()
    first = datetime.combine(day, time(15, 16), CT).astimezone(timezone.utc)
    return frozenset(first + timedelta(minutes=i) for i in range(15))


def missing_minute_ranges(day, stamps, scheduled_close):
    """Compact original-source holes; no prices, sessions or bars are inserted."""
    seen=set(stamps)
    paused=scheduled_pause_bar_labels(day)
    minute=datetime.combine(day-timedelta(days=1),time(17,1),CT).astimezone(timezone.utc)
    result=[]
    while minute<=scheduled_close:
        if minute not in paused and minute not in seen:
            if result and minute==result[-1][1]+timedelta(minutes=1):
                result[-1]=(result[-1][0],minute)
            else:result.append((minute,minute))
        minute+=timedelta(minutes=1)
    return tuple(result)


class ObservedExposureCoverage:
    """Record source holes crossed by execution, including accelerated callbacks.

    Known observed bars skipped by acceleration are never treated as gaps. The
    first observation establishes a boundary; leading/trailing source omissions
    remain in the source inventory, not invented execution encounters.
    """
    def __init__(self, ranges):
        self.ranges=tuple(sorted(ranges));self.previous=None;self.cursor=0

    def check(self, stamp, exposure):
        previous=self.previous
        self.previous=stamp
        if previous is None:return ()
        result=[]
        while self.cursor<len(self.ranges):
            first,last=self.ranges[self.cursor]
            if first>=stamp:break
            self.cursor+=1
            if last<=previous:continue
            first=max(first,previous+timedelta(minutes=1))
            last=min(last,stamp-timedelta(minutes=1))
            if first>last:continue
            result.append(dict(first_missing_utc=first.isoformat(),last_missing_utc=last.isoformat(),
                resumed_at_source_utc=stamp.isoformat(),missing_minutes=int((last-first).total_seconds()//60)+1,
                exposure=exposure or 'flat'))
        return tuple(result)


def summarize_observed_coverage(paths):
    """Compact diagnostics only; trading P&L is not trader cash or a loss estimate."""
    from decimal import Decimal
    from ..decimal_math import add
    values=[p['observed_bar_diagnostics'] for p in paths if 'observed_bar_diagnostics' in p]
    if not values:return None
    counts=('gap_encounters','missing_minutes_crossed','position_gap_encounters',
        'working_entry_gap_encounters','flat_gap_encounters','gap_exposed_completed_trades')
    result=dict(version=VERSION,mode='observed_bars_diagnostic_only',assumption=ASSUMPTION,
        paths=len(values),paths_with_exposure=sum(v['position_gap_encounters']+v['working_entry_gap_encounters']>0 for v in values),
        longest_gap_minutes=max(v['longest_gap_minutes'] for v in values),
        count_scope='Summed encounters across simulated account paths, not unique source gaps.')
    result.update({key:sum(v[key] for v in values) for key in counts})
    net=Decimal(0)
    for value in values:net=add(net,Decimal(value['gap_exposed_trade_net_pnl']))
    result['gap_exposed_trade_net_pnl']=str(net)
    result['pnl_scope']='Signed actual trading P&L of completed trades exposed to a source gap; not the effect of missing data or trader receipts.'
    return result


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
    paused=scheduled_pause_bar_labels(day)
    while start<=end:
        if start not in paused:result.add(start)
        start+=timedelta(minutes=1)
    # If flattening falls in the reviewed halt, require the first resumed bar.
    if day<PAUSE_REMOVED and time(15,15)<=cutoff.astimezone(CT).time()<=time(15,30):
        resumed=datetime.combine(day,time(15,31),CT).astimezone(timezone.utc)
        if resumed<=scheduled_close:result.add(resumed)
    return result

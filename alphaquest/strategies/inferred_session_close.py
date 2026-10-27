"""Backtest-only lookahead: infer a Chicago session's close from observed bars.

Buffer one 17:00-to-16:00 session, never the full dataset. A truncated dataset
is intentionally treated as an early close under this research assumption.
"""

from datetime import datetime, time, timedelta
from itertools import groupby
from zoneinfo import ZoneInfo


CT = ZoneInfo("America/Chicago")
MINUTES_BEFORE_CLOSE = 5


def session_date(bar):
    local = bar.timestamp_utc.astimezone(CT)
    return local.date() + (timedelta(days=1) if local.time() >= time(17) else timedelta())


def session_bars(bars, strategy):
    """Set each session's executable cutoff before yielding its first bar.

    Ignore evening quotes and any 16:00-17:00 maintenance-period bars when
    inferring the close. Select the last actual bar at/before the cutoff; no
    fabricated timestamp or price. If none exists, disallow entries throughout
    the session. Grouping uses the local session-ending date, not CME trade date.
    """
    latest = strategy.parameters.eod_flat_time
    for day, group in groupby(bars, key=session_date):
        observed = list(group)
        daytime = [bar for bar in observed
                   if (local := bar.timestamp_utc.astimezone(CT)).date() == day
                   and local.time() <= time(16)]
        target = cutoff = last = None
        if daytime:
            last = daytime[-1].timestamp_utc
            normal = datetime.combine(day, time(latest // 100, latest % 100), CT)
            target = min(normal, last - timedelta(minutes=MINUTES_BEFORE_CLOSE))
            cutoff = next((bar.timestamp_utc for bar in reversed(observed)
                           if bar.timestamp_utc <= target), None)
        strategy._session_cutoff = cutoff
        strategy._session_plan_ready = True
        strategy._record_session_close(day, last, target, cutoff)
        yield from observed

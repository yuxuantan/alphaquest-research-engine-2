"""Read-only display units for saved batch results."""

import csv
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from .drawdown import saved_period


def trading_day_duration(folder, record):
    """Longest trade-close drawdown in elapsed weekday session transitions.

    Reconstruct every peak/recovery: elapsed seconds alone cannot distinguish
    weekends, or identify the longest drawdown on a weekday clock. Retain idle
    weekdays, as in the prop simulation. Same-session durations are zero.
    """
    metadata = record.get('run_metadata', {})
    calendar = metadata.get('strategy', {}).get('session_calendar', {})
    cme = calendar.get('id') in ('cme_nq', 'cme_es')
    zone = ZoneInfo('America/Chicago' if cme else
                    metadata.get('dataset', {}).get('source_timezone', 'UTC'))

    def clock(timestamp):
        local = timestamp.astimezone(zone).replace(tzinfo=None)
        day = (local + timedelta(hours=7) if cme else local).date()
        weeks, remainder = divmod(day.toordinal(), 7)
        return weeks * 5 + min(remainder, 5)

    if 'period_start_utc' in record and 'period_end_utc' in record:
        start, end = (datetime.fromisoformat(record[key]) for key in
                      ('period_start_utc', 'period_end_utc'))
    else:
        start, end = saved_period(folder / record.get('artifacts', {}).get('report', 'report.json'))
    peak = Decimal(record['summary']['initial_capital'])
    peak_day = clock(start)
    longest = 0
    underwater = False
    count = 0
    last = start
    with (folder / 'equity.csv').open(newline='', encoding='utf-8') as source:
        for ordinal, point in enumerate(csv.DictReader(source)):
            if int(point['trade_number']) != ordinal:
                raise ValueError('Saved trade-close equity is not contiguous.')
            equity = Decimal(point['equity'])
            if not ordinal:
                if equity != peak:raise ValueError('Saved starting equity differs from the run.')
            else:
                timestamp = datetime.fromisoformat(point['exit_time_utc'])
                if timestamp < last or timestamp > end:
                    raise ValueError('Saved trade-close timestamps are outside the run.')
                last = timestamp
                day = clock(timestamp)
                if underwater or equity < peak:
                    longest = max(longest, day - peak_day)
                if equity >= peak:
                    peak, peak_day, underwater = equity, day, False
                else:
                    underwater = True
            count += 1
    if count != record['summary']['trades_taken'] + 1:
        raise ValueError('Saved trade-close equity count differs from the run.')
    if underwater:longest = max(longest, clock(end) - peak_day)
    return longest

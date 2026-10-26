"""Reusable export expectations and bounded, source-bound coverage inspection.

Calendar schedules are a pinned model, not live exchange certification. Observed
spacing is only a suggestion: a chosen export profile defines expected bars.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from math import gcd
import re
from typing import Literal
from zoneinfo import ZoneInfo

from ._report_reader import InputError, ReportReader, require
from .calendar import CalendarDay, DataWindow, SessionCalendar, local_utc, microseconds
from .rules import _canonical_json, _digest
from .types import Value, _integer, _require


CALENDAR_VERSION = "pandas_market_calendars 5.5.0 CME_Equity"
CALENDAR_SOURCES = (
    "https://www.cmegroup.com/trading-hours.html",
    "https://github.com/rsheftel/pandas_market_calendars/blob/v5.5.0/pandas_market_calendars/calendars/cme.py",
)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class SourceSessionProfile(Value):
    id: str
    version: str
    name: str
    calendar: Literal["cme_equity_model", "weekday_approximation"]
    window: Literal["cash_hours", "overnight", "custom"]
    bar_interval_seconds: int
    first_bar_time: time | None = None
    last_bar_time: time | None = None
    timezone: Literal["America/New_York"] = "America/New_York"

    def __post_init__(self):
        super(SourceSessionProfile, self).__post_init__()
        _integer("bar_interval_seconds", self.bar_interval_seconds)
        _require(re.fullmatch(r"[a-z][a-z0-9_]{0,79}", self.id) is not None and len(self.name) <= 160, "Invalid source-session profile ID/name.")
        _require(self.bar_interval_seconds <= 86400, "Bar interval exceeds one day.")
        _require(self.version == "1.0.0", "Unsupported source-session profile version.")
        _require((self.first_bar_time is not None and self.last_bar_time is not None) if self.window == "custom"
                 else self.first_bar_time is None and self.last_bar_time is None, "Only custom windows require first/last bar-close labels.")
        _require(self.calendar != "weekday_approximation" or self.window == "custom", "Weekday approximation requires a custom window.")
        if self.window == "custom":
            def offset(t): return (t.hour * 3600 + t.minute * 60 + t.second - 18 * 3600) % 86400
            duration = offset(self.last_bar_time) - offset(self.first_bar_time)
            _require(duration >= 0 and duration % self.bar_interval_seconds == 0, "Custom labels are reversed or not aligned to bar cadence.")
            _require(all(t.microsecond == 0 and offset(t) < 23 * 3600 for t in (self.first_bar_time, self.last_bar_time)), "Custom labels must be whole seconds outside the maintenance break.")

    @property
    def sha256(self):
        return _digest(self.to_dict())


def profiles():
    return tuple(SourceSessionProfile(f"cme_{window}_{seconds}", "1.0.0",
        f"CME equity {label} · {seconds // 60}-minute bars", "cme_equity_model", window, seconds)
        for window, label in (("cash_hours", "US cash hours"), ("overnight", "overnight session"))
        for seconds in (60, 300))


def trading_date(stamp, policy):
    local = stamp.astimezone(ZoneInfo(policy.timezone))
    return local.date() + timedelta(days=local.time() >= policy.open_time)


def utc(value):
    require(type(value) is str and value.endswith("Z"), "Coverage requires UTC report timestamps ending in Z.")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def source_bounds(record, policy, profile=None):
    """Retain empty selected prefix/suffix dates; never trim to observed trades."""
    selection = record["run_metadata"]["selection"]
    zone = ZoneInfo(selection["source_timezone"])
    first_stamp = local_utc(date.fromisoformat(selection["from_date"]), time(0), zone) if selection.get("from_date") else utc(selection["start_utc"])
    last_stamp = local_utc(date.fromisoformat(selection["to_date"]), time(23, 59, 59), zone) if selection.get("to_date") else utc(selection["end_utc"])
    first, last = trading_date(first_stamp, policy), trading_date(last_stamp, policy)
    require(0 <= (last - first).days < 10000, "Coverage supports at most 10,000 consecutive source dates.")
    if profile and (selection.get("from_date") or selection.get("to_date")):
        # Requested source-calendar dates can touch two prop dates. Include only
        # sessions whose *expected* export window intersects the selected range;
        # never shorten an intersecting window to the observations that survived.
        account_zone = ZoneInfo(policy.timezone)
        labels = []
        for i in range((last - first).days + 1):
            day = first + timedelta(days=i)
            a, b = (profile.first_bar_time, profile.last_bar_time) if profile.window == "custom" else (
                (time(9, 30), time(16)) if profile.window == "cash_hours" else (policy.open_time, policy.close_time))
            lo = local_utc(day - timedelta(days=a >= policy.open_time), a, account_zone)
            hi = local_utc(day - timedelta(days=b >= policy.open_time), b, account_zone)
            if (not selection.get("from_date") or hi >= first_stamp) and (not selection.get("to_date") or lo <= last_stamp): labels.append(day)
        require(bool(labels), "Selected dates do not intersect this export-session profile.")
        first, last = labels[0], labels[-1]
    return first, last


def scan_source(store, runs, record, policy, *, force=False):
    """Compress exact timestamp sequences to SQLite; RAM does not grow with bars."""
    from .sessions import _exact_equal
    path = runs.root / record["id"] / "report.json"
    stat = path.stat()
    fingerprint = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, _digest(record), _digest(policy.to_dict()), "coverage-scan-1.0.0"]
    with store.connect() as conn:
        old = conn.execute("SELECT fingerprint,payload FROM prop_coverage_cache WHERE run_id=?", (record["id"],)).fetchone()
        if not force and old and json.loads(old[0]) == fingerprint:
            return json.loads(old[1])
        conn.execute("DELETE FROM prop_coverage_segments WHERE run_id=?", (record["id"],))
        conn.execute("DELETE FROM prop_coverage_trades WHERE run_id=?", (record["id"],))
        digest, header, gaps = sha256(), {}, Counter()
        count = trades = ordinal = 0
        current = previous = None

        class Reader:
            def __init__(self, stream): self.stream = stream
            def read(self, n):
                value = self.stream.read(n)
                digest.update(value.encode("utf-8"))
                return value

        def flush():
            nonlocal ordinal
            if current:
                conn.execute("INSERT INTO prop_coverage_segments VALUES (?,?,?,?,?,?,?)",
                             (record["id"], ordinal, *current))
                ordinal += 1

        with path.open(encoding="utf-8", newline="") as stream:
            for key, item in ReportReader(Reader(stream)).records():
                if key == "trades":
                    label = trading_date(utc(item["exit_time_utc"]), policy).isoformat()
                    conn.execute("INSERT INTO prop_coverage_trades VALUES (?,?,1) ON CONFLICT(run_id,trading_date) DO UPDATE SET count=count+1", (record["id"], label))
                    trades += 1
                elif key == "equity":
                    if item["bar_number"] == 0:
                        require(count == 0 and item["timestamp_utc"] is None, "Invalid starting equity observation.")
                        continue
                    require(item["bar_number"] == count + 1, "Coverage needs contiguous saved bar numbers.")
                    stamp = utc(item["timestamp_utc"])
                    stamp_us = microseconds(stamp - EPOCH)
                    label = trading_date(stamp, policy).isoformat()
                    require(previous is None or stamp_us > previous, "Coverage observations must be strictly chronological.")
                    delta = stamp_us - previous if previous is not None else None
                    if delta is not None and delta <= 86400 * 1000000:
                        # Bound the histogram even for irregular/non-time bars.
                        seconds = delta // 1000000
                        if seconds in (1, 5, 10, 15, 30, 60, 120, 180, 300, 600, 900, 1800, 3600): gaps[seconds] += 1
                    if current and current[0] == label and (current[4] == 1 or delta == current[3]):
                        current = (label, current[1], stamp_us, delta if current[4] == 1 else current[3], current[4] + 1)
                    else:
                        flush()
                        current = (label, stamp_us, stamp_us, 0, 1)
                    previous = stamp_us
                    count += 1
                else:
                    header[key] = item
        flush()
        for key, value in header.items():
            if key == "summary":
                require(all(k in record[key] and _exact_equal(v, record[key][k]) for k, v in value.items()), "Source summary changed; coverage was not published.")
            else:
                require(key in record and _exact_equal(value, record[key], decimal_text=False), "Source metadata changed; coverage was not published.")
        require(count == record["reconciliation"]["observed_bar_count"] and trades == record["summary"]["trades_taken"], "Source counts do not reconcile for coverage.")
        final = path.stat()
        require([final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns] == fingerprint[:5], "Source changed during coverage inspection.")
        summary = dict(source_backtest_id=record["id"], report_sha256=digest.hexdigest(), bar_count=count, trade_count=trades,
                       suggested_interval_seconds=gaps.most_common(1)[0][0] if gaps else None,
                       cadence_note="Observed spacing is a suggestion, not proof of expected exporter cadence.")
        conn.execute("INSERT INTO prop_coverage_cache VALUES (?,?,?) ON CONFLICT(run_id) DO UPDATE SET fingerprint=excluded.fingerprint,payload=excluded.payload",
                     (record["id"], _canonical_json(fingerprint), _canonical_json(summary)))
    return summary


def build_calendar(profile, record, policy, tz_version):
    first, last = source_bounds(record, policy, profile)
    zone = ZoneInfo(policy.timezone)
    market = {}
    if profile.calendar == "cme_equity_model":
        from importlib.metadata import version
        import pandas_market_calendars as mcal
        _require(version("pandas_market_calendars") == "5.5.0", "Install pinned pandas_market_calendars==5.5.0 before resolving coverage.")
        _require(2013 <= first.year <= last.year <= 2026, "CME coverage model supports 2013–2026; use an explicit calendar outside this reviewed range.")
        schedule = mcal.get_calendar("CME_Equity").schedule(first, last)
        market = {stamp.date(): row for stamp, row in schedule.iterrows()}
    days = []
    for i in range((last - first).days + 1):
        day = first + timedelta(days=i)
        row = market.get(day)
        if (profile.calendar == "cme_equity_model" and row is None) or (profile.calendar == "weekday_approximation" and day.weekday() >= 5):
            days.append(CalendarDay(day, "closed")); continue
        opened = local_utc(day - timedelta(days=1), policy.open_time, zone)
        closed = local_utc(day, policy.close_time, zone)
        early = None
        intervals = [(opened, closed)]
        if row is not None:
            market_open, market_close = row["market_open"].to_pydatetime(), row["market_close"].to_pydatetime()
            opened, closed = max(opened, market_open), min(closed, market_close)
            if market_close < local_utc(day, policy.close_time, zone): early = market_close.astimezone(zone).time()
            intervals = [(opened, closed)]
            b1, b2 = row["break_start"].to_pydatetime(), row["break_end"].to_pydatetime()
            if b1 < b2 and opened < b1 < closed:
                intervals = [(opened, b1), (b2, closed)]
        step = timedelta(seconds=profile.bar_interval_seconds)
        windows = []
        if profile.window == "custom":
            start = local_utc(day - timedelta(days=profile.first_bar_time >= policy.open_time), profile.first_bar_time, zone)
            end = local_utc(day - timedelta(days=profile.last_bar_time >= policy.open_time), profile.last_bar_time, zone)
            _require(start <= end, "Custom export window is reversed within the prop session.")
        elif profile.window == "cash_hours":
            start, end = local_utc(day, time(9, 30), zone) + step, local_utc(day, time(16), zone)
        else:
            start, end = opened + step, closed
        # Clip to modeled market hours/breaks, never to whichever source bars exist.
        for a, b in intervals:
            lo = max(start, a + step if a >= start else start)
            hi = min(end, b)
            n = max(0, -(-microseconds(lo - start) // (profile.bar_interval_seconds * 1000000)))
            lo = start + n * step
            if lo <= hi:
                hi = lo + (microseconds(hi - lo) // (profile.bar_interval_seconds * 1000000)) * step
                windows.append(DataWindow(lo, hi, profile.bar_interval_seconds))
        if not windows and profile.calendar == "cme_equity_model":
            days.append(CalendarDay(day, "closed", close_time=early)); continue
        _require(bool(windows), f"Export window has no modeled bars on {day}; use an explicit exception calendar.")
        days.append(CalendarDay(day, "covered", tuple(windows), early))
    assumption = (f"Explicitly selected export profile {profile.name} {profile.version}, SHA-256 {profile.sha256}; cadence {profile.bar_interval_seconds}s; "
                  f"{CALENDAR_VERSION if profile.calendar == 'cme_equity_model' else 'weekday-only approximation without holidays'}. "
                  "No bars filled or dates trimmed. Model schedules are not live exchange certification.")
    return SessionCalendar("source-profile-" + profile.id, policy, tz_version,
                           "explicit" if profile.calendar == "cme_equity_model" else "weekday_approximation", assumption, tuple(days))


def assess(store, record, calendar, scan):
    rows, total_missing, total_extra, partial = [], 0, 0, 0
    zero = covered = holidays = early = 0
    with store.connect() as conn:
        trade_counts = dict(conn.execute("SELECT trading_date,count FROM prop_coverage_trades WHERE run_id=?", (record["id"],)))
        for day in calendar.days:
            observed = matched = off_grid = 0
            first = last = None
            for a, b, step, count in conn.execute("SELECT first_us,last_us,step_us,count FROM prop_coverage_segments WHERE run_id=? AND trading_date=? ORDER BY ordinal", (record["id"], day.trading_date.isoformat())):
                observed += count
                first = a if first is None else min(first, a)
                last = b if last is None else max(last, b)
                for window in day.windows:
                    lo, hi = microseconds(window.first_utc - EPOCH), microseconds(window.last_utc - EPOCH)
                    if count == 1:
                        n, stamp = (1, a) if lo <= a <= hi else (0, a)
                    else:
                        left = max(0, -(-(lo - a) // step)); right = min(count - 1, (hi - a) // step)
                        n, stamp = max(0, right - left + 1), a + left * step
                    if n:
                        grid = window.bar_interval_seconds * 1000000
                        if count == 1:
                            aligned = int((stamp - lo) % grid == 0)
                        else:
                            g = gcd(step, grid)
                            if (lo - a) % g:
                                aligned = 0
                            else:
                                period = grid // g
                                residue = ((lo - a) // g * pow(step // g, -1, period)) % period if period > 1 else 0
                                first_index = left + (residue - left) % period
                                aligned = max(0, (right - first_index) // period + 1)
                        matched += aligned
                        off_grid += n - aligned
            expected = sum(w.bar_count for w in day.windows)
            missing, extra = max(0, expected - matched), observed - matched
            is_partial = bool(day.windows and observed and (first > microseconds(day.windows[0].first_utc - EPOCH) or last < microseconds(day.windows[-1].last_utc - EPOCH)))
            complete = day.status == "covered" and missing == extra == off_grid == 0
            trades = trade_counts.get(day.trading_date.isoformat(), 0)
            status = "closed" if day.status == "closed" and observed == 0 else "covered" if complete else "missing"
            rows.append(dict(trading_date=day.trading_date.isoformat(), status=status, expected_bars=expected, observed_bars=observed,
                             missing_bars=missing, unexpected_bars=extra, off_grid_bars=off_grid, partial_boundary=is_partial,
                             trade_count=trades, zero_trade=complete and trades == 0, early_close=day.close_time.isoformat() if day.close_time else None))
            total_missing += missing; total_extra += extra; partial += is_partial
            covered += complete; zero += complete and trades == 0
            holidays += day.status == "closed" and day.trading_date.weekday() < 5; early += day.close_time is not None
        for label, count in conn.execute("SELECT trading_date,sum(count) FROM prop_coverage_segments WHERE run_id=? AND (trading_date<? OR trading_date>?) GROUP BY trading_date",
                                         (record["id"], calendar.days[0].trading_date.isoformat(), calendar.days[-1].trading_date.isoformat())):
            total_extra += count
            rows.append(dict(trading_date=label, status="missing", expected_bars=0, observed_bars=count, missing_bars=0,
                             unexpected_bars=count, off_grid_bars=0, partial_boundary=True, trade_count=trade_counts.get(label, 0), zero_trade=False, early_close=None))
    rows.sort(key=lambda row: row["trading_date"])
    return dict(status="compatible" if not total_missing and not total_extra and all(r["status"] != "missing" for r in rows) else "rejected",
                source=scan, calendar_sha256=calendar.sha256,
                summary=dict(session_dates=len(rows), covered_sessions=covered, zero_trade_sessions=zero, holiday_dates=holidays,
                             closed_dates=sum(d.status == "closed" for d in calendar.days), early_closes=early,
                             missing_bars=total_missing, unexpected_bars=total_extra, partial_sessions=partial), sessions=rows)

"""Reviewed Nasdaq equity session hours; never inspect price-bar suffixes."""

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import hashlib
import io
from pathlib import Path
import re
from types import MappingProxyType
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


CT = ZoneInfo("America/Chicago")
MINUTES_BEFORE_CLOSE = 5
NQ_SYMBOL_PATTERN = r"@?NQ(?:[!#12]*|[FGHJKMNQUVXZ][0-9]{1,4})(?:[. ]CME)?"
NQ_CALENDAR = dict(id="cme_nq", file="calendars/cme_nq_closures.csv",
                   instrument="NQ futures", timezone="America/Chicago",
                   symbol_pattern=NQ_SYMBOL_PATTERN)
MNQ_SYMBOL_PATTERN = r"@?MNQ(?:[!#12]*|[FGHJKMNQUVXZ][0-9]{1,4})(?:[. ]CME)?"
MNQ_CALENDAR = dict(id="cme_mnq", file="calendars/cme_nq_closures.csv",
                    instrument="MNQ futures", timezone="America/Chicago",
                    symbol_pattern=MNQ_SYMBOL_PATTERN,
                    first_session="2019-05-06",
                    mapping="CME equity-index session closes; instrument prices and multipliers remain separate",
                    reviewed_on="2026-11-08",
                    source_url="https://www.cmegroup.com/trading/equity-index/files/cme-micro-e-mini-futures-fact-card.pdf")
FIELDS = ("coverage_start", "coverage_end", "session_date", "closure_type",
          "close_time_local", "timezone", "event", "source_url", "source_note", "verified_on")


class CalendarError(ValueError):
    """Actionable source/calendar incompatibility; never publish a partial run."""


def resolve_calendar(symbol):
    """Resolve an explicitly saved/chart symbol; never infer from prices or names."""
    for descriptor in (NQ_CALENDAR, MNQ_CALENDAR):
        if re.fullmatch(descriptor['symbol_pattern'], str(symbol or "").strip().upper()):
            return dict(descriptor)
    raise CalendarError(f"No reviewed session calendar for instrument {symbol or '(not set)'!r}. "
                        "Calendar EOD flattening currently supports NQ and MNQ only. "
                        "Use a dataset with an explicit supported symbol, or disable Use EOD Flat.")


def validate_close_buffer(minutes):
    if type(minutes) is not int or not 1 <= minutes <= 1440:
        raise CalendarError("Close buffer minutes must be an integer from 1 through 1440.")


def calendar_path():
    # One canonical editable CSV in a checkout; build_py bundles those same bytes.
    checkout = Path(__file__).resolve().parents[1] / "calendars/cme_nq_closures.csv"
    return checkout if checkout.is_file() else Path(__file__).with_name("reference_data") / "cme_nq_closures.csv"


def session_date(stamp):
    local = stamp.astimezone(CT)
    return local.date() + (timedelta(days=1) if local.time() >= time(17) else timedelta())


@dataclass(frozen=True, slots=True)
class SessionPlan:
    day: date
    kind: str
    close: datetime | None
    cutoff: datetime | None

    def allows(self, stamp):
        if self.cutoff is None or stamp >= self.cutoff:
            return False
        local = stamp.astimezone(CT)
        # Close-labelled minute bars: 17:00 itself is in the maintenance gap.
        return session_date(stamp) == self.day and (local.date() == self.day or local.time() > time(17))


@dataclass(frozen=True, slots=True)
class SessionCalendar:
    start: date
    end: date
    entries: object
    sha256: str
    instrument: str = "NQ futures"

    def metadata(self):
        return dict(file="calendars/cme_nq_closures.csv", sha256=self.sha256,
                    coverage_start=self.start.isoformat(), coverage_end=self.end.isoformat(),
                    timezone="America/Chicago", instrument=self.instrument, rows=len(self.entries))

    def plan(self, day, eod_flat_time=1555, close_buffer_minutes=MINUTES_BEFORE_CLOSE):
        validate_close_buffer(close_buffer_minutes)
        if not self.start <= day <= self.end:
            raise CalendarError(f"{self.instrument.split()[0]} session calendar does not cover {day}; reviewed coverage is "
                             f"{self.start} through {self.end}. Update the shared CSV before running this period.")
        if day.weekday() >= 5:
            return SessionPlan(day, "weekend", None, None)
        row = self.entries.get(day)
        kind = row["closure_type"] if row else "regular"
        if kind == "full_close":
            return SessionPlan(day, kind, None, None)
        close = datetime.combine(day, time.fromisoformat(row["close_time_local"]) if row else time(16), CT)
        configured = datetime.combine(day, time(eod_flat_time // 100, eod_flat_time % 100), CT)
        return SessionPlan(day, kind, close, min(configured, close - timedelta(minutes=close_buffer_minutes)))


def load_calendar(path=None, *, symbol="NQ"):
    descriptor = resolve_calendar(symbol)
    path = Path(path) if path is not None else calendar_path()
    try:
        raw = path.read_bytes()
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("headers must be exactly " + ",".join(FIELDS))
        entries, start, end, previous = {}, None, None, None
        for number, row in enumerate(reader, 2):
            if None in row or any(value is None or value != value.strip() for value in row.values()):
                raise ValueError(f"line {number}: malformed columns or whitespace")
            if any(not row[name] for name in FIELDS if name != "close_time_local"):
                raise ValueError(f"line {number}: missing required value")
            for name in ("coverage_start", "coverage_end", "session_date", "verified_on"):
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[name]):
                    raise ValueError(f"line {number}: {name} must use YYYY-MM-DD")
                date.fromisoformat(row[name])
            bounds = date.fromisoformat(row["coverage_start"]), date.fromisoformat(row["coverage_end"])
            if start is None:
                start, end = bounds
            if bounds != (start, end) or start > end:
                raise ValueError(f"line {number}: inconsistent coverage bounds")
            day = date.fromisoformat(row["session_date"])
            if not start <= day <= end or day.weekday() >= 5 or previous is not None and day <= previous:
                raise ValueError(f"line {number}: exception dates must be covered unique weekdays in ascending order")
            previous = day
            if row["timezone"] != "America/Chicago":
                raise ValueError(f"line {number}: timezone must be America/Chicago")
            kind, close = row["closure_type"], row["close_time_local"]
            if kind == "full_close":
                if close:
                    raise ValueError(f"line {number}: full_close requires an empty time")
            elif kind != "early_close" or not re.fullmatch(r"\d{2}:\d{2}", close) or not time.fromisoformat(close) < time(16):
                raise ValueError(f"line {number}: early_close requires a valid HH:MM before 16:00")
            source = urlparse(row["source_url"])
            if source.scheme != "https" or not source.netloc:
                raise ValueError(f"line {number}: missing absolute HTTPS source URL")
            entries[day] = MappingProxyType(row)
        if not entries:
            raise ValueError("no exception rows")
        effective_start = max(start, date.fromisoformat(descriptor.get('first_session', start.isoformat())))
        return SessionCalendar(effective_start, end, MappingProxyType(entries), hashlib.sha256(raw).hexdigest(), descriptor['instrument'])
    except (OSError, ValueError, csv.Error, UnicodeError) as error:
        raise CalendarError(f"Invalid NQ session calendar {path}: {error}") from error

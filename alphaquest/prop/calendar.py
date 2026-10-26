"""Declared source coverage, prop sessions, and unambiguous local boundaries."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from .rules import _canonical_json, _digest, _read_json
from .types import SessionPolicy, Value, _integer, _require


def microseconds(delta):
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def local_utc(day, clock, zone):
    """Reject nonexistent/ambiguous times instead of silently choosing a fold."""
    naive = datetime.combine(day, clock)
    candidates = set()
    for fold in (0, 1):
        utc = naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(utc)
    _require(len(candidates) == 1, f"Ambiguous or nonexistent session boundary: {naive} {zone.key}.")
    return candidates.pop()


@dataclass(frozen=True, slots=True)
class DataWindow(Value):
    """Inclusive expected bar-close labels, with an explicitly declared cadence."""

    first_utc: datetime
    last_utc: datetime
    bar_interval_seconds: int

    def __post_init__(self):
        super(DataWindow, self).__post_init__()
        _integer("bar_interval_seconds", self.bar_interval_seconds)
        _require(self.first_utc <= self.last_utc, "Data window is reversed.")
        _require(microseconds(self.last_utc - self.first_utc) % (self.bar_interval_seconds * 1000000) == 0,
                 "Data window endpoints do not align to cadence.")

    @property
    def bar_count(self):
        return microseconds(self.last_utc - self.first_utc) // (self.bar_interval_seconds * 1000000) + 1


@dataclass(frozen=True, slots=True)
class CalendarDay(Value):
    trading_date: date
    status: Literal["covered", "closed", "missing"]
    windows: tuple[DataWindow, ...] = ()
    close_time: time | None = None

    def __post_init__(self):
        super(CalendarDay, self).__post_init__()
        _require((self.status == "covered") == bool(self.windows), "Only covered days require nonempty data windows.")
        _require(all(a.last_utc < b.first_utc for a, b in zip(self.windows, self.windows[1:])),
                 "Data windows must be ordered and nonoverlapping.")


@dataclass(frozen=True, slots=True)
class SessionCalendar(Value):
    id: str
    policy: SessionPolicy
    timezone_data_version: str
    mode: Literal["explicit", "weekday_approximation"]
    coverage_assumption: str
    days: tuple[CalendarDay, ...]

    def __post_init__(self):
        super(SessionCalendar, self).__post_init__()
        _require(bool(self.days), "Calendar cannot be empty.")
        _require(all(b.trading_date - a.trading_date == timedelta(days=1) for a, b in zip(self.days, self.days[1:])),
                 "Calendar must declare every date, including closed dates, in order.")
        for day in self.days:
            opened, closed, _ = self.bounds(day)
            for window in day.windows:
                _require(opened <= window.first_utc <= window.last_utc <= closed, "Data window exceeds its prop session.")
            if self.mode == "weekday_approximation":
                _require((day.status == "closed") == (day.trading_date.weekday() >= 5),
                         "Weekday approximation must declare weekends closed and weekdays covered or missing.")

    def bounds(self, day):
        zone = ZoneInfo(self.policy.timezone)
        close_time = day.close_time or self.policy.close_time
        _require(close_time <= self.policy.close_time, "Calendar override can only close earlier.")
        opened = local_utc(day.trading_date - timedelta(days=1), self.policy.open_time, zone)
        closed = local_utc(day.trading_date, close_time, zone)
        reset = local_utc(day.trading_date, self.policy.reset_time, zone)
        _require(opened < closed < reset, "Invalid session boundaries.")
        return opened, closed, reset

    def snapshot_dict(self):
        payload = self.to_dict()
        payload["resolved_boundaries"] = [
            [stamp.isoformat().replace("+00:00", "Z") for stamp in self.bounds(day)] for day in self.days
        ]
        return payload

    @property
    def sha256(self):
        return _digest(self.snapshot_dict())

    def to_json(self):
        return _canonical_json(self.snapshot_dict())

    @classmethod
    def from_json(cls, text):
        payload = _read_json(text)
        _require(type(payload) is dict and "resolved_boundaries" in payload, "Missing calendar boundary snapshot.")
        boundaries = payload.pop("resolved_boundaries")
        calendar = cls.from_dict(payload)
        _require(boundaries == calendar.snapshot_dict()["resolved_boundaries"],
                 "Saved boundaries differ from the available timezone interpretation.")
        return calendar

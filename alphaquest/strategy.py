"""Small immutable strategy inputs/intents. No fills, P&L, or strategy rules."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol
from typing import Literal


def _positive_integer(name: str, value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be an integer >= 1; booleans and coercion are not accepted.")


def _decimal(name: str, value: Decimal, *, positive: bool = False, nonnegative: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal.")
    if positive and value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _utc(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a timezone-aware UTC datetime.")


def _reason(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("reason must be a non-empty string.")


@dataclass(frozen=True, slots=True)
class Bar:
    """One validated completed bar; source_fields preserves all decoded CSV cells.

    Date/time retain source text; the seven numeric attributes are Decimals.
    timestamp_utc represents the bar close under the reviewed contract.
    There is no dataset handle, iterator, or future-bar collection on this input.
    """

    bar_number: int
    timestamp_utc: datetime
    date: str
    time: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    up_vol: Decimal
    down_vol: Decimal
    source_fields: tuple[str, ...]

    def __reduce__(self):
        # Reconstruct through the fixed constructor instead of dataclasses'
        # reflective per-field slot restoration in every worker replay.
        return type(self), (self.bar_number, self.timestamp_utc, self.date, self.time,
                            self.open, self.high, self.low, self.close, self.volume,
                            self.up_vol, self.down_vol, self.source_fields)


@dataclass(frozen=True, slots=True)
class Position:
    """Current filled position with unsigned quantity and explicit side; flat is None."""

    contracts: int
    entry_time_utc: datetime
    entry_fill_price: Decimal
    entry_bar_number: int
    side: Literal["long", "short"] = "long"

    def __post_init__(self):
        _positive_integer("contracts", self.contracts)
        _positive_integer("entry_bar_number", self.entry_bar_number)
        _utc("entry_time_utc", self.entry_time_utc)
        _decimal("entry_fill_price", self.entry_fill_price)
        if self.side not in ("long", "short"):
            raise ValueError("side must be long or short.")


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    initial_capital: Decimal
    tick_size: Decimal
    point_value: Decimal
    slippage_ticks: int
    commission_per_contract_per_side: Decimal

    def __post_init__(self):
        for name in ("initial_capital", "tick_size", "point_value"):
            _decimal(name, getattr(self, name), positive=True)
        _decimal("commission_per_contract_per_side", self.commission_per_contract_per_side, nonnegative=True)
        if type(self.slippage_ticks) is not int or self.slippage_ticks < 0:
            raise ValueError("slippage_ticks must be an integer >= 0; booleans and coercion are not accepted.")


@dataclass(frozen=True, slots=True)
class EntryProtection:
    """Conditional exits prepared before entry; distances resolve from actual fill.

    Exactly one stop basis is required. No completed entry-bar prices are used
    to construct this plan. None target disables the profit-taking leg.
    """

    stop_price: Decimal | None = None
    stop_distance: Decimal | None = None
    target_distance: Decimal | None = None
    max_stop_distance: Decimal | None = None

    def __post_init__(self):
        if (self.stop_price is None) == (self.stop_distance is None):
            raise ValueError("Entry protection requires exactly one stop basis.")
        if self.stop_price is not None:
            _decimal("stop_price", self.stop_price)
        for name in ("stop_distance", "max_stop_distance"):
            if getattr(self, name) is not None:
                _decimal(name, getattr(self, name), positive=True)
        if self.target_distance is not None:
            _decimal("target_distance", self.target_distance, nonnegative=True)


@dataclass(frozen=True, slots=True)
class EntryIntent:
    """Request one entry; defaults preserve long, same-close execution.

    The engine records the deadline but never schedules an exit from it.
    Optional protection is a separate precommitted, fill-activated exit plan.
    No price/fill/cost arithmetic belongs here.
    """

    contracts: int
    reason: str
    exit_deadline_utc: datetime | None = None
    side: Literal["long", "short"] = "long"
    timing: Literal["same_close", "next_open"] = "same_close"
    initial_stop: Decimal | None = None
    protection: EntryProtection | None = None

    def __post_init__(self):
        if self.protection is not None and (type(self.protection) is not EntryProtection or self.timing != "next_open"):
            raise ValueError("Attached entry protection requires a next-bar entry and an EntryProtection plan.")
        if self.initial_stop is not None:
            _decimal("initial_stop", self.initial_stop)
        _positive_integer("contracts", self.contracts)
        _reason(self.reason)
        if self.side not in ("long", "short") or self.timing not in ("same_close", "next_open"):
            raise ValueError("Unsupported entry side or timing.")
        if self.exit_deadline_utc is not None:
            _utc("exit_deadline_utc", self.exit_deadline_utc)


@dataclass(frozen=True, slots=True)
class CloseIntent:
    """Full close at the current Close (default) or the next observed Open."""

    reason: str
    timing: Literal["same_close", "next_open"] = "same_close"

    def __post_init__(self):
        _reason(self.reason)
        if self.timing not in ("same_close", "next_open"):
            raise ValueError("Unsupported close timing.")


@dataclass(frozen=True, slots=True)
class BracketIntent:
    """Full-position stop and optional OCO limit, active for the next bar only."""

    stop_price: Decimal
    target_price: Decimal | None = None

    def __post_init__(self):
        _decimal("stop_price", self.stop_price)
        if self.target_price is not None:
            _decimal("target_price", self.target_price)


@dataclass(frozen=True, slots=True)
class StopEntriesIntent:
    """Flat-only OCO entry stops, active for the next observed bar only.

    Entries retain their own direction, quantity and reason. If both stops
    touch after the Open, OHLC cannot determine the winner: execution rejects.
    """

    orders: tuple[tuple[EntryIntent, Decimal], ...]

    def __post_init__(self):
        if type(self.orders) is not tuple or not 1 <= len(self.orders) <= 2:
            raise ValueError("Stop entries require one or two immutable orders.")
        sides = set()
        for order in self.orders:
            if type(order) is not tuple or len(order) != 2:
                raise ValueError("Each stop entry requires an EntryIntent and trigger price.")
            entry, price = order
            if type(entry) is not EntryIntent or entry.timing != "next_open" or entry.side in sides:
                raise ValueError("Stop entries require distinct sides and next-bar entries.")
            _decimal("entry stop price", price)
            sides.add(entry.side)


class Strategy(Protocol):
    def on_bar(self, bar: Bar, position: Position | None) -> EntryIntent | CloseIntent | BracketIntent | StopEntriesIntent | None:
        """Inspect only the current completed bar and position; return at most one intent."""
        ...

    def on_finish(self, last_bar: Bar, position: Position | None) -> CloseIntent | None:
        """Called after the final bar and its fill; exit policy belongs in the strategy."""
        ...

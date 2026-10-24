"""Small immutable strategy inputs/intents. No fills, P&L, or strategy rules."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol


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


@dataclass(frozen=True, slots=True)
class Position:
    """Current filled long position supplied by the engine; flat is None."""

    contracts: int
    entry_time_utc: datetime
    entry_fill_price: Decimal
    entry_bar_number: int

    def __post_init__(self):
        _positive_integer("contracts", self.contracts)
        _positive_integer("entry_bar_number", self.entry_bar_number)
        _utc("entry_time_utc", self.entry_time_utc)
        _decimal("entry_fill_price", self.entry_fill_price)


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
class EntryIntent:
    """Request one long entry; optional deadline is strategy-owned metadata.

    The engine records the deadline but never schedules or triggers an exit.
    No price/fill/cost arithmetic belongs here.
    """

    contracts: int
    reason: str
    exit_deadline_utc: datetime | None = None

    def __post_init__(self):
        _positive_integer("contracts", self.contracts)
        _reason(self.reason)
        if self.exit_deadline_utc is not None:
            _utc("exit_deadline_utc", self.exit_deadline_utc)


@dataclass(frozen=True, slots=True)
class CloseIntent:
    """Request a full close of the current position."""

    reason: str

    def __post_init__(self):
        _reason(self.reason)


class Strategy(Protocol):
    def on_bar(self, bar: Bar, position: Position | None) -> EntryIntent | CloseIntent | None:
        """Inspect only the current completed bar and position; return at most one intent."""
        ...

    def on_finish(self, last_bar: Bar, position: Position | None) -> CloseIntent | None:
        """Called after the final bar and its fill; exit policy belongs in the strategy."""
        ...

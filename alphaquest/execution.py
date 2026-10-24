"""Streaming, long-only same-close execution. All trading decisions are external."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Context, Decimal, Inexact, InvalidOperation, MAX_EMAX, MIN_EMIN, Overflow
from typing import Literal

from .strategy import Bar, CloseIntent, EntryIntent, ExecutionConfig, Position, Strategy


TIMESTAMP_CONVENTION = "bar_close"
ZERO = Decimal(0)


class ExecutionError(ValueError):
    """Unsupported input, intent, or incomplete final position."""


@dataclass(frozen=True, slots=True)
class Trade:
    trade_number: int
    side: Literal["long"]
    entry_bar_number: int
    exit_bar_number: int
    entry_time_utc: datetime
    exit_time_utc: datetime
    exit_deadline_utc: datetime | None
    contracts: int
    entry_reference_price: Decimal
    exit_reference_price: Decimal
    entry_fill_price: Decimal
    exit_fill_price: Decimal
    entry_commission: Decimal
    exit_commission: Decimal
    total_commissions: Decimal
    reference_gross_pnl: Decimal
    slippage_cost: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    actual_holding_minutes: Decimal
    entry_reason: str
    exit_reason: str


@dataclass(frozen=True, slots=True)
class EquityPoint:
    bar_number: int
    timestamp_utc: datetime | None
    cash_balance: Decimal
    realized_net_pnl: Decimal
    unrealized_pnl: Decimal
    equity: Decimal
    position_contracts: int


def _context(precision: int) -> Context:
    # Independent of caller/strategy Decimal settings. Never leave a localcontext
    # active across a yield. Sufficient operand-derived precision avoids silently
    # rounding accepted CSV prices with more than the default 28 digits.
    return Context(prec=max(1, precision), Emin=MIN_EMIN, Emax=MAX_EMAX,
                   traps=[Inexact, InvalidOperation, Overflow])


def _sum_context(a: Decimal, b: Decimal) -> Context:
    return _context(max(a.adjusted(), b.adjusted()) - min(a.as_tuple().exponent, b.as_tuple().exponent) + 2)


def _add(a: Decimal, b: Decimal) -> Decimal:
    return _sum_context(a, b).add(a, b)


def _sub(a: Decimal, b: Decimal) -> Decimal:
    return _sum_context(a, b).subtract(a, b)


def _mul(a: Decimal, b: Decimal) -> Decimal:
    return _context(len(a.as_tuple().digits) + len(b.as_tuple().digits)).multiply(a, b)


def _pnl(exit_price: Decimal, entry_price: Decimal, contracts: int, point_value: Decimal) -> Decimal:
    return _mul(_mul(_sub(exit_price, entry_price), Decimal(contracts)), point_value)


def _holding_minutes(entry: datetime, exit: datetime) -> Decimal:
    elapsed = exit - entry
    microseconds = (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds
    # The supported CSV has minute timestamps, so these fixture durations divide
    # exactly. For subminute direct inputs only the duration may recur (28 digits);
    # financial arithmetic never uses this quotient.
    return Context(prec=max(28, len(str(microseconds)))).divide(Decimal(microseconds), Decimal(60_000_000))


def _validate_bar(bar: Bar, previous: Bar | None) -> None:
    if type(bar) is not Bar:
        raise ExecutionError("Execution requires normalized Bar values from the dataset reader.")
    expected_number = previous.bar_number + 1 if previous else 1
    if type(bar.bar_number) is not int or bar.bar_number != expected_number:
        raise ExecutionError(f"Expected contiguous bar_number {expected_number}.")
    stamp = bar.timestamp_utc
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ExecutionError("Bar timestamps must be timezone-aware UTC datetimes.")
    if previous and stamp <= previous.timestamp_utc:
        raise ExecutionError("Bar timestamps must be strictly chronological and unique; execution does not sort.")
    for name in ("open", "high", "low", "close", "volume", "up_vol", "down_vol"):
        value = getattr(bar, name)
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ExecutionError(f"Bar {name} must be a finite Decimal.")
    if not bar.low <= bar.open <= bar.high or not bar.low <= bar.close <= bar.high:
        raise ExecutionError("Bar OHLC prices are inconsistent.")
    if any(value < 0 for value in (bar.volume, bar.up_vol, bar.down_vol)):
        raise ExecutionError("Bar volumes must be non-negative.")


class _Account:
    def __init__(self, config: ExecutionConfig):
        self.config = config
        self.cash = config.initial_capital
        self.position: Position | None = None
        self.entry_intent: EntryIntent | None = None
        self.entry_reference = ZERO
        self.entry_commission = ZERO
        self.trade_count = 0
        self.slippage = _mul(config.tick_size, Decimal(config.slippage_ticks))

    def apply(self, intent: EntryIntent | CloseIntent | None, bar: Bar, *, finishing: bool = False) -> Trade | None:
        if intent is None:
            return None
        if type(intent) is EntryIntent:
            if finishing:
                raise ExecutionError("on_finish may return only CloseIntent or None; entry is unsupported.")
            if self.position is not None:
                raise ExecutionError("EntryIntent while holding is unsupported: no pyramiding or position replacement.")
            if intent.exit_deadline_utc is not None and intent.exit_deadline_utc < bar.timestamp_utc:
                raise ExecutionError("Entry exit_deadline_utc cannot precede the actual entry time.")
            fill = _add(bar.close, self.slippage)
            commission = _mul(Decimal(intent.contracts), self.config.commission_per_contract_per_side)
            self.position = Position(intent.contracts, bar.timestamp_utc, fill, bar.bar_number)
            self.entry_intent = intent
            self.entry_reference = bar.close
            self.entry_commission = commission
            self.cash = _sub(self.cash, commission)
            return None
        if type(intent) is not CloseIntent:
            raise ExecutionError(f"Unsupported intent {type(intent).__name__}; return one EntryIntent, CloseIntent, or None.")
        position = self.position
        entry = self.entry_intent
        if position is None or entry is None:
            raise ExecutionError("CloseIntent while flat is inconsistent: there is no position to close.")
        fill = _sub(bar.close, self.slippage)
        commission = _mul(Decimal(position.contracts), self.config.commission_per_contract_per_side)
        gross = _pnl(fill, position.entry_fill_price, position.contracts, self.config.point_value)
        reference_gross = _pnl(bar.close, self.entry_reference, position.contracts, self.config.point_value)
        commissions = _add(self.entry_commission, commission)
        self.trade_count += 1
        trade = Trade(
            trade_number=self.trade_count, side="long",
            entry_bar_number=position.entry_bar_number, exit_bar_number=bar.bar_number,
            entry_time_utc=position.entry_time_utc, exit_time_utc=bar.timestamp_utc,
            exit_deadline_utc=entry.exit_deadline_utc, contracts=position.contracts,
            entry_reference_price=self.entry_reference, exit_reference_price=bar.close,
            entry_fill_price=position.entry_fill_price, exit_fill_price=fill,
            entry_commission=self.entry_commission, exit_commission=commission, total_commissions=commissions,
            reference_gross_pnl=reference_gross, slippage_cost=_sub(reference_gross, gross),
            gross_pnl=gross, net_pnl=_sub(gross, commissions),
            actual_holding_minutes=_holding_minutes(position.entry_time_utc, bar.timestamp_utc),
            entry_reason=entry.reason, exit_reason=intent.reason,
        )
        self.cash = _sub(_add(self.cash, gross), commission)
        self.position = None
        self.entry_intent = None
        return trade

    def mark(self, bar: Bar | None) -> EquityPoint:
        unrealized = ZERO
        if bar is not None and self.position is not None:
            unrealized = _pnl(bar.close, self.position.entry_fill_price, self.position.contracts, self.config.point_value)
        return EquityPoint(
            bar_number=bar.bar_number if bar else 0,
            timestamp_utc=bar.timestamp_utc if bar else None,
            cash_balance=self.cash, realized_net_pnl=_sub(self.cash, self.config.initial_capital),
            unrealized_pnl=unrealized, equity=_add(self.cash, unrealized),
            position_contracts=self.position.contracts if self.position else 0,
        )


def execute(bars: Iterable[Bar], strategy: Strategy, config: ExecutionConfig) -> Iterator[Trade | EquityPoint]:
    """Yield immutable completed trades and equity points with bounded state.

    Exhaust this iterator inside read_bars' context for a completed run. Results
    are provisional until exhaustion: bad input, strategy errors, or an open
    final position can fail after earlier events have been emitted. The caller
    owns input resources and should close a partially consumed execution iterator.

    Strategy callbacks receive only the current bar and filled position. No next
    bar is pulled until the current callback/fill has completed. One equity point
    is retained until the next bar or EOF, so the final point includes on_finish
    without a duplicate. A completed trade precedes its associated equity point.
    """
    if type(config) is not ExecutionConfig:
        raise ExecutionError("config must be an ExecutionConfig with explicit Decimal settings.")
    if not callable(getattr(strategy, "on_bar", None)) or not callable(getattr(strategy, "on_finish", None)):
        raise ExecutionError("Strategy must supply on_bar and on_finish callbacks.")
    account = _Account(config)
    previous = None
    pending = None
    yield account.mark(None)
    for bar in bars:
        if pending is not None:
            yield pending
        _validate_bar(bar, previous)
        trade = account.apply(strategy.on_bar(bar, account.position), bar)
        if trade is not None:
            yield trade
        pending = account.mark(bar)
        previous = bar
    if previous is None:
        raise ExecutionError("Cannot execute an empty dataset: no last bar for on_finish.")
    trade = account.apply(strategy.on_finish(previous, account.position), previous, finishing=True)
    if trade is not None:
        yield trade
    if account.position is not None:
        raise ExecutionError("Unsupported completion: strategy left an open position after on_finish.")
    yield account.mark(previous)

"""Streaming same-close and next-bar OHLC execution. All trading decisions are external."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Context, Decimal
from typing import Literal
from contextlib import nullcontext

from .decimal_math import add as _add, multiply as _mul, subtract as _sub
from .strategy import Bar, BracketIntent, CloseIntent, EntryIntent, ExecutionConfig, Position, Strategy


TIMESTAMP_CONVENTION = "bar_close"
ZERO = Decimal(0)


class ExecutionError(ValueError):
    """Unsupported input, intent, or incomplete final position."""


@dataclass(frozen=True, slots=True)
class Trade:
    trade_number: int
    side: Literal["long", "short"]
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

    def apply(self, intent: EntryIntent | CloseIntent | None, bar: Bar, *, finishing: bool = False,
              reference: Decimal | None = None, limit: bool = False) -> Trade | None:
        if intent is None:
            return None
        reference = bar.close if reference is None else reference
        if type(intent) is EntryIntent:
            if finishing:
                raise ExecutionError("on_finish may return only CloseIntent or None; entry is unsupported.")
            if self.position is not None:
                raise ExecutionError("EntryIntent while holding is unsupported: no pyramiding or position replacement.")
            if intent.exit_deadline_utc is not None and intent.exit_deadline_utc < bar.timestamp_utc:
                raise ExecutionError("Entry exit_deadline_utc cannot precede the actual entry time.")
            fill = (_add if intent.side == "long" else _sub)(reference, self.slippage)
            commission = _mul(Decimal(intent.contracts), self.config.commission_per_contract_per_side)
            self.position = Position(intent.contracts, bar.timestamp_utc, fill, bar.bar_number, intent.side)
            self.entry_intent = intent
            self.entry_reference = reference
            self.entry_commission = commission
            self.cash = _sub(self.cash, commission)
            return None
        if type(intent) is not CloseIntent:
            raise ExecutionError(f"Unsupported intent {type(intent).__name__}; return one EntryIntent, CloseIntent, or None.")
        if finishing and intent.timing != "same_close":
            raise ExecutionError("on_finish cannot schedule a next-open exit without a future bar.")
        position = self.position
        entry = self.entry_intent
        if position is None or entry is None:
            raise ExecutionError("CloseIntent while flat is inconsistent: there is no position to close.")
        fill = reference if limit else (_sub if position.side == "long" else _add)(reference, self.slippage)
        commission = _mul(Decimal(position.contracts), self.config.commission_per_contract_per_side)
        signed_contracts = position.contracts if position.side == "long" else -position.contracts
        gross = _pnl(fill, position.entry_fill_price, signed_contracts, self.config.point_value)
        reference_gross = _pnl(reference, self.entry_reference, signed_contracts, self.config.point_value)
        commissions = _add(self.entry_commission, commission)
        self.trade_count += 1
        trade = Trade(
            trade_number=self.trade_count, side=position.side,
            entry_bar_number=position.entry_bar_number, exit_bar_number=bar.bar_number,
            entry_time_utc=position.entry_time_utc, exit_time_utc=bar.timestamp_utc,
            exit_deadline_utc=entry.exit_deadline_utc, contracts=position.contracts,
            entry_reference_price=self.entry_reference, exit_reference_price=reference,
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
            contracts = self.position.contracts if self.position.side == "long" else -self.position.contracts
            unrealized = _pnl(bar.close, self.position.entry_fill_price, contracts, self.config.point_value)
        return EquityPoint(
            bar_number=bar.bar_number if bar else 0,
            timestamp_utc=bar.timestamp_utc if bar else None,
            cash_balance=self.cash, realized_net_pnl=_sub(self.cash, self.config.initial_capital),
            unrealized_pnl=unrealized, equity=_add(self.cash, unrealized),
            position_contracts=self.position.contracts if self.position else 0,
        )


def _fill_bracket(account: _Account, bracket: BracketIntent, bar: Bar) -> Trade | None:
    """Open gaps first; otherwise stop wins an ambiguous two-level bar.

    Limits fill at the limit or a better opening price, without adverse slippage.
    Stops become market orders with adverse slippage. No intrabar path is invented.
    """
    position = account.position
    if position is None:
        raise ExecutionError("Pending bracket has no position.")
    stop, target = bracket.stop_price, bracket.target_price
    long = position.side == "long"
    if (bar.open <= stop if long else bar.open >= stop):
        return account.apply(CloseIntent("stop_loss"), bar, reference=bar.open)
    if (bar.open >= target if long else bar.open <= target):
        return account.apply(CloseIntent("take_profit"), bar, reference=bar.open, limit=True)
    if (bar.low <= stop if long else bar.high >= stop):
        return account.apply(CloseIntent("stop_loss"), bar, reference=stop)
    if (bar.high >= target if long else bar.low <= target):
        return account.apply(CloseIntent("take_profit"), bar, reference=target, limit=True)
    return None


def execute(bars: Iterable[Bar], strategy: Strategy, config: ExecutionConfig) -> Iterator[Trade | EquityPoint]:
    """Replay, applying an optional strategy-owned historical preparation pass.

    VWAP's EOD option deliberately looks ahead within each session to infer its
    last bar. Strategies without prepare_replay retain the causal streaming
    interface. Preparation never edits existing reports or source datasets.
    """
    prepare = getattr(strategy, "prepare_replay", None)
    with (prepare(bars) if prepare is not None else nullcontext(bars)) as replay:
        yield from _execute(replay, strategy, config)


def _execute(bars: Iterable[Bar], strategy: Strategy, config: ExecutionConfig) -> Iterator[Trade | EquityPoint]:
    """Yield immutable completed trades and equity points with bounded state.

    Exhaust this iterator inside read_bars' context for a completed run. Results
    are provisional until exhaustion: bad input, strategy errors, or an open
    final position can fail after earlier events have been emitted. The caller
    owns input resources and should close a partially consumed execution iterator.

    Strategy callbacks receive only the current bar and filled position. No next
    bar is pulled until the current callback/fill has completed. Next-open orders
    and brackets execute before the following callback; brackets expire after
    that bar. Fill times identify the containing bar close. One equity point
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
    next_order = None
    yield account.mark(None)
    for bar in bars:
        if pending is not None:
            yield pending
        _validate_bar(bar, previous)
        closed_on_bar = False
        if next_order is not None:
            if type(next_order) is BracketIntent:
                trade = _fill_bracket(account, next_order, bar)
            else:
                allow_entry = getattr(strategy, "allow_entry_fill", None)
                if type(next_order) is EntryIntent and allow_entry is not None and not allow_entry(bar):
                    trade = None
                else:
                    trade = account.apply(next_order, bar, reference=bar.open)
            if trade is not None:
                closed_on_bar = True
                yield trade
        intent = strategy.on_bar(bar, account.position)
        next_order = None
        if type(intent) is BracketIntent:
            if account.position is None:
                raise ExecutionError("BracketIntent while flat is inconsistent.")
            if ((account.position.side == "long" and intent.stop_price >= intent.target_price)
                    or (account.position.side == "short" and intent.stop_price <= intent.target_price)):
                raise ExecutionError("Bracket stop and target order is inconsistent with position side.")
            next_order = intent
        elif type(intent) in (EntryIntent, CloseIntent) and intent.timing == "next_open":
            if (type(intent) is EntryIntent) != (account.position is None):
                raise ExecutionError("Next-open entry requires flat; next-open close requires a position.")
            next_order = intent
        else:
            if closed_on_bar and type(intent) is EntryIntent:
                raise ExecutionError("Same-close re-entry on an exit bar is unsupported; use next_open.")
            trade = account.apply(intent, bar)
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

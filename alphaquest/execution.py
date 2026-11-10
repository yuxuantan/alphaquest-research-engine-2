"""Streaming same-close and next-bar OHLC execution. All trading decisions are external."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Context, Decimal, localcontext, ROUND_CEILING, ROUND_FLOOR
from typing import Literal
from contextlib import nullcontext

from .decimal_math import add as _add, multiply as _mul, subtract as _sub
from .intratrade import IntratradeRisk, RiskCapture
from .strategy import Bar, BracketIntent, CloseIntent, EntryIntent, ExecutionConfig, Position, StopEntriesIntent, Strategy
from .execution_scenarios import FillAssumptions
from .decision_capture import DecisionEvent
from .prop.native_control import (EntryAcceptance, ExecutionSnapshot, KnownEntryProposal,
                                  SessionContext, SessionRiskOrders, executable_floor_reference)
from .session_calendar import session_date


TIMESTAMP_CONVENTION = "bar_close"
ZERO = Decimal(0)


class ExecutionError(ValueError):
    """Unsupported input, intent, or incomplete final position."""


@dataclass(frozen=True, slots=True)
class ExecutionContinuation:
    """Flat controlled-block cash, retaining the original trading capital."""
    engine_initial_capital: Decimal
    trading_cash: Decimal

    def __post_init__(self):
        if (not all(type(value) is Decimal and value.is_finite() for value in
                    (self.engine_initial_capital,self.trading_cash)) or self.engine_initial_capital <= 0):
            raise ExecutionError('Continuation requires finite Decimal cash and positive original capital.')


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
    def __init__(self, config: ExecutionConfig, capture_risk=False, fill_assumptions=None, capture_decisions=False):
        self.config = config
        self.capture_decisions = capture_decisions
        self.decision_count = self.decision_sequence = 0
        self.pending_decision = self.active_decision = None
        self.decision_events = []
        self.fill_assumptions = fill_assumptions or FillAssumptions()
        self.capture_risk = capture_risk
        self.risk = self.closed_risk = None
        self.cash = config.initial_capital
        self.position: Position | None = None
        self.entry_intent: EntryIntent | None = None
        self.entry_reference = ZERO
        self.entry_commission = ZERO
        self.trade_count = 0
        self.slippage = _mul(config.tick_size, Decimal(config.slippage_ticks))

    def emit_decision(self, kind, decision_id, bar, side, contracts, **values):
        if not self.capture_decisions:
            return None
        self.decision_sequence += 1
        event = DecisionEvent(sequence=self.decision_sequence, kind=kind, decision_id=decision_id,
                              bar_number=bar.bar_number, timestamp_utc=bar.timestamp_utc,
                              side=side, contracts=contracts, **values)
        self.decision_events.append(event)
        return event

    def record_decision(self, intent, bar):
        if not self.capture_decisions:
            return
        if self.pending_decision is not None or self.position is not None:
            raise ExecutionError('An entry decision requires no active or pending position.')
        if intent.initial_stop is not None and not (intent.initial_stop < bar.close if intent.side == 'long' else intent.initial_stop > bar.close):
            raise ExecutionError('Initial stop must be adverse to the causal decision close.')
        self.decision_count += 1
        self.pending_decision = self.emit_decision('entry_decision', self.decision_count, bar, intent.side, intent.contracts,
            trade_number=None, reference_price=bar.close, stop_price=intent.initial_stop,
            execution_timing=intent.timing, reason=intent.reason)

    def cancel_decision(self, bar, reason):
        if self.pending_decision is not None:
            decision = self.pending_decision
            self.emit_decision('entry_cancelled', decision.decision_id, bar, decision.side, decision.contracts,
                               trade_number=None, reason=reason)
            self.pending_decision = None

    def record_bracket(self, intent, bar):
        if self.capture_decisions:
            if self.active_decision is None or self.position is None:
                raise ExecutionError('Bracket evidence requires a captured filled entry decision.')
            self.emit_decision('bracket_submission', self.active_decision.decision_id, bar,
                self.position.side, self.position.contracts, trade_number=self.trade_count + 1,
                reference_price=bar.close, stop_price=intent.stop_price, target_price=intent.target_price,
                reason='strategy_bracket_next_observed_bar')

    def drain_decisions(self):
        events, self.decision_events = self.decision_events, []
        yield from events

    def apply(self, intent: EntryIntent | CloseIntent | None, bar: Bar, *, finishing: bool = False,
              reference: Decimal | None = None, limit: bool = False, phase: str = "close",
              stop_exit: bool = False, risk_reference: Decimal | None = None,
              entry_fill_exit: bool = False) -> Trade | None:
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
            if self.capture_decisions:
                if self.pending_decision is None:
                    raise ExecutionError('Filled entry lacks a causal captured decision.')
                self.active_decision, self.pending_decision = self.pending_decision, None
                self.emit_decision('entry_fill', self.active_decision.decision_id, bar, intent.side, intent.contracts,
                    trade_number=self.trade_count + 1, reference_price=reference, fill_price=fill, reason='actual_native_fill')
            self.cash = _sub(self.cash, commission)
            if self.capture_risk:
                self.risk = RiskCapture(self.position, self.config, commission, reference, phase)
            return None
        if type(intent) is not CloseIntent:
            raise ExecutionError(f"Unsupported intent {type(intent).__name__}; return one EntryIntent, CloseIntent, or None.")
        if finishing and intent.timing != "same_close":
            raise ExecutionError("on_finish cannot schedule a next-open exit without a future bar.")
        position = self.position
        entry = self.entry_intent
        if position is None or entry is None:
            raise ExecutionError("CloseIntent while flat is inconsistent: there is no position to close.")
        slippage = self.slippage
        if stop_exit and self.fill_assumptions.stop_extra_slippage_ticks:
            slippage = _add(slippage, _mul(self.config.tick_size, Decimal(self.fill_assumptions.stop_extra_slippage_ticks)))
        fill = reference if limit else (_sub if position.side == "long" else _add)(reference, slippage)
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
        if self.risk is not None:
            if not entry_fill_exit and phase in ("open", "stop", "target"):
                self.risk.observe_bar(bar, phase, reference if risk_reference is None else risk_reference)
            self.closed_risk = self.risk.finish(trade, phase)
            self.risk = None
        self.cash = _sub(_add(self.cash, gross), commission)
        self.position = None
        self.entry_intent = None
        if self.capture_decisions:
            if self.active_decision is None:
                raise ExecutionError('Completed trade lacks captured decision provenance.')
            self.emit_decision('trade_close', self.active_decision.decision_id, bar, trade.side, trade.contracts,
                trade_number=trade.trade_number, reference_price=reference, fill_price=fill, net_pnl=trade.net_pnl,
                reason=trade.exit_reason)
            self.active_decision = None
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


class _ControlledExecution:
    """Execution facts only; the supplied phase owner owns account decisions."""
    def __init__(self, owner, account):
        self.owner,self.account=owner,account
        self.context=None;self.session_bars=0;self.acceptance=None;self.offered=None

    def snapshot(self,bar):
        return ExecutionSnapshot(bar.timestamp_utc,bar.bar_number,self.account.config.initial_capital,
                                 self.account.cash,self.account.position)

    def end_session(self,bar,next_order):
        if self.account.position is not None or next_order is not None or self.acceptance is not None:
            raise ExecutionError('Controlled session boundary requires flat with no pending orders; no boundary liquidation is invented.')
        if self.session_bars!=self.context.observed_bar_count:
            raise ExecutionError('Controlled session observed bar inventory differs from execution.')
        self.owner.end_session(self.context,self.snapshot(bar))
        self.context=None

    def begin_bar(self,bar,previous,next_order):
        context=self.owner.session_context(bar.timestamp_utc)
        if (type(context) is not SessionContext or context.session!=session_date(bar.timestamp_utc)
                or type(context.observed_bar_count) is not int or context.observed_bar_count<1
                or context.fully_observed_or_flat_after_entry_cutoff is not True):
            raise ExecutionError('Controlled execution requires a verified observed session context.')
        if self.context is not None and context.session!=self.context.session:
            self.end_session(previous,next_order)
        if self.context is None:
            self.context=context;self.session_bars=0
            self.owner.begin_session(context,self.snapshot(bar))
        elif context!=self.context:
            raise ExecutionError('Controlled session context changed within a session.')
        self.session_bars+=1

    def orders(self,bar):
        orders=self.owner.risk_orders(self.snapshot(bar))
        floors=(() if orders.daily_floor_engine_equity is None else (orders.daily_floor_engine_equity,)) if type(orders) is SessionRiskOrders else ()
        if (type(orders) is not SessionRiskOrders or orders.session!=self.context.session
                or type(orders.entry_allowed) is not bool
                or not all(type(value) is Decimal and value.is_finite() for value in (orders.account_floor_engine_equity,*floors))):
            raise ExecutionError('Phase owner returned invalid executable equity floors.')
        return orders

    def strategy_bar(self,strategy,bar):
        self.offered=None
        def admit(intent):
            if type(intent) is not EntryIntent or intent.initial_stop is None:
                raise ExecutionError('A controlled opportunity requires an EntryIntent and causal initial stop.')
            if self.account.position is not None or self.acceptance is not None or self.offered is not None:
                raise ExecutionError('Controlled admission requires flat with no accepted pending entry.')
            if not (intent.initial_stop<bar.close if intent.side=='long' else intent.initial_stop>bar.close):
                raise ExecutionError('Initial stop must be adverse to the causal decision close.')
            proposal=KnownEntryProposal(bar.timestamp_utc,bar.bar_number,intent.side,intent.timing,bar.close,
                intent.initial_stop,bar.timestamp_utc,intent.reason,intent.exit_deadline_utc)
            accepted=self.owner.admit_entry(proposal,self.snapshot(bar))
            if type(accepted) is not EntryAcceptance or accepted.action not in ('accept','skip','halt'):
                raise ExecutionError('Phase owner returned an invalid entry acceptance.')
            if accepted.action!='accept':
                if accepted.accepted_intent is not None:
                    raise ExecutionError('Skipped entry cannot carry an executable intent.')
                return None
            result=accepted.accepted_intent
            if (type(result) is not EntryIntent or replace(result,contracts=intent.contracts)!=intent
                    or not self.orders(bar).entry_allowed):
                raise ExecutionError('Controlled admission may change quantity only and must permit entry.')
            self.acceptance=accepted;self.offered=result
            return result
        intent=strategy.on_bar_controlled(bar,self.account.position,admit)
        if (type(intent) is EntryIntent and intent!=self.offered) or (self.offered is not None and intent!=self.offered):
            raise ExecutionError('Controlled strategy must return exactly its accepted provisional entry.')
        return intent

    def entry_filled(self,bar):
        if self.acceptance is None:
            raise ExecutionError('Controlled entry fill lacks its causal acceptance.')
        self.owner.after_entry_fill(self.snapshot(bar),self.acceptance)
        self.acceptance=None

    def entry_cancelled(self,bar,reason):
        if self.acceptance is None:
            raise ExecutionError('Controlled entry cancellation lacks its acceptance.')
        self.owner.cancel_entry(self.acceptance,self.snapshot(bar),reason)
        self.acceptance=None

    def closed(self,trade,bar,trigger=None):
        self.owner.after_trade_close(trade,self.snapshot(bar),triggering_floor=trigger)


def _controlled_fill(account,bracket,bar,control,*,include_range=True,reference=None,phase='open'):
    """Arbitrate real strategy orders and provider floors through Account.apply.

    A gap is observed before intrabar touches. Otherwise the nearest adverse
    executable stop precedes an ambiguous target, exactly as the ordinary OCO
    convention. Same-close entry risk uses only the current close.
    """
    if account.position is None:
        return None,None
    orders=control.orders(bar);position=account.position
    price=bar.open if reference is None else reference
    signed=position.contracts*(1 if position.side=='long' else -1)
    marked=_add(account.cash,_pnl(price,position.entry_fill_price,signed,account.config.point_value))
    hit=('account' if marked<=orders.account_floor_engine_equity else
         'daily' if orders.daily_floor_engine_equity is not None and marked<=orders.daily_floor_engine_equity else None)
    if hit:
        return account.apply(CloseIntent('native_'+hit+'_floor'),bar,reference=price,
            phase=phase,stop_exit=True),hit
    if not include_range:
        return None,None
    if bracket is not None:
        target=bracket.target_price
        if target is not None:
            penetration=_mul(account.config.tick_size,Decimal(account.fill_assumptions.limit_penetration_ticks))
            target=(_add if position.side=='long' else _sub)(target,penetration)
        gap=((bar.open<=bracket.stop_price or (target is not None and bar.open>=target)) if position.side=='long' else
             (bar.open>=bracket.stop_price or (target is not None and bar.open<=target)))
        if gap:
            return _fill_bracket(account,bracket,bar),None
    floor=orders.account_floor_engine_equity;trigger='account'
    if orders.daily_floor_engine_equity is not None and orders.daily_floor_engine_equity>floor:
        floor=orders.daily_floor_engine_equity;trigger='daily'
    stop=executable_floor_reference(control.snapshot(bar),floor,account.config.tick_size,account.config.point_value)
    reason='native_'+trigger+'_floor'
    if bracket is not None and (bracket.stop_price>stop if position.side=='long' else bracket.stop_price<stop):
        stop=bracket.stop_price;reason='stop_loss';trigger=None
    touched=bar.low<=stop if position.side=='long' else bar.high>=stop
    if touched:
        return account.apply(CloseIntent(reason),bar,reference=stop,phase='stop',stop_exit=True),trigger
    return (_fill_bracket(account,bracket,bar),None) if bracket is not None else (None,None)


def _fill_bracket(account: _Account, bracket: BracketIntent, bar: Bar) -> Trade | None:
    """Open gaps first; otherwise stop wins an ambiguous two-level bar.

    Optional limit penetration is required before filling; opening improvement
    can be disabled. Stops include explicitly declared extra stop slippage.
    No intrabar path or queue position is invented.
    """
    position = account.position
    if position is None:
        raise ExecutionError("Pending bracket has no position.")
    stop, target = bracket.stop_price, bracket.target_price
    long = position.side == "long"
    assumptions = account.fill_assumptions
    trigger = target
    if target is not None and assumptions.limit_penetration_ticks:
        penetration = _mul(account.config.tick_size, Decimal(assumptions.limit_penetration_ticks))
        trigger = (_add if long else _sub)(target, penetration)
    if (bar.open <= stop if long else bar.open >= stop):
        return account.apply(CloseIntent("stop_loss"), bar, reference=bar.open, phase="open", stop_exit=True)
    if trigger is not None and (bar.open >= trigger if long else bar.open <= trigger):
        reference = bar.open if assumptions.limit_price_improvement else target
        return account.apply(CloseIntent("take_profit"), bar, reference=reference, limit=True, phase="open")
    if (bar.low <= stop if long else bar.high >= stop):
        return account.apply(CloseIntent("stop_loss"), bar, reference=stop, phase="stop", stop_exit=True)
    if trigger is not None and (bar.high >= trigger if long else bar.low <= trigger):
        return account.apply(CloseIntent("take_profit"), bar, reference=target, limit=True, phase="target", risk_reference=trigger)
    return None


def _fill_entry_stops(account, orders, bar, strategy):
    allow_entry = getattr(strategy, "allow_entry_fill", None)
    if allow_entry is not None and not allow_entry(bar):
        return
    gaps = [(entry, bar.open, "open") for entry, price in orders.orders
            if (bar.open >= price if entry.side == "long" else bar.open <= price)]
    hits = gaps or [(entry, price, "entry_stop") for entry, price in orders.orders
                    if (bar.high >= price if entry.side == "long" else bar.low <= price)]
    if len(hits) > 1:
        raise ExecutionError("Both OCO entry stops touched: one-minute OHLC cannot determine entry order; supply finer data or remove the ambiguity.")
    if hits:
        entry, reference, phase = hits[0]
        account.apply(entry, bar, reference=reference, phase=phase)
        return _protect_entry(account, entry, bar, strategy, reference, phase)


def _protect_entry(account, entry, bar, strategy, reference, phase):
    """Activate a precommitted bracket at fill without invoking on_bar twice.

    Market/open fills may use the remaining bar range. For an intrabar stop
    entry, an adverse extreme may precede entry: ambiguous stop timing rejects.
    """
    plan = entry.protection
    if plan is None:
        return None
    if account.capture_decisions:
        raise ExecutionError("Attached entry protection is not supported by native decision capture.")
    filled = getattr(strategy, "on_entry_fill", None)
    if filled is not None:
        filled(entry, account.position)
    position = account.position
    long = position.side == "long"
    fill = position.entry_fill_price
    with localcontext() as ctx:
        ctx.prec = 50
        stop = plan.stop_price if plan.stop_price is not None else fill + (-plan.stop_distance if long else plan.stop_distance)
        if plan.max_stop_distance is not None:
            cap = fill + (-plan.max_stop_distance if long else plan.max_stop_distance)
            stop = max(stop, cap) if long else min(stop, cap)
        # MC special stop amounts normalize to an adverse tick; special targets
        # normalize to a favourable tick. Absolute swing prices already lie on
        # the instrument's tick grid.
        stop = (stop / account.config.tick_size).to_integral_value(
            rounding=ROUND_FLOOR if long else ROUND_CEILING) * account.config.tick_size
        target = None
        if plan.target_distance is not None:
            target = fill + (plan.target_distance if long else -plan.target_distance)
            target = (target / account.config.tick_size).to_integral_value(
                rounding=ROUND_CEILING if long else ROUND_FLOOR) * account.config.tick_size
    bracket = BracketIntent(stop, target)
    if phase == "open":
        return _fill_bracket(account, bracket, bar)
    # A very tight cap can already be breached at the known entry reference
    # after adverse entry slippage. Close at that known price, not at the Open
    # which preceded this stop entry.
    if (reference <= stop if long else reference >= stop):
        return account.apply(CloseIntent("stop_loss"), bar, reference=reference, phase="stop", stop_exit=True, entry_fill_exit=True)
    trigger = target
    if trigger is not None and account.fill_assumptions.limit_penetration_ticks:
        penetration = _mul(account.config.tick_size, Decimal(account.fill_assumptions.limit_penetration_ticks))
        trigger = (_add if long else _sub)(trigger, penetration)
    target_hit = trigger is not None and (bar.high >= trigger if long else bar.low <= trigger)
    stop_in_range = bar.low <= stop if long else bar.high >= stop
    stop_after_entry = bar.close <= stop if long else bar.close >= stop
    if stop_in_range and (target_hit or not stop_after_entry):
        raise ExecutionError(
            f"Immediate entry protection is ambiguous on bar {bar.bar_number} ({bar.timestamp_utc.isoformat()}): "
            "the adverse extreme may precede the stop-entry fill, or SL/TP order is unknown. "
            "One-minute OHLC cannot establish the post-entry path; finer-grained intrabar execution support is required to resolve it. "
            "immediate_protection=false explicitly reproduces the earlier delayed strategy.")
    if stop_in_range:
        return account.apply(CloseIntent("stop_loss"), bar, reference=stop, phase="stop", stop_exit=True)
    if target_hit:
        return account.apply(CloseIntent("take_profit"), bar, reference=target, limit=True,
                             phase="target", risk_reference=trigger)
    return None


def execute(bars: Iterable[Bar], strategy: Strategy, config: ExecutionConfig, *, capture_risk=False, observe_bar=None, fill_assumptions=None, capture_decisions=False,
            account_control=None,continuation=None,completion='strategy_finish') -> Iterator[Trade | EquityPoint | IntratradeRisk | DecisionEvent]:
    """Replay, applying an optional strategy-owned historical preparation pass.

    Preparation is optional. The calendar-based VWAP strategy uses the causal
    streaming interface. Saved reports and source datasets are never edited.
    """
    prepare = getattr(strategy, "prepare_replay", None)
    if account_control is not None and prepare is not None:
        raise ExecutionError('Controlled native execution cannot run a strategy historical preparation pass.')
    with (prepare(bars) if prepare is not None else nullcontext(bars)) as replay:
        yield from _execute(replay, strategy, config, capture_risk=capture_risk, observe_bar=observe_bar, fill_assumptions=fill_assumptions, capture_decisions=capture_decisions,
                            account_control=account_control,continuation=continuation,completion=completion)


def _execute(bars: Iterable[Bar], strategy: Strategy, config: ExecutionConfig, *, capture_risk=False, observe_bar=None, fill_assumptions=None, capture_decisions=False,
             account_control=None,continuation=None,completion='strategy_finish') -> Iterator[Trade | EquityPoint | IntratradeRisk | DecisionEvent]:
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
    if fill_assumptions is not None and type(fill_assumptions) is not FillAssumptions:
        raise ExecutionError('fill_assumptions must be FillAssumptions or None.')
    if not callable(getattr(strategy, "on_bar", None)) or not callable(getattr(strategy, "on_finish", None)):
        raise ExecutionError("Strategy must supply on_bar and on_finish callbacks.")
    if type(capture_decisions) is not bool:
        raise ExecutionError('capture_decisions must be a boolean.')
    if completion not in ('strategy_finish','require_flat'):
        raise ExecutionError('Unknown execution completion policy.')
    if account_control is not None and (completion!='require_flat' or not callable(getattr(strategy,'on_bar_controlled',None))):
        raise ExecutionError('Controlled execution requires provisional strategy admission and require_flat completion.')
    if continuation is not None and (account_control is None or type(continuation) is not ExecutionContinuation
                                     or continuation.engine_initial_capital!=config.initial_capital):
        raise ExecutionError('A continuation requires controlled execution and the unchanged original capital.')
    account = _Account(config, capture_risk, fill_assumptions, capture_decisions)
    if continuation is not None:
        account.cash=continuation.trading_cash
    control=_ControlledExecution(account_control,account) if account_control is not None else None
    previous = None
    pending = None
    next_order = None
    yield account.mark(None)
    for bar in bars:
        if pending is not None:
            yield pending
        _validate_bar(bar, previous)
        if control is not None:
            control.begin_bar(bar,previous,next_order)
        holding_check = getattr(strategy, "validate_holding_bar", None)
        if holding_check is not None:
            holding_check(bar, account.position)
        if observe_bar is not None:
            observe_bar(bar)
        closed_on_bar = False
        risk_checked=False
        if next_order is not None:
            trigger=None
            if type(next_order) is StopEntriesIntent:
                trade = _fill_entry_stops(account, next_order, bar, strategy)
            elif type(next_order) is BracketIntent:
                if control is not None:
                    trade,trigger=_controlled_fill(account,next_order,bar,control)
                    risk_checked=True
                else:
                    trade = _fill_bracket(account, next_order, bar)
            else:
                allow_entry = getattr(strategy, "allow_entry_fill", None)
                if type(next_order) is EntryIntent and allow_entry is not None and not allow_entry(bar):
                    account.cancel_decision(bar, 'entry_guard_rejected')
                    if control is not None:
                        control.entry_cancelled(bar,'entry_guard_rejected')
                    trade = None
                else:
                    trade,trigger=(_controlled_fill(account,None,bar,control,include_range=False,reference=bar.open)
                        if control is not None and type(next_order) is CloseIntent else (None,None))
                    if trade is None:
                        trade = account.apply(next_order, bar, reference=bar.open, phase="open")
                        if type(next_order) is EntryIntent and next_order.protection is not None:
                            if control is not None:
                                raise ExecutionError("Controlled native replay does not support attached entry protection.")
                            trade = _protect_entry(account, next_order, bar, strategy, bar.open, "open")
                        if control is not None and type(next_order) is EntryIntent:
                            control.entry_filled(bar)
            if trade is not None:
                closed_on_bar = True
                if control is not None:
                    control.closed(trade,bar,trigger)
                yield trade
                if capture_risk:
                    yield account.closed_risk
        if control is not None and account.position is not None and not risk_checked:
            trade,trigger=_controlled_fill(account,None,bar,control)
            if trade is not None:
                closed_on_bar=True
                control.closed(trade,bar,trigger)
                yield trade
                if capture_risk:
                    yield account.closed_risk
        yield from account.drain_decisions()
        if account.risk is not None:
            account.risk.observe_bar(bar)
        intent = control.strategy_bar(strategy,bar) if control is not None else strategy.on_bar(bar, account.position)
        if type(intent) is EntryIntent:
            if intent.protection is not None and (capture_decisions or control is not None):
                raise ExecutionError("Attached entry protection is unsupported by decision capture and controlled native replay.")
            account.record_decision(intent, bar)
            yield from account.drain_decisions()
        next_order = None
        if type(intent) is StopEntriesIntent:
            if account.position is not None:
                raise ExecutionError("StopEntriesIntent requires a flat account.")
            if capture_decisions or control is not None:
                raise ExecutionError("OCO stop entry decision capture and controlled native replay are not supported.")
            next_order = intent
        elif type(intent) is BracketIntent:
            if account.position is None:
                raise ExecutionError("BracketIntent while flat is inconsistent.")
            if intent.target_price is not None and ((account.position.side == "long" and intent.stop_price >= intent.target_price)
                    or (account.position.side == "short" and intent.stop_price <= intent.target_price)):
                raise ExecutionError("Bracket stop and target order is inconsistent with position side.")
            account.record_bracket(intent, bar)
            yield from account.drain_decisions()
            next_order = intent
        elif type(intent) in (EntryIntent, CloseIntent) and intent.timing == "next_open":
            if (type(intent) is EntryIntent) != (account.position is None):
                raise ExecutionError("Next-open entry requires flat; next-open close requires a position.")
            next_order = intent
        else:
            if closed_on_bar and type(intent) is EntryIntent:
                raise ExecutionError("Same-close re-entry on an exit bar is unsupported; use next_open.")
            trade = account.apply(intent, bar)
            trigger=None
            if control is not None and type(intent) is EntryIntent:
                control.entry_filled(bar)
                trade,trigger=_controlled_fill(account,None,bar,control,include_range=False,reference=bar.close,phase='close')
            if trade is not None:
                if control is not None:
                    control.closed(trade,bar,trigger)
                yield trade
                if capture_risk:
                    yield account.closed_risk
        yield from account.drain_decisions()
        pending = account.mark(bar)
        previous = bar
    if previous is None:
        raise ExecutionError("Cannot execute an empty dataset: no last bar for on_finish.")
    if completion=='require_flat':
        if account.position is not None or next_order is not None:
            raise ExecutionError('Controlled completion requires flat with no pending orders; source truncation cannot fabricate an EOF liquidation.')
        if control is not None:
            control.end_session(previous,next_order)
        trade=None
    else:
        trade = account.apply(strategy.on_finish(previous, account.position), previous, finishing=True)
    if trade is not None:
        yield trade
        if capture_risk:
            yield account.closed_risk
    yield from account.drain_decisions()
    if account.position is not None:
        raise ExecutionError("Unsupported completion: strategy left an open position after on_finish.")
    account.cancel_decision(previous, 'end_of_data_before_fill')
    yield from account.drain_decisions()
    yield account.mark(previous)

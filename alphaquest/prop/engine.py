"""Deterministic sampled account transitions. No storage, HTTP, strategy or RNG.

Only historical evaluation is executable in this release. Source sessions and
their trade/observation iterators are caller-owned and already reconciled.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..decimal_math import add, subtract, multiply
from .calendar import local_utc
from .types import StressConfig


ENGINE_VERSION = "evaluation-1.0.0"
ZERO = Decimal(0)


class SimulationError(ValueError):
    """An unsupported/incompatible operation, never a financial account loss."""


@dataclass(frozen=True, slots=True)
class ReplaySession:
    session: object
    trades: object
    observations: object


def require(condition, message):
    if not condition:
        raise SimulationError(message)


class AccountEngine:
    """One transition implementation; future phases must extend this engine."""

    def __init__(self, resolved, calendar, execution, emit):
        self.config, self.profile = resolved.config, resolved.rules.profile
        require(self.config.phase == "evaluation", "Funded execution is not implemented.")
        require(self.config.analysis == "historical" and self.config.sizing is None,
                "Only fixed-quantity historical evaluation is implemented.")
        require(self.config.stress == StressConfig(), "Stress execution is not implemented.")
        require(self.config.account_start_utc == calendar.bounds(calendar.days[0])[0],
                "Historical start must equal the first declared session open; partial/pre-purchase access is unsupported.")
        require(self.config.end_utc in {calendar.bounds(day)[2] for day in calendar.days},
                "Historical end must equal a declared session reset; partial or uncovered future bounds are unsupported.")
        self.rules, self.execution, self.emit = self.profile.evaluation, execution, emit
        self.start, self.end = self.config.account_start_utc, self.config.end_utc
        zone = ZoneInfo(self.profile.session.timezone)
        purchase_day = self.start.astimezone(zone).date()
        self.expiry = local_utc(purchase_day + timedelta(days=self.rules.access_calendar_days - 1), self.rules.expiry_time, zone)
        self.balance = self.equity = self.high_water = self.rules.initial_balance
        self.floor = subtract(self.balance, self.rules.drawdown.amount)
        self.dll_floor = None
        self.position = self.processed = self.completed = self.skipped = self.forced = self.suspensions = self.sessions = self.closed_dates = self.zero_days = self.trading_days = 0
        self.external_costs = ZERO
        self.outcome = self.reason = self.outcome_at = self.target_at = self.reviewed_at = self.recognized_at = None
        self.suspended = self.pending_target = False
        self.day = self.trade_number = None
        self.sequence = 0
        self.last_time = self.start
        self.fees = iter(sorted(self.config.fees.scheduled, key=lambda fee: fee.at_utc))
        self.next_fee = next(self.fees, None)

    def event(self, timestamp, kind, detail="", *, realized_delta=ZERO, external_cost=ZERO,
              observed=False, source_equity=None):
        require(timestamp >= self.last_time, "Account events must be chronological.")
        self.last_time = timestamp
        self.emit(dict(sequence=self.sequence, timestamp_utc=timestamp, kind=kind,
                       session_date=self.day.isoformat() if self.day else None, trade_number=self.trade_number,
                       balance=self.balance, equity=self.equity, high_water=self.high_water, trailing_floor=self.floor,
                       daily_loss_floor=self.dll_floor, position_contracts=self.position, realized_delta=realized_delta,
                       external_cost=external_cost, is_equity_observation=observed, source_equity=source_equity, detail=detail))
        self.sequence += 1

    def finish(self, timestamp, outcome, detail):
        require(self.position == 0, "Calendar/terminal boundary cuts unsupported open exposure.")
        self.outcome, self.reason, self.outcome_at = outcome, detail, timestamp
        self.event(timestamp, "outcome", detail, observed=True)

    def advance(self, until, *, pass_priority=False):
        """External fees precede equal-time trading; final valid pass precedes expiry."""
        if self.outcome:
            return False
        while self.next_fee and self.next_fee.at_utc <= until:
            if self.next_fee.at_utc > self.expiry:
                break
            fee = self.next_fee
            self.external_costs = add(self.external_costs, fee.amount)
            self.event(fee.at_utc, "external_fee", fee.name, external_cost=fee.amount)
            self.next_fee = next(self.fees, None)
        if self.expiry <= until and not (pass_priority and self.expiry == until):
            self.finish(self.expiry, "expired", "Calendar access expired without a prior modeled pass.")
            return False
        return True

    def mark(self, mark, baseline, trade):
        if not self.advance(mark.timestamp_utc):
            return
        if self.suspended or self.pending_target:
            return
        before = self.balance
        self.balance = add(baseline, mark.realized_net_pnl) if trade else self.balance
        self.equity = add(baseline, mark.equity_change) if trade else self.balance
        self.position = mark.position_contracts if trade else 0
        self.event(mark.timestamp_utc, "observation", "Selected source observation; costs already included.",
                   realized_delta=subtract(self.balance, before), observed=True, source_equity=mark.source_equity)
        permanent = self.equity <= self.floor
        daily = self.dll_floor is not None and self.equity <= self.dll_floor
        if permanent or daily:
            self.event(mark.timestamp_utc, "drawdown_detected" if permanent else "daily_loss_detected",
                       "Observed loss retained; no threshold-fill interpolation.")
            if self.position:
                # Entry expense/slippage is already in the observed mark. Replace
                # the unconsumed source exit with one modeled market close.
                commission = multiply(Decimal(self.position), self.execution.commission_per_contract_per_side)
                slippage = multiply(multiply(Decimal(self.position), self.execution.point_value),
                                    multiply(self.execution.tick_size, Decimal(self.execution.slippage_ticks)))
                before = self.balance
                self.balance = self.equity = subtract(self.equity, add(commission, slippage))
                self.position = 0
                self.forced += 1
                self.event(mark.timestamp_utc, "liquidated", f"Remaining exit commission {commission}; slippage {slippage}; source exit replaced.",
                           realized_delta=subtract(self.balance, before), observed=True)
            if permanent or self.equity <= self.floor:
                self.finish(mark.timestamp_utc, "failed_drawdown", "Permanent floor touched/crossed at observation or after closing costs.")
            else:
                self.suspended = True
                self.suspensions += 1
                self.event(mark.timestamp_utc, "session_suspended", "Remaining source trades skipped until the next covered session.")
        elif trade and self.position == 0 and self.balance >= add(self.rules.initial_balance, self.rules.profit_target):
            self.pending_target = True
            if self.target_at is None:
                self.target_at = mark.timestamp_utc
            self.event(mark.timestamp_utc, "target_reached", "Flat target reached; stop trading pending valid EOD review.")

    def run_session(self, source):
        session = source.session
        if session.open_utc >= self.end or self.outcome:
            return
        self.day, self.trade_number = session.trading_date, None
        if not self.advance(session.open_utc):
            return
        require(self.position == 0, "Exposure must be flat at every prop-session boundary.")
        self.suspended = self.pending_target = False
        self.dll_floor = subtract(self.balance, self.rules.limits.daily_loss_limit) if self.rules.limits.daily_loss_limit is not None else None
        self.event(session.open_utc, "session_opened" if session.status == "covered" else "calendar_closed",
                   "Limits fixed for this session." if session.status == "covered" else "Declared closed date; calendar clocks still advance.")
        if session.status == "covered":
            self.sessions += 1
            self.zero_days += session.trade_count == 0
        else:
            self.closed_dates += 1
        opened_trade = False
        observations = iter(source.observations)
        mark = next(observations, None)
        for trade in source.trades:
            require(trade.source.entry_time_utc >= self.start, "Source trade requires pre-purchase access.")
            while mark is not None and mark.trade_number is None:
                require(mark.timestamp_utc <= trade.source.entry_time_utc, "Source trade/observation order mismatch.")
                self.trade_number = None
                self.mark(mark, self.balance, None)
                if self.outcome:
                    return
                mark = next(observations, None)
            self.trade_number = trade.source.trade_number
            if not self.advance(trade.source.entry_time_utc):
                return
            baseline = self.balance
            accepted = not (self.suspended or self.pending_target)
            if accepted:
                require(multiply(Decimal(trade.contracts), self.config.contract_limit_weight) <= Decimal(self.rules.limits.max_contracts),
                        "Requested quantity exceeds the session contract limit; source trades cannot be resized or skipped to fit.")
                self.processed += 1
                opened_trade = True
                self.event(trade.source.entry_time_utc, "entry_accepted", "Balance/equity update at the selected observations.")
            else:
                self.skipped += 1
                self.event(trade.source.entry_time_utc, "trade_skipped", "Session suspended." if self.suspended else "Target pending EOD review.")
            require(mark is not None and mark.trade_number == trade.source.trade_number, "Missing source trade observations.")
            natural_close = False
            while mark is not None and mark.trade_number == trade.source.trade_number:
                if accepted:
                    observed = not (self.suspended or self.pending_target)
                    forced_before = self.forced
                    self.mark(mark, baseline, trade)
                    if observed and mark.position_contracts == 0 and self.forced == forced_before:
                        natural_close = True
                elif not self.advance(mark.timestamp_utc):
                    return
                if self.outcome:
                    if accepted and natural_close:
                        self.completed += 1
                    return
                mark = next(observations, None)
            if accepted and natural_close:
                self.completed += 1
        self.trade_number = None
        while mark is not None:
            require(mark.trade_number is None, "Unexpected source observation without trade metadata.")
            self.mark(mark, self.balance, None)
            if self.outcome:
                return
            mark = next(observations, None)
        if not self.advance(session.close_utc):
            return
        require(self.position == 0, "Historical session ended with unsupported open exposure.")
        self.trading_days += opened_trade
        if session.status == "covered":
            self.high_water = max(self.high_water, self.balance)
            candidate = subtract(self.high_water, self.rules.drawdown.amount)
            if self.rules.drawdown.lock_profit is not None:
                candidate = min(candidate, add(self.rules.initial_balance, self.rules.drawdown.lock_profit))
            self.floor = max(self.floor, candidate)
            self.event(session.close_utc, "session_closed", "EOD high-water/floor ratchet; no withdrawals in evaluation.", observed=True)
        if self.pending_target and self.trading_days >= self.rules.minimum_trading_days:
            review = local_utc(session.trading_date, self.rules.review_time, ZoneInfo(self.profile.session.timezone))
            if not self.advance(review):
                return
            self.reviewed_at = review
            self.event(review, "target_reviewed", "Valid EOD review under the saved modeling policy.")
            recognized = local_utc(session.trading_date, self.rules.recognition_not_before, ZoneInfo(self.profile.session.timezone))
            if self.advance(recognized, pass_priority=True):
                self.recognized_at = recognized
                self.finish(recognized, "passed", "Modeled recognition; not external provider approval.")
        else:
            self.advance(min(session.reset_utc, self.end))

    def run(self, sessions):
        self.event(self.start, "account_started", "Source initial capital removed; account starts at profile balance.", observed=True)
        self.external_costs = self.config.fees.attempt_fee
        self.event(self.start, "external_fee", "User-supplied attempt fee.", external_cost=self.external_costs)
        for source in sessions:
            if self.outcome or source.session.open_utc >= self.end:
                break
            self.run_session(source)
        if self.advance(self.end):
            require(self.position == 0, "Historical end cuts open exposure.")
            self.finish(self.end, "unresolved_data_end", "Declared historical coverage ended with an active account; no missing future invented.")
        return dict(outcome=self.outcome, reason=self.reason, outcome_at_utc=self.outcome_at, initial_balance=self.rules.initial_balance,
                    balance=self.balance, equity=self.equity, trailing_floor=self.floor, high_water=self.high_water,
                    realized_net_trading_pnl=subtract(self.balance, self.rules.initial_balance),
                    external_costs=self.external_costs, modeled_receipts=ZERO, modeled_net_cash=subtract(ZERO, self.external_costs),
                    processed_trades=self.processed, completed_source_trades=self.completed, skipped_trades=self.skipped,
                    forced_exits=self.forced, suspensions=self.suspensions, processed_sessions=self.sessions,
                    closed_dates=self.closed_dates, zero_trade_sessions=self.zero_days, target_reached_at_utc=self.target_at,
                    reviewed_at_utc=self.reviewed_at, recognized_at_utc=self.recognized_at, expiry_at_utc=self.expiry,
                    event_count=self.sequence)


def replay_evaluation(resolved, calendar, execution, sessions, emit):
    return AccountEngine(resolved, calendar, execution, emit).run(sessions)

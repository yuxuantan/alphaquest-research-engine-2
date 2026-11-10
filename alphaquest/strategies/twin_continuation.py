"""Causal Twin Continuation port; original source and execution contract in docs/strategies.

State follows the supplied PowerLanguage evaluation order, including late bucket
finalization and the source's deliberately simple half-day date heuristic.
"""

from dataclasses import dataclass, field, fields
from datetime import timedelta, timezone
from decimal import Decimal, localcontext, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from ..backtest_data import DatasetReadError
from ..session_calendar import (CalendarError, NQ_CALENDAR, MNQ_SYMBOL_PATTERN, calendar_path,
                                load_calendar, resolve_calendar, session_date)
from ..strategy import BracketIntent, CloseIntent, EntryIntent, EntryProtection, StopEntriesIntent

D = Decimal
CT = ZoneInfo("America/Chicago")
LOG = logging.getLogger(__name__)
STRATEGY_ID = "twin_continuation"
DESCRIPTION = (
    "Twin Continuation: 6-hour confirmed swing breakout plus 10-minute morning momentum. "
    "One position, setup-owned exits; Chicago one-minute close-labelled bars. "
    "Next-bar market/stop entries with immediate fill-activated SL/TP by default. "
    "Ambiguous two-sided entries and uncertain post-stop-entry protection reject; "
    "Open-entry and later held-bar brackets use stop first. "
    "Local NQ/MNQ calendar supplies same-close session liquidation, including early closes; "
    "source Momentum half-day heuristic is retained."
)
EXECUTION_ASSUMPTION = "twin_selectable_fill_or_legacy_protection_reject_ambiguous_entry_path_calendar_session_close_v3"
SUPPORTS_DECISION_CAPTURE = False
SESSION_CALENDAR = dict(NQ_CALENDAR, instrument="NQ / MNQ futures",
                        symbol_pattern="(?:" + NQ_CALENDAR['symbol_pattern'] + "|" + MNQ_SYMBOL_PATTERN + ")")


def number(default, description, minimum=0, maximum=None):
    metadata = dict(description=description, minimum=minimum)
    if maximum is not None:
        metadata["maximum"] = maximum
    return field(default=default, metadata=metadata)


@dataclass(frozen=True, slots=True)
class Parameters:
    use_breakout: bool = True
    use_momentum: bool = True
    qty: int = number(1, "Contracts of the saved instrument; no NQ/MNQ conversion.", 1)
    bo_target_mult: Decimal = D("2.0")
    bo_max_stop_mult: Decimal = D(0)
    bo_atr_period: int = number(14, "Completed 15-minute bars for Wilder ATR.", 1)
    bo_vol_cap: Decimal = D("2.0")
    bo_vol_lookback: int = number(50, "Previous session ranges; source clamps to 1..99.", 1, 99)
    bo_session_open: int = number(1700, "Session open, Chicago HHMM.", 0, 2359)
    bo_session_close: int = number(1600, "Fixed session close, Chicago HHMM.", 0, 2359)
    bo_last_fill: int = number(1530, "Last BO fill boundary, Chicago HHMM.", 0, 2359)
    bo_exit_time: int = number(1545, "BO same-close flatten time, Chicago HHMM.", 0, 2359)
    bo_pivot_tf: int = number(360, "Session-aligned swing candle length in minutes.", 1, 1440)
    mo_basis_len: int = number(21, "Momentum basis EMA length.", 1)
    mo_range_len: int = number(14, "Momentum Wilder range length.", 1)
    mo_signal_len: int = number(3, "Momentum oscillator EMA length.", 1)
    mo_trigger: Decimal = D(100)
    mo_window_start: int = number(840, "Inclusive completed 10-minute bucket end HHMM.", 0, 2359)
    mo_window_end: int = number(930, "Inclusive completed 10-minute bucket end HHMM.", 0, 2359)
    mo_exit_time: int = number(1450, "MO next-Open flatten submission HHMM.", 0, 2359)
    mo_stop_points: Decimal = D(75)
    mo_warmup: int = number(60, "Minimum completed 10-minute buckets.", 1)
    mo_full_bars_only: bool = True
    mo_allow_long: bool = True
    mo_allow_short: bool = True
    clock_shift: int = number(0, "Source clock offset in minutes; AQ bars already close-labelled: use 0.", -1440, 1440)
    debug_log: bool = False
    immediate_protection: bool = field(default=True, metadata={"description":
        "Activate SL/TP on entry fill, including the entry bar. Ambiguous intrabar stop-entry paths reject. "
        "False reproduces the original next-bar protection timing."})
    max_bars_back: int = number(5, "Leading records skipped, matching manual MC Max Bars Back.", 0)
    use_session_calendar: bool = field(default=True, metadata={"description":
        "Match MC End of Day Exit at the local calendar's scheduled Close, including holidays. "
        "Requires NQ/MNQ and 17:00–16:00 session Inputs. Off retains the earlier fixed-clock model."})

    def __post_init__(self):
        times = {"bo_session_open", "bo_session_close", "bo_last_fill", "bo_exit_time",
                 "mo_window_start", "mo_window_end", "mo_exit_time"}
        for item in fields(self):
            value = getattr(self, item.name)
            if item.type is bool:
                if type(value) is not bool:
                    raise ValueError(f"{item.name} must be a boolean.")
            elif item.type is int:
                if type(value) is not int or value < item.metadata["minimum"] or value > item.metadata.get("maximum", value):
                    raise ValueError(f"{item.name} must be an integer within its supported range.")
                if item.name in times and value % 100 >= 60:
                    raise ValueError(f"{item.name} must be valid HHMM.")
            elif type(value) is not D or not value.is_finite() or value < 0:
                raise ValueError(f"{item.name} must be a non-negative finite Decimal.")
        if self.mo_stop_points <= 0:
            raise ValueError("mo_stop_points must be positive.")
        if self.bo_session_open == self.bo_session_close:
            raise ValueError("Session open and close must differ.")
        if self.mo_window_start > self.mo_window_end:
            raise ValueError("Momentum window must not cross midnight.")
        if self.use_session_calendar and (self.bo_session_open != 1700 or self.bo_session_close != 1600):
            raise ValueError("Calendar session exits require BO session open 1700 and close 1600; "
                             "custom session clocks require use_session_calendar=false.")


def minutes(hhmm):
    return hhmm // 100 * 60 + hhmm % 100


def hhmm(value):
    value %= 1440
    return value // 60 * 100 + value % 60


def source_fingerprint():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in (Path(__file__), root / "strategy.py", root / "execution.py", root / "intratrade.py",
                 root / "session_calendar.py", calendar_path()):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def validate_dataset(dataset):
    interval = dataset.get("interval_seconds")
    if interval is not None and interval != 60:
        raise ValueError("Twin Continuation requires one-minute bars; the saved dataset has another interval.")
    # An irregular source may be minute bars with gaps. Metadata cannot prove
    # its original aggregation interval; require the user to supply 1m OHLC.


def validate_instrument(parameters, symbol):
    if parameters.use_session_calendar:
        resolve_calendar(symbol)


def backtest_assumptions(parameters, *, calendar=None, instrument_symbol="NQ"):
    enabled = parameters.use_session_calendar
    return dict(enabled=enabled, mode="twin_csv_session_close_v2", lookahead=False,
                protection_activation="on_entry_fill" if parameters.immediate_protection else "following_bar_legacy",
                entry_bar_path="reject ambiguous post-stop-entry SL timing/order; market/Open entries use full remaining range",
                calendar=(calendar or load_calendar(symbol=instrument_symbol)).metadata() if enabled else None,
                calendar_selection="instrument_symbol", instrument_symbol=instrument_symbol,
                calendar_id=resolve_calendar(instrument_symbol)['id'] if enabled else None,
                timezone="America/Chicago", minutes_before_close=0, order_timing="same_close",
                fill="scheduled session-close bar Close; pending price exits on that bar retain priority",
                missing_close_bar="reject held exposure before later-session orders; never infer a close from missing bars",
                truncated_session="does not change the scheduled close; explicit end_of_data liquidation remains labelled",
                reference_status="Original MC export qualifies delayed protection only; immediate mode needs a fresh MC export. No runtime export dependency.")


class TwinContinuation:
    def __init__(self, parameters=None, *, execution_config=None, instrument_symbol="NQ"):
        self.p = parameters if parameters is not None else Parameters()
        if type(self.p) is not Parameters:
            raise ValueError("parameters must be Twin Continuation Parameters.")
        validate_instrument(self.p, instrument_symbol)
        self.instrument_symbol = instrument_symbol
        self.tick_size = execution_config.tick_size if execution_config is not None else D("0.25")
        self.calendar = load_calendar(symbol=instrument_symbol) if self.p.use_session_calendar else None
        self.session_plan = None
        self.session_digest = hashlib.sha256()
        self.session_flattening = dict(backtest_assumptions(self.p, calendar=self.calendar, instrument_symbol=instrument_symbol),
            sessions=0, closed_sessions=0, early_close_sessions=0, examples=[], early_close_examples=[],
            plans_sha256=self.session_digest.hexdigest())
        self.prev_sm = self.prev_bkt = self.prev_hidx = -1
        self.session_hi = self.session_lo = D(0)
        self.ranges = []
        self.vol_ratio = D(0)
        self.can_open = self.bar_open = False
        self.cur_hi = self.cur_lo = self.b_hi = self.b_lo = self.b_close = D(0)
        self.b_last_hi = self.b_last_lo = D(0)
        self.b_last_sm = 0
        self.candles = []
        self.tr_n = 0
        self.tr_sum = self.atr = self.prev_c15 = D(0)
        self.got_hi = self.got_lo = None
        self.swing_hi = self.swing_lo = self.last_hi = self.last_lo = D(0)
        self.have_hi = self.have_lo = self.hi_open = self.lo_open = False
        self.armed = self.ok_long = self.ok_short = False
        self.level_long = self.level_short = self.stop_long = self.stop_short = self.arm_atr = D(0)
        self.arm_trades = self.total_trades = 0
        self.s_prev_bk = -1
        self.s_bk_date = self.last_date = None
        self.s_open = self.traded_today = False
        self.s_hi = self.s_lo = self.s_close = D(0)
        self.s_n = self.s_end = self.s_count = 0
        self.s_prev_close = self.s_atr = self.s_pivot = self.osc = self.osc_prev = D(0)
        self.have_osc = self.have_osc_prev = False
        self.setup = self.pending_setup = None
        self.was_holding = False
        self.previous_stamp = None

    def _set_session(self, bar):
        if self.calendar is None:
            return None
        day = session_date(bar.timestamp_utc)
        if self.session_plan is None or self.session_plan.day != day:
            # Only the scheduled Close is used. The shared plan's next-Open
            # cutoff/buffer belongs to VWAP and is irrelevant to MC ExitOnClose.
            self.session_plan = self.calendar.plan(day)
            plan = self.session_plan
            record = dict(session_date=day.isoformat(), session_type=plan.kind,
                          scheduled_close=plan.close.isoformat() if plan.close else None)
            self.session_digest.update((json.dumps(record, sort_keys=True) + "\n").encode())
            metadata = self.session_flattening
            metadata['sessions'] += 1
            metadata['closed_sessions'] += plan.close is None
            metadata['early_close_sessions'] += plan.kind == 'early_close'
            if len(metadata['examples']) < 5:
                metadata['examples'].append(record)
            if plan.kind == 'early_close' and len(metadata['early_close_examples']) < 10:
                metadata['early_close_examples'].append(record)
            metadata['plans_sha256'] = self.session_digest.hexdigest()
        return self.session_plan

    def _close_15(self, position):
        p = self.p
        self.bar_open = False
        tr = self.b_hi - self.b_lo if self.tr_n == 0 else max(self.b_hi, self.prev_c15) - min(self.b_lo, self.prev_c15)
        self.tr_n += 1
        if self.tr_n <= p.bo_atr_period:
            self.tr_sum += tr
            if self.tr_n == p.bo_atr_period:
                self.atr = self.tr_sum / p.bo_atr_period
        else:
            self.atr = (self.atr * (p.bo_atr_period - 1) + tr) / p.bo_atr_period
        self.prev_c15 = self.b_close
        if self.got_hi is not None:
            self.swing_hi = self.last_hi = self.got_hi
            self.have_hi = True
            self.hi_open = self.b_close < self.swing_hi and self.b_last_hi < self.swing_hi
            self.got_hi = None
        if self.got_lo is not None:
            self.swing_lo = self.last_lo = self.got_lo
            self.have_lo = True
            self.lo_open = self.b_close > self.swing_lo and self.b_last_lo > self.swing_lo
            self.got_lo = None
        self.armed = False
        if position is None and self.tr_n >= p.bo_atr_period:
            self.arm_atr = self.atr
            self.level_long, self.stop_long = self.swing_hi, self.last_lo
            self.level_short, self.stop_short = self.swing_lo, self.last_hi
            self.ok_long = self.hi_open and self.have_lo and self.stop_long < self.level_long
            self.ok_short = self.lo_open and self.have_hi and self.stop_short > self.level_short
            fill_end = (minutes(p.bo_last_fill) - minutes(p.bo_session_open)) % 1440
            self.armed = (p.use_breakout and (self.ok_long or self.ok_short) and self.b_last_sm < fill_end - 1
                          and not (p.bo_vol_cap > 0 and self.vol_ratio > p.bo_vol_cap))
            self.arm_trades = self.total_trades
            if p.debug_log and self.armed:
                LOG.info("BO arm L=%s S=%s ATR=%s vol=%s", self.level_long, self.level_short, self.arm_atr, self.vol_ratio)

    def _close_candle(self):
        self.can_open = False
        self.candles.insert(0, (self.cur_hi, self.cur_lo))
        del self.candles[7:]
        if len(self.candles) == 7:
            high, low = self.candles[3]
            if all(high >= candle[0] for candle in self.candles):
                self.got_hi = high
            if all(low <= candle[1] for candle in self.candles):
                self.got_lo = low

    def _close_momentum(self, high, low, close, count, end, half_day, position):
        p = self.p
        self.s_open = False
        self.s_count += 1
        if self.s_count == 1:
            self.s_atr, self.s_pivot = high - low, close
        else:
            tr = max(high - low, abs(high - self.s_prev_close), abs(low - self.s_prev_close))
            self.s_atr += (tr - self.s_atr) / p.mo_range_len
            self.s_pivot += (close - self.s_pivot) * D(2) / (p.mo_basis_len + 1)
        self.s_prev_close = close
        side = 0
        if self.s_atr > 0:
            raw = (close - self.s_pivot) / (3 * self.s_atr) * 100
            if not self.have_osc:
                self.osc, self.have_osc = raw, True
            else:
                self.osc_prev, self.have_osc_prev = self.osc, True
                self.osc += (raw - self.osc) * D(2) / (p.mo_signal_len + 1)
            if self.have_osc_prev:
                if self.osc > p.mo_trigger and self.osc_prev <= p.mo_trigger:
                    side = 1
                elif self.osc < -p.mo_trigger and self.osc_prev >= -p.mo_trigger:
                    side = -1
        if (side and p.mo_window_start <= end <= p.mo_window_end and (not p.mo_full_bars_only or count == 10)
                and not self.traded_today and not half_day and position is None and self.s_count >= p.mo_warmup):
            # Source consumes the daily opportunity even with MO/direction disabled.
            self.traded_today = True
            fire = side if p.use_momentum and (p.mo_allow_long if side == 1 else p.mo_allow_short) else 0
            if p.debug_log:
                LOG.info("MO end=%s side=%s osc=%s fire=%s", end, side, self.osc, fire)
            return fire
        return 0

    def on_bar(self, bar, position):
        with localcontext() as ctx:
            ctx.prec = 50
            return self._on_bar(bar, position)

    def on_entry_fill(self, entry, position):
        # Execution notification only: no candle/oscillator/entry calculation.
        # It also lets a same-bar round trip consume exactly one completed trade
        # when the normal completed-bar callback observes the account flat.
        self.setup = self.pending_setup = "MO" if entry.reason.startswith("MO-") else "BO"
        self.was_holding = True

    def _protection(self, *, stop=None, momentum=False):
        if not self.p.immediate_protection:
            return None
        if momentum:
            return EntryProtection(stop_distance=self.p.mo_stop_points)
        if self.arm_atr <= 0 and (self.p.bo_target_mult > 0 or self.p.bo_max_stop_mult > 0):
            raise ValueError("Immediate BO target/cap protection requires a positive frozen 15-minute ATR.")
        return EntryProtection(stop_price=stop,
            max_stop_distance=self.p.bo_max_stop_mult*self.arm_atr if self.p.bo_max_stop_mult>0 else None,
            target_distance=self.p.bo_target_mult*self.arm_atr if self.p.bo_target_mult>0 else None)

    def _on_bar(self, bar, position):
        p = self.p
        if bar.timestamp_utc.second or bar.timestamp_utc.microsecond:
            raise DatasetReadError("Twin Continuation requires minute-aligned one-minute bars.")
        if self.previous_stamp is not None and (bar.timestamp_utc - self.previous_stamp).total_seconds() < 60:
            raise DatasetReadError("Twin Continuation requires one-minute bars; subminute input is unsupported.")
        self.previous_stamp = bar.timestamp_utc
        plan = self._set_session(bar)
        if bar.bar_number <= p.max_bars_back:
            return None
        stamp = bar.timestamp_utc.astimezone(CT)
        date = stamp.date()  # Source Date is unshifted, even when ClockShift wraps.
        clock = (stamp.hour * 60 + stamp.minute + p.clock_shift) % 1440
        time = hhmm(clock)
        if self.was_holding and position is None:
            self.total_trades += 1
            self.setup = None
        if position is not None and not self.was_holding:
            self.setup = self.pending_setup
        self.was_holding = position is not None
        start = minutes(p.bo_session_open)
        sm = (clock - 1 - start) % 1440
        end = (minutes(p.bo_session_close) - start) % 1440
        fill_end = (minutes(p.bo_last_fill) - start) % 1440
        flat = (minutes(p.bo_exit_time) - start) % 1440
        new_session = self.prev_sm < 0 or sm < self.prev_sm
        bkt, hidx = sm // 15, sm // p.bo_pivot_tf
        new_bkt, new_can = new_session or bkt != self.prev_bkt, new_session or hidx != self.prev_hidx
        if new_session:
            if self.prev_sm >= 0 and self.session_hi > self.session_lo:
                self.ranges.insert(0, self.session_hi - self.session_lo)
                del self.ranges[100:]
                self.vol_ratio = D(0)
                n = p.bo_vol_lookback
                if len(self.ranges) > n:
                    total = sum(self.ranges[1:n + 1], D(0))
                    if total > 0:
                        self.vol_ratio = self.ranges[0] / (total / n)
            self.session_hi, self.session_lo = bar.high, bar.low
        else:
            self.session_hi, self.session_lo = max(self.session_hi, bar.high), min(self.session_lo, bar.low)
        late_can, late_bar = new_can and self.can_open, new_bkt and self.bar_open
        for late in (True, False):
            if late:
                do_can, do_bar = late_can, late_bar
            else:
                if new_can:
                    self.cur_hi, self.cur_lo, self.can_open = bar.high, bar.low, True
                else:
                    self.cur_hi, self.cur_lo = max(self.cur_hi, bar.high), min(self.cur_lo, bar.low)
                if new_bkt:
                    self.b_hi, self.b_lo, self.bar_open = bar.high, bar.low, True
                else:
                    self.b_hi, self.b_lo = max(self.b_hi, bar.high), min(self.b_lo, bar.low)
                self.b_close, self.b_last_hi, self.b_last_lo, self.b_last_sm = bar.close, bar.high, bar.low, sm
                if self.hi_open and bar.high >= self.swing_hi:
                    self.hi_open = False
                if self.lo_open and bar.low <= self.swing_lo:
                    self.lo_open = False
                do_can = self.can_open and ((sm + 1) % p.bo_pivot_tf == 0 or sm + 1 >= end)
                do_bar = self.bar_open and (sm + 1) % 15 == 0
            if do_can:
                self._close_candle()
            if do_bar:
                self._close_15(position)
        self.prev_sm, self.prev_bkt, self.prev_hidx = sm, bkt, hidx
        midnight_exit = False
        if date != self.last_date:
            self.traded_today = False
            midnight_exit = self.last_date is not None and self.setup == "MO" and position is not None
            self.last_date = date
        half_day = ((date.month == 7 and date.day == 3) or (date.month == 12 and date.day == 24)
                    or (date.month == 11 and date.weekday() == 4 and 23 <= date.day <= 29))
        s_start = (clock - 1) % 1440
        sbk = s_start // 10
        new_sbk = sbk != self.s_prev_bk or date != self.s_bk_date
        fire = 0
        for late in (True, False):
            if late:
                do = new_sbk and self.s_open
            else:
                if new_sbk:
                    self.s_hi, self.s_lo, self.s_n, self.s_open, self.s_bk_date = bar.high, bar.low, 1, True, date
                else:
                    self.s_hi, self.s_lo, self.s_n = max(self.s_hi, bar.high), min(self.s_lo, bar.low), self.s_n + 1
                self.s_close, self.s_end = bar.close, hhmm((sbk + 1) * 10)
                do = self.s_open and (s_start + 1) % 10 == 0
            if do:
                result = self._close_momentum(self.s_hi, self.s_lo, self.s_close, self.s_n, self.s_end, half_day, position)
                if result:
                    fire = result
        self.s_prev_bk = sbk
        if fire:
            self.armed = False
            self.pending_setup = "MO"
            return EntryIntent(p.qty, "MO-L" if fire == 1 else "MO-S", side="long" if fire == 1 else "short", timing="next_open",
                               protection=self._protection(momentum=True))
        if self.armed and (position is not None or self.total_trades > self.arm_trades):
            self.armed = False
        if position is not None:
            long = position.side == "long"
            session_end = (bar.timestamp_utc == plan.close.astimezone(timezone.utc) if plan is not None and plan.close
                           else sm + 1 == end if plan is None else False)
            if midnight_exit or (self.setup == "BO" and sm + 1 >= flat and sm < end) or session_end:
                self.was_holding = False
                self.total_trades += 1
                self.setup = None
                if midnight_exit:
                    reason = "MO-LX2" if long else "MO-SX2"
                elif session_end:
                    reason = "session_close"
                else:
                    reason = "BO-LX" if long else "BO-SX"
                return CloseIntent(reason)
            if self.setup == "MO":
                if p.mo_exit_time <= time <= 1600:
                    return CloseIntent("MO-LX" if long else "MO-SX", timing="next_open")
                stop = position.entry_fill_price + (-p.mo_stop_points if long else p.mo_stop_points)
                if p.immediate_protection:
                    stop = (stop/self.tick_size).to_integral_value(rounding=ROUND_FLOOR if long else ROUND_CEILING)*self.tick_size
                return BracketIntent(stop)
            stop = self.stop_long if long else self.stop_short
            entry = position.entry_fill_price
            if (stop >= entry if long else stop <= entry):
                return CloseIntent("BO-L0" if long else "BO-S0", timing="next_open")
            if p.bo_max_stop_mult > 0:
                stop = max(stop, entry - p.bo_max_stop_mult * self.arm_atr) if long else min(stop, entry + p.bo_max_stop_mult * self.arm_atr)
            if p.immediate_protection:
                stop = (stop/self.tick_size).to_integral_value(rounding=ROUND_FLOOR if long else ROUND_CEILING)*self.tick_size
            target = entry + (p.bo_target_mult * self.arm_atr if long else -p.bo_target_mult * self.arm_atr) if p.bo_target_mult > 0 else None
            if target is not None:
                # MC's measured BO targets normalize outward: sell limits up,
                # buy-to-cover limits down. Do not fill a fractional tick.
                target = (target / self.tick_size).to_integral_value(
                    rounding=ROUND_CEILING if long else ROUND_FLOOR) * self.tick_size
            return BracketIntent(stop, target)
        if self.armed and sm + 1 < fill_end:
            orders = []
            if self.ok_long:
                orders.append((EntryIntent(p.qty, "BO-L", timing="next_open", protection=self._protection(stop=self.stop_long)), self.level_long))
            if self.ok_short:
                orders.append((EntryIntent(p.qty, "BO-S", side="short", timing="next_open", protection=self._protection(stop=self.stop_short)), self.level_short))
            self.pending_setup = "BO"
            return StopEntriesIntent(tuple(orders))
        return None

    def validate_holding_bar(self, bar, position):
        # No future-row inference of an early close. If a held position misses
        # its configured session close, stop instead of filling an evening gap.
        plan = self._set_session(bar)
        if position is None or self.previous_stamp is None:
            return
        previous = self.previous_stamp.astimezone(CT).replace(tzinfo=None) + timedelta(minutes=self.p.clock_shift)
        current = bar.timestamp_utc.astimezone(CT).replace(tzinfo=None) + timedelta(minutes=self.p.clock_shift)
        close = previous.replace(hour=minutes(self.p.bo_session_close) // 60, minute=minutes(self.p.bo_session_close) % 60)
        if close < previous:
            close += timedelta(days=1)
        missed_close = previous < close < current
        if self.calendar is not None:
            holding_day = session_date(position.entry_time_utc)
            holding_plan = plan if plan.day == holding_day else self.calendar.plan(holding_day)
            if holding_plan.close is None:
                raise CalendarError("Held position belongs to a closed NQ/MNQ session; no liquidation price is invented.")
            close = holding_plan.close.replace(tzinfo=None)
            missed_close = bar.timestamp_utc > holding_plan.close.astimezone(timezone.utc)
        if missed_close:
            raise DatasetReadError(
                f"Held position crossed the configured session close {close:%Y-%m-%d %H:%M} "
                f"without a liquidation bar. Last observed bar: {previous:%Y-%m-%d %H:%M}; "
                f"next observed bar: {current:%Y-%m-%d %H:%M} (selected bar {bar.bar_number}). "
                f"Chicago strategy clock, ClockShift={self.p.clock_shift}; "
                f"holding {self.setup or 'unknown setup'} {position.side}, {position.contracts} contract(s). "
                "Review the strategy's shortened-session policy or source coverage. "
                "No session-close fill was invented."
            )

    def on_finish(self, last_bar, position):
        return CloseIntent("end_of_data") if position is not None else None

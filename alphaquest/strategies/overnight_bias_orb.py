"""Overnight Bias ORB source rules on 15-minute closes, with one-minute execution."""

from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo

from ..backtest_data import DatasetReadError
from ..session_calendar import load_calendar, resolve_calendar, session_date
from ..strategy import BracketIntent, CloseIntent, EntryIntent, EntryProtection
from ..strategy_sizing import SizingSupport
from . import vwap_pullback_risk_sizing as vwap

D = Decimal
ET = ZoneInfo("America/New_York")
STRATEGY_ID = "overnight_bias_orb"
DESCRIPTION = (
    "Overnight Bias ORB: civil-midnight overnight range, one direction set at the RTH open, "
    "and 15-minute close breakouts on Globex one-minute data. Eastern strategy clock. "
    "Next-Open entries with fill-bar stop and target anchored to the signal Close."
)
EXECUTION_ASSUMPTION = "overnight_bias_orb_15m_close_1m_magnifier_v1"
SUPPORTS_DECISION_CAPTURE = False
SIZING_SUPPORT = SizingSupport(
    fixed_path_check=lambda p: None,
    native_check=lambda p: "Overnight Bias ORB has no controlled account replay for its 15-minute decisions and fill-bar brackets.",
)


@dataclass(frozen=True, slots=True)
class Parameters:
    sess_start: int = vwap.integer(930, "RTH open, exclusive for opening range and RTH ATR, Eastern HHMM.", 0, 2359)
    or_end: int = vwap.integer(945, "Last opening-range bar close, Eastern HHMM.", 0, 2359)
    last_entry: int = vwap.integer(1300, "Last eligible breakout close, inclusive, Eastern HHMM.", 0, 2359)
    flat_time: int = vwap.integer(1530, "First held-bar close that sends a market exit for the next open, Eastern HHMM.", 0, 2359)
    sess_end: int = vwap.integer(1600, "Last bar included in RTH ATR, Eastern HHMM.", 0, 2359)
    max_trades_per_day: int = vwap.integer(4, "Maximum entry submissions per civil date.", 0)
    bias_long_min: Decimal = vwap.decimal("0.67", "Minimum open position in the overnight range for long bias.")
    bias_short_max: Decimal = vwap.decimal("0.33", "Maximum open position in the overnight range for short bias.")
    adx_len: int = vwap.integer(16, "Wilder ADX length in completed 15-minute bars.")
    adx_min: Decimal = vwap.decimal("20", "Minimum ADX on the breakout bar.")
    break_skip_mult: Decimal = vwap.decimal("2.5", "Maximum breakout bar range as a multiple of the prior range average.")
    bar_avg_len: int = vwap.integer(20, "Prior completed 15-minute bar ranges in the exhaustion average.")
    min_or_x: Decimal = vwap.decimal("0", "Minimum opening range as a multiple of the previous opening-range EMA.")
    max_or_x: Decimal = vwap.decimal("2", "Maximum opening range as a multiple of the previous opening-range EMA.")
    or_median_days: int = vwap.integer(20, "Opening-range EMA length and warm-up count. The source's reference is an EMA.")
    atr_k: Decimal = vwap.decimal("0.30", "Stop distance as a multiple of completed RTH daily ATR.")
    atr_days: int = vwap.integer(15, "Completed RTH days in the simple true-range average.", 1, 200)
    take_profit_rr: Decimal = vwap.decimal("3", "Target distance as a multiple of the initial stop distance.")
    num_contracts: int = vwap.integer(1, "Fixed contracts per entry.")
    max_bars_back: int = vwap.integer(250, "Leading 15-minute history bars before the source starts calculating.")
    use_session_calendar: bool = field(default=True, metadata={"description":
        "Use the reviewed NQ/MNQ calendar for SetExitOnClose, including scheduled early closes."})
    chart_session_close: int = vwap.integer(1700,
        "Fixed Globex chart close in Eastern HHMM when the reviewed calendar is disabled.", 0, 2359)

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if item.type is int:
                if type(value) is not int or not item.metadata["minimum"] <= value <= item.metadata.get("maximum", value):
                    raise ValueError(f"{item.name} is outside its supported integer range.")
                if item.metadata.get("maximum") == 2359 and value % 100 >= 60:
                    raise ValueError(f"{item.name} must be a valid Eastern HHMM time.")
            elif item.type is bool:
                if type(value) is not bool:
                    raise ValueError(f"{item.name} must be a boolean.")
            elif not isinstance(value, D) or not value.is_finite() or value < 0:
                raise ValueError(f"{item.name} must be a non-negative finite Decimal.")
        if self.max_bars_back < max(self.adx_len, self.bar_avg_len):
            raise ValueError("max_bars_back must cover adx_len and bar_avg_len.")


def source_fingerprint():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in (Path(__file__), Path(vwap.__file__), root / "strategy.py", root / "execution.py",
                 root / "ohlc_path.py", root / "session_calendar.py"):
        digest.update(path.name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def validate_dataset(dataset):
    if dataset.get("tick_data"):
        raise ValueError("Overnight Bias ORB uses one-minute OHLC magnification. Select a one-minute OHLC dataset.")
    interval = dataset.get("interval_seconds")
    if interval is not None and interval != 60:
        raise ValueError("Overnight Bias ORB requires close-labelled one-minute NQ/MNQ bars for magnified 15-minute replay.")


def validate_instrument(parameters, symbol):
    resolve_calendar(symbol)


@dataclass(slots=True)
class _Candle:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


class OvernightBiasORB:
    def __init__(self, parameters, *, execution_config, instrument_symbol="NQ"):
        self.p = parameters
        self.tick_size = execution_config.tick_size
        self.calendar = load_calendar(symbol=instrument_symbol) if self.p.use_session_calendar else None
        self.session_flattening = dict(
            enabled=True, mode="overnight_bias_orb_chart_close_v1", timezone=ET.key,
            order_timing="same_close", calendar=self.calendar.metadata() if self.calendar else None,
            chart_session_close=self.p.chart_session_close, flat_time=self.p.flat_time,
            fill="scheduled chart closing minute Close after active price exits; FlatTime is a separate next-Open exit",
        )
        self._held_day = self._held_close = None
        self._decision_stamp = self._candle = self._prior_day = None
        self._history = deque(maxlen=max(self.p.adx_len, self.p.bar_avg_len) + 1)
        self._adx = vwap._ADX(self.p.adx_len)
        self._count = 0
        self._daily_tr = deque(maxlen=self.p.atr_days)
        self.atr_ref = self._previous_rth_close = self.or_reference = D(0)
        self.or_count = 0
        self.regime_ok = True
        self.bracket = None
        self._reset_day(None)

    @contextmanager
    def prepare_replay(self, bars):
        # A next-bucket timestamp can identify a sparse candle's last observed
        # minute. That timestamp never contributes prices or gates to the candle.
        # Normal full candles complete without prefetching another minute.
        def decisions():
            pending = bucket = last = None
            has_minute_pair = False
            for bar in bars:
                stamp = bar.timestamp_utc
                if stamp.second or stamp.microsecond:
                    raise DatasetReadError("Overnight Bias ORB requires minute-aligned close stamps.")
                if not has_minute_pair and last is not None:
                    has_minute_pair = stamp - last == timedelta(minutes=1)
                last = stamp
                end = stamp + timedelta(minutes=(-stamp.minute) % 15)
                if pending is not None:
                    self._decision_stamp = bucket if bucket != end else None
                    yield pending
                pending, bucket = bar, end
                if stamp == end:
                    self._decision_stamp = end
                    yield bar
                    pending = None
            if pending is not None:
                self._decision_stamp = None  # EOF inside a candle does not complete it.
                yield pending
            if not has_minute_pair:
                raise DatasetReadError("Overnight Bias ORB needs observed one-minute data, including consecutive minute closes.")

        yield decisions()

    def _reset_day(self, candle):
        self._rth = None
        self.or_high, self.or_low = D(0), D(999999)
        self.or_done = False
        self.submissions = 0
        self.session_open, self.bias = D(0), 0
        self.on_high, self.on_low = (candle.high, candle.low) if candle else (D(0), D(999999))

    def _roll_day(self, candle):
        if self._rth is not None:
            rth = self._rth
            tr = rth.high - rth.low
            if self._previous_rth_close > 0:
                tr = max(tr, abs(rth.high - self._previous_rth_close), abs(rth.low - self._previous_rth_close))
            self._daily_tr.append(tr)
            self._previous_rth_close = rth.close
        self.atr_ref = sum(self._daily_tr, D(0)) / self.p.atr_days if len(self._daily_tr) == self.p.atr_days else D(0)
        self._reset_day(candle)

    def _step(self, stamp, candle, position):
        p = self.p
        local = stamp.astimezone(ET)
        day = local.date()
        hhmm = 100 * local.hour + local.minute
        self._count += 1
        prior_day, self._prior_day = self._prior_day, day
        self._history.append(candle)
        if self._count <= p.max_bars_back:
            return None

        if day != prior_day:
            self._roll_day(candle)
        elif hhmm <= p.sess_start:
            self.on_high = max(self.on_high, candle.high)
            self.on_low = min(self.on_low, candle.low)
        if p.sess_start < hhmm <= p.sess_end:
            if self._rth is None:
                self._rth = _Candle(candle.open, candle.high, candle.low, candle.close)
            else:
                self._include(self._rth, candle)

        if p.sess_start < hhmm <= p.or_end:
            if self.session_open == 0:
                self.session_open = candle.open
                if self.on_high > self.on_low:
                    opening_position = (self.session_open - self.on_low) / (self.on_high - self.on_low)
                    self.bias = 1 if opening_position >= p.bias_long_min else -1 if opening_position <= p.bias_short_max else 9
            self.or_high = max(self.or_high, candle.high)
            self.or_low = min(self.or_low, candle.low)
        if not self.or_done and hhmm > p.or_end and self.or_high > 0:
            self.or_done = True
            width = self.or_high - self.or_low
            self.or_count += 1
            self.regime_ok = (
                self.or_count < p.or_median_days
                or self.or_reference <= 0
                or p.min_or_x * self.or_reference <= width <= p.max_or_x * self.or_reference
            )
            self.or_reference = (self.or_reference + D(2) / (p.or_median_days + 1) * (width - self.or_reference)
                                 if self.or_reference else width)

        adx = self._adx.update(self._history)
        stop_points = p.atr_k * self.atr_ref
        if position is not None:
            if hhmm >= p.flat_time:
                return CloseIntent("XL" if position.side == "long" else "XS", "next_open")
            return None
        if not (self.or_done and self.regime_ok and adx >= p.adx_min and stop_points > 0
                and p.or_end < hhmm <= p.last_entry and self.submissions < p.max_trades_per_day):
            return None
        long_break = candle.close > self.or_high
        short_break = candle.close < self.or_low
        if not ((long_break and self.bias == 1) or (not long_break and short_break and self.bias == -1)):
            return None
        prior = list(self._history)[-(p.bar_avg_len + 1):-1]
        prior_average = sum((b.high - b.low for b in prior), D(0)) / p.bar_avg_len
        if prior_average != 0 and candle.high - candle.low > p.break_skip_mult * prior_average:
            return None

        sign = 1 if long_break else -1
        stop = candle.close - sign * stop_points
        target = candle.close + sign * stop_points * p.take_profit_rr
        # On tick-grid prices the inequalities imply these outward trigger ticks.
        stop = self._round(stop, upward=not long_break)
        target = self._round(target, upward=long_break)
        self.bracket = BracketIntent(stop, target)
        self.submissions += 1
        return EntryIntent(p.num_contracts, "ORB_L" if long_break else "ORB_S",
                           side="long" if long_break else "short", timing="next_open", initial_stop=stop,
                           protection=EntryProtection(stop_price=stop, target_price=target))

    def _round(self, price, *, upward):
        return (price / self.tick_size).to_integral_value(rounding=ROUND_CEILING if upward else ROUND_FLOOR) * self.tick_size

    @staticmethod
    def _include(candle, bar):
        candle.high = max(candle.high, bar.high)
        candle.low = min(candle.low, bar.low)
        candle.close = bar.close

    def _session_close(self, position):
        day = session_date(position.entry_time_utc)
        if self._held_day != day:
            if self.calendar is None:
                hh, mm = divmod(self.p.chart_session_close, 100)
                close = datetime.combine(day, time(hh, mm), ET)
            else:
                close = self.calendar.plan(day).close
                if close is None:
                    raise DatasetReadError(f"Overnight Bias ORB position belongs to closed Globex session {day}.")
            self._held_day, self._held_close = day, close
        return self._held_close

    def validate_holding_bar(self, bar, position):
        if position is not None and bar.timestamp_utc > self._session_close(position):
            raise DatasetReadError("Overnight Bias ORB held exposure past a missing scheduled close minute.")

    def on_bar(self, bar, position):
        if self._candle is None:
            self._candle = _Candle(bar.open, bar.high, bar.low, bar.close)
        else:
            self._include(self._candle, bar)
        order = None
        if self._decision_stamp is not None:
            order = self._step(self._decision_stamp, self._candle, position)
            self._candle = None
        if position is None:
            return order
        if bar.timestamp_utc == self._session_close(position):
            return CloseIntent("session_close")
        # A 15-minute order stays active across each constituent minute.
        return order or self.bracket

    def on_finish(self, last_bar, position):
        if position is not None:
            raise DatasetReadError("Overnight Bias ORB data ended while the strategy was still holding a position.")
        return None

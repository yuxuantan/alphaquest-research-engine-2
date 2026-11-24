"""Noise PowerLanguage rules on 15-minute closes with one-minute execution."""

from collections import deque
from dataclasses import dataclass, field, fields
from datetime import timedelta
from decimal import Decimal
import hashlib
from itertools import islice
from pathlib import Path
from zoneinfo import ZoneInfo

from ..backtest_data import DatasetReadError
from ..execution import ExecutionError, protection_bracket
from ..session_calendar import CalendarError, resolve_calendar
from ..strategy import CloseIntent, EntryIntent, EntryProtection, ReverseIntent
from ..strategy_sizing import SizingSupport
from .vwap_pullback_risk_sizing import decimal, integer

CT = ZoneInfo("America/Chicago")
MINUTE = timedelta(minutes=1)
STRATEGY_ID = "noise"
DESCRIPTION = (
    "Noise trades directional 15-minute NQ/MNQ closes outside bands built from prior "
    "same-slot moves. Central chart dates, next-open orders and fill-relative protection."
)
EXECUTION_ASSUMPTION = "noise_15m_close_1m_magnifier_v1"
SUPPORTS_DECISION_CAPTURE = False
SIZING_SUPPORT = SizingSupport(
    fixed_path_check=lambda p: None if p.contracts_per_trade > 0 else "Noise requires positive fixed contracts for saved-path sizing.",
    native_check=lambda p: "Noise has no controlled account replay for paired reversals and can carry across sessions when the exact flat bar is absent.",
)


@dataclass(frozen=True, slots=True)
class Parameters:
    lookback_days: int = integer(20, "Prior observations of each 15-minute slot.", 1, 100)
    volatility_multiplier: Decimal = decimal("1.0", "Scale of the mean absolute same-slot move.")
    ema_length: int = integer(20, "Close EMA length in 15-minute bars.")
    stop_loss_points: Decimal = decimal("50", "Positive fill-relative stop distance in points.")
    contracts_per_trade: int = integer(2, "Fixed entry size. Zero disables entries.", 0)
    reward_risk: Decimal = decimal("0.5", "Positive target distance as a multiple of stop distance.")
    long_trade: bool = field(default=True, metadata={"description": "Enable long entries and long reversal signals."})
    short_trade: bool = field(default=True, metadata={"description": "Enable short entries and short reversal signals."})
    max_trades_per_day: int = integer(10, "Maximum entry submissions per Central chart date, including reversals.", 0)
    max_stops_per_day: int = integer(3, "Block new entries after this many full-stop-sized losses on the chart date.", 0)
    first_eval_time: int = integer(900, "First evaluation time in Central HHMM.", 0, 2359)
    last_entry_time: int = integer(1400, "Last eligible entry signal in Central HHMM, inclusive.", 0, 2359)
    flat_signal_time: int = integer(1430, "Exact Central HHMM close that sends the next-open flat order.", 0, 2359)
    max_bars_back: int = integer(1, "Leading completed 15-minute candles reserved before calculation. Match the PowerLanguage chart.")

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if item.type is int:
                if type(value) is not int or not item.metadata["minimum"] <= value <= item.metadata.get("maximum", value):
                    raise ValueError(f"{item.name} is outside its supported integer range.")
                if item.name.endswith("_time") and value % 100 >= 60:
                    raise ValueError(f"{item.name} must be a valid Central HHMM time.")
            elif item.type is bool:
                if type(value) is not bool:
                    raise ValueError(f"{item.name} must be a boolean.")
            elif not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError(f"{item.name} must be a non-negative finite decimal.")
        if self.stop_loss_points <= 0 or self.reward_risk <= 0:
            raise ValueError("Noise requires positive stop and target distances.")


def source_fingerprint():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in (Path(__file__), root / "strategy.py", root / "execution.py", root / "ohlc_path.py"):
        digest.update(path.name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def validate_dataset(dataset):
    if dataset.get("tick_data") or dataset.get("interval_seconds") not in (None, 60):
        raise ValueError("Noise requires close-labelled one-minute NQ/MNQ OHLC data for its 15-minute decisions.")


def validate_instrument(parameters, symbol):
    try:
        resolve_calendar(symbol)
    except CalendarError:
        raise ValueError("Noise requires a dataset with an explicit NQ or MNQ symbol.") from None


def backtest_assumptions(parameters):
    return dict(
        enabled=True, mode="noise_exact_chart_time_v1", timezone=CT.key,
        flat_time=parameters.flat_signal_time, order_timing="next_open",
        fill="exact 15-minute clock match only; no fallback on shortened sessions",
    )


def _minutes(hhmm):
    return hhmm // 100 * 60 + hhmm % 100


class Noise:
    def __init__(self, parameters, *, execution_config):
        self.p = parameters
        self.tick_size = execution_config.tick_size
        self.protection = EntryProtection(
            stop_distance=parameters.stop_loss_points,
            target_distance=parameters.stop_loss_points * parameters.reward_risk,
        )
        self.loss_threshold = -parameters.stop_loss_points * execution_config.point_value * parameters.contracts_per_trade
        self._alpha = Decimal(2) / (parameters.ema_length + 1)
        self._slot_start = _minutes(parameters.first_eval_time)
        self._history = [deque(maxlen=100) for _ in range(22)]
        self._previous_stamp = self._bucket_end = None
        self._has_minute_pair = False
        self._candle_count = 0
        self._prior_date = self._prior_close = None
        self._anchor_open = self._anchor_prior_close = Decimal(0)
        self._ema = None
        self._last_trade = None
        self._last_total_trades = 0
        self._entries = self._stops = 0
        self._bracket = None

    def on_entry_fill(self, entry, position):
        self._bracket = protection_bracket(entry.protection, position, self.tick_size)

    def on_trade_closed(self, trade):
        self._last_trade = trade
        self._bracket = None

    def _enter(self, side, reason):
        self._entries += 1
        return EntryIntent(self.p.contracts_per_trade, reason, side=side, timing="next_open", protection=self.protection)

    def _decide(self, stamp, opening, close, position):
        self._candle_count += 1
        day = stamp.date()
        prior_date, prior_close = self._prior_date, self._prior_close
        self._prior_date, self._prior_close = day, close
        if self._candle_count <= self.p.max_bars_back:
            return None
        p = self.p
        total = self._last_trade.trade_number if self._last_trade is not None else 0
        if self._candle_count == p.max_bars_back + 1:
            self._last_total_trades = total
        if day != prior_date:
            self._anchor_open = opening
            if self._candle_count > p.max_bars_back + 1:
                self._anchor_prior_close = prior_close
            self._entries = self._stops = 0
            self._last_total_trades = total
        if total > self._last_total_trades:
            # PowerLanguage samples the latest closed position once per decision bar.
            self._stops += self._last_trade.net_pnl <= self.loss_threshold
            self._last_total_trades = total

        self._ema = close if self._ema is None else self._ema + self._alpha * (close - self._ema)
        hhmm = 100 * stamp.hour + stamp.minute
        if hhmm == p.flat_signal_time and position is not None:
            return CloseIntent("FlatLong1430" if position.side == "long" else "FlatShort1430", "next_open")
        if not (p.first_eval_time <= hhmm <= p.flat_signal_time
                and self._anchor_open > 0 and self._anchor_prior_close > 0):
            return None
        slot = (_minutes(hhmm) - self._slot_start) // 15
        if not 0 <= slot < len(self._history):
            return None
        history = self._history[slot]
        if len(history) >= p.lookback_days:
            band = sum(islice(history, p.lookback_days)) / p.lookback_days * p.volatility_multiplier
        else:
            band = None
        history.appendleft(abs(close / self._anchor_open - 1))
        if band is None or hhmm == p.flat_signal_time:
            return None

        upper = max(self._anchor_open, self._anchor_prior_close) * (1 + band)
        lower = min(self._anchor_open, self._anchor_prior_close) * (1 - band)
        long_signal = hhmm <= p.last_entry_time and p.long_trade and close > upper and close > opening
        short_signal = hhmm <= p.last_entry_time and p.short_trade and close < lower and close < opening
        may_enter = p.contracts_per_trade >= 1 and self._entries < p.max_trades_per_day and self._stops < p.max_stops_per_day
        if position is None:
            if may_enter and long_signal:
                return self._enter("long", "NoiseLong")
            if may_enter and short_signal:
                return self._enter("short", "NoiseShort")
        elif position.side == "long":
            if short_signal:
                exit_order = CloseIntent("LongRevExit", "next_open")
                return ReverseIntent(exit_order, self._enter("short", "RevToShort")) if may_enter else exit_order
            if close < max(upper, self._ema):
                return CloseIntent("LongEMAExit", "next_open")
        else:
            if long_signal:
                exit_order = CloseIntent("ShortRevExit", "next_open")
                return ReverseIntent(exit_order, self._enter("long", "RevToLong")) if may_enter else exit_order
            if close > min(lower, self._ema):
                return CloseIntent("ShortEMAExit", "next_open")
        return None

    def on_bar(self, bar, position):
        stamp = bar.timestamp_utc
        if stamp.second or stamp.microsecond:
            raise DatasetReadError("Noise requires minute-aligned close stamps.")
        self._has_minute_pair |= self._previous_stamp is not None and stamp - self._previous_stamp == MINUTE
        self._previous_stamp = stamp
        end = stamp + timedelta(minutes=(-stamp.minute) % 15)
        if self._bucket_end != end:
            self._bucket_end, self._bucket_open = end, bar.open
        # An exact observed boundary completes a candle. A missing boundary
        # cannot generate the source's clock exit or borrow a later Open.
        if stamp == end:
            order = self._decide(stamp.astimezone(CT), self._bucket_open, bar.close, position)
            if order is not None:
                return order
        return self._bracket if position is not None else None

    def on_finish(self, last_bar, position):
        if not self._has_minute_pair:
            raise DatasetReadError("Noise needs observed one-minute OHLC, including consecutive minute closes.")
        if position is not None:
            raise ExecutionError("Noise replay ended with an open position. Extend the selected window through an actual exit.")
        return None

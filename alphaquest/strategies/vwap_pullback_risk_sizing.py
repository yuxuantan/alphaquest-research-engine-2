"""Causal port of the retained PowerLanguage VWAP pullback risk-sizing signal.

See docs/strategies/vwap_pullback_risk_sizing.md for execution and parity limits.
"""

from collections import deque
from dataclasses import dataclass, field, fields
from decimal import Decimal, localcontext
import logging
from zoneinfo import ZoneInfo

from ..strategy import Bar, BracketIntent, CloseIntent, EntryIntent, ExecutionConfig, Position


STRATEGY_ID = "vwap_pullback_risk_sizing"
DESCRIPTION = (
    "PowerLanguage VWAP pullback: close-latched opening-range break, VWAP retest/reclaim, "
    "confirmed pivot target, pivot or pullback stop, ADX elevation/decay gates, fixed or risk sizing. "
    "Chicago time; full-session 1-minute close-labelled bars. Next-bar Open market fills; "
    "brackets start after the entry bar, stop first if both levels hit. EOD next-bar flatten."
)
EXECUTION_ASSUMPTION = "next_open_market_next_bar_bracket_stop_first"
CT = ZoneInfo("America/Chicago")
LOG = logging.getLogger(__name__)
D = Decimal


def integer(default, description, minimum=1, maximum=None):
    metadata = {"description": description, "minimum": minimum}
    if maximum is not None:
        metadata["maximum"] = maximum
    return field(default=default, metadata=metadata)


def decimal(default, description):
    return field(default=D(default), metadata={"description": description, "minimum": "0"})


def boolean(default, description):
    return field(default=default, metadata={"description": description})


@dataclass(frozen=True, slots=True)
class Parameters:
    use_vol_sizing: bool = boolean(False, "Use risk-budget sizing instead of fixed contracts.")
    position_size: int = integer(1, "Fixed contracts; source Inputs default is 1.")
    mm_capital_usd: Decimal = decimal("500000", "Capital used only for the sizing risk budget.")
    mm_risk_pct: Decimal = decimal("2.0", "Risk budget as percent of sizing capital.")
    max_contracts: int = integer(1, "Contract ceiling for risk sizing only.")
    trade_longs: bool = boolean(True, "Enable long entries.")
    trade_shorts: bool = boolean(False, "Enable short entries.")
    min_rr: Decimal = decimal("0", "Minimum signal-close reward/risk; zero disables.")
    max_stop_points: Decimal = decimal("0", "Maximum signal-close stop distance; zero disables.")
    use_adx_elev: bool = boolean(True, "Require signal-bar ADX at or above threshold.")
    adx_elev_thr: Decimal = decimal("20", "ADX elevation threshold.")
    use_adx_decay: bool = boolean(True, "Require ADX <= its lookback value; preserves retest latches.")
    adx_decay_lb: int = integer(1, "Bars back for ADX decay comparison.")
    adx_len: int = integer(14, "Directional movement and ADX smoothing length.")
    retest_mode: int = integer(1, "1: touch VWAP; 2: close through then reclaim.", maximum=2)
    stop_mode: int = integer(1, "1: confirmed pivot; 2: pullback extreme.", maximum=2)
    max_trades_per_day: int = integer(1, "Maximum orders submitted per reset day.", minimum=0)
    stop_swing_len: int = integer(20, "Strict pivot strength on each side for stops.")
    target_swing_len: int = integer(5, "Strict pivot strength on each side for targets.")
    buffer_mode: int = integer(2, "1: ticks; 2: points.", maximum=2)
    buffer_amount: Decimal = decimal("0", "Outward stop buffer.")
    or_start_time: int = integer(830, "Opening range start, exclusive, Chicago HHMM.", 0, 2359)
    or_end_time: int = integer(900, "Opening range end, inclusive, Chicago HHMM.", 0, 2359)
    vwap_start_time: int = integer(830, "VWAP start, exclusive, Chicago HHMM.", 0, 2359)
    vwap_end_time: int = integer(1700, "VWAP end, inclusive, Chicago HHMM.", 0, 2359)
    entry_start_time: int = integer(900, "Entry start, exclusive, Chicago HHMM.", 0, 2359)
    entry_end_time: int = integer(1700, "Entry end, inclusive, Chicago HHMM.", 0, 2359)
    day_reset_time: int = integer(2300, "Reset only when Time > reset and previous Time <= reset.", 0, 2359)
    use_eod_flat: bool = boolean(True, "Request a next-bar market exit at EOD.")
    eod_flat_time: int = integer(1555, "EOD trigger Chicago HHMM, before reset time.", 0, 2359)
    plot_trade_levels: bool = boolean(True, "Log signal-bar entry details through Python logging.")
    max_bars_back: int = integer(42, "Leading history bars before PowerLanguage CurrentBar=1.")

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if item.type is bool:
                if type(value) is not bool:
                    raise ValueError(f"{item.name} must be a boolean.")
            elif item.type is int:
                if type(value) is not int or value < item.metadata["minimum"]:
                    raise ValueError(f"{item.name} must be an integer >= {item.metadata['minimum']}.")
                if "maximum" in item.metadata and value > item.metadata["maximum"]:
                    raise ValueError(f"{item.name} exceeds {item.metadata['maximum']}.")
                if item.name.endswith("_time") and value % 100 >= 60:
                    raise ValueError(f"{item.name} must be a valid HHMM time.")
            elif not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError(f"{item.name} must be a non-negative finite Decimal.")
        if self.max_bars_back < max(2 * self.stop_swing_len, 2 * self.target_swing_len, self.adx_len, self.adx_decay_lb):
            raise ValueError("max_bars_back must cover both pivot windows, ADX length and decay lookback.")


class _ADX:
    """DirMovement initialization and Wilder recurrence, with bounded history.

    Initial DM/TR means use Len changes ending at CurrentBar=1. The first Len
    DX values use a cumulative mean; subsequent ADX values use Wilder smoothing.
    MultiCharts reference: https://www.multicharts.cn/post?idno=181
    """

    def __init__(self, length):
        self.length = length
        self.count = 0
        self.plus = self.minus = self.tr = self.total_dx = self.value = D(0)

    @staticmethod
    def movement(bar, previous):
        up, down = bar.high - previous.high, previous.low - bar.low
        return (max(up, D(0)) if up > down else D(0),
                max(down, D(0)) if down > up else D(0),
                max(bar.high, previous.close) - min(bar.low, previous.close))

    def update(self, history):
        n = D(self.length)
        if self.count == 0:
            changes = [self.movement(history[-i], history[-i - 1]) for i in range(1, self.length + 1)]
            self.plus, self.minus, self.tr = (sum((row[j] for row in changes), D(0)) / n for j in range(3))
        else:
            plus, minus, tr = self.movement(history[-1], history[-2])
            self.plus += (plus - self.plus) / n
            self.minus += (minus - self.minus) / n
            self.tr += (tr - self.tr) / n
        # The common TR divisor cancels in DX; a flat series has DX=0.
        total = self.plus + self.minus
        dx = D(100) * abs(self.plus - self.minus) / total if self.tr > 0 and total > 0 else D(0)
        self.count += 1
        if self.count <= self.length:
            self.total_dx += dx
            self.value = self.total_dx / D(self.count)
        else:
            self.value += (dx - self.value) / n
        return self.value


class VwapPullbackRiskSizing:
    def __init__(self, parameters: Parameters | None = None, *, execution_config: ExecutionConfig):
        if parameters is not None and type(parameters) is not Parameters:
            raise TypeError("parameters must be Parameters.")
        if type(execution_config) is not ExecutionConfig:
            raise TypeError("execution_config must be ExecutionConfig.")
        self.parameters = parameters or Parameters()
        self.config = execution_config
        p = self.parameters
        self._history = deque(maxlen=p.max_bars_back + 1)
        self._adx = _ADX(p.adx_len)
        self._adx_history = deque(maxlen=p.adx_decay_lb + 1)
        self.current_bar = 0
        self._seen = 0
        self._previous_time = None
        self._previous_orb = self._previous_vwap = False
        self._previous_long_latched = self._previous_short_latched = False
        self.orb_high = self.orb_low = self.ny_vwap = D(0)
        self._cum_pv = self._cum_vol = D(0)
        self.orb_ready = False
        self.trades_today = 0
        self._clear_latches()
        self.pullback_low = self.pullback_high = D(0)
        self.last_stop_high = self.last_stop_low = None
        self.last_target_high = self.last_target_low = None
        self.active_stop = self.active_target = D(0)
        self.adx_value = D(0)

    def _clear_latches(self):
        self.long_orb_broken = self.short_orb_broken = False
        self.long_vwap_touched = self.short_vwap_touched = False
        self.long_closed_through = self.short_closed_through = False

    def _pivots(self, strength):
        if self.current_bar <= 2 * strength:
            return None, None
        window = list(self._history)[-(2 * strength + 1):]
        candidate = window[strength]
        others = window[:strength] + window[strength + 1:]
        high = candidate.high if all(other.high < candidate.high for other in others) else None
        low = candidate.low if all(other.low > candidate.low for other in others) else None
        return high, low

    def _quantity(self, distance):
        p = self.parameters
        if not p.use_vol_sizing:
            return p.position_size
        risk = p.mm_capital_usd * p.mm_risk_pct / D(100)
        per_contract = (distance + 2 * self.config.tick_size) * self.config.point_value
        # Integer ratios avoid rounding a quotient up across a contract boundary.
        numerator, denominator = risk.as_integer_ratio()
        cost_numerator, cost_denominator = per_contract.as_integer_ratio()
        return min((numerator * cost_denominator) // (denominator * cost_numerator), p.max_contracts)

    def on_bar(self, bar: Bar, position: Position | None):
        # Fix indicator precision independently of callers; account money still uses
        # the engine's exact Decimal arithmetic. PL itself uses binary doubles.
        with localcontext() as context:
            context.prec = 50
            return self._on_bar(bar, position)

    def _on_bar(self, bar, position):
        p = self.parameters
        self._history.append(bar)
        self._seen += 1
        if self._seen <= p.max_bars_back:
            return None
        self.current_bar += 1
        local = bar.timestamp_utc.astimezone(CT)
        time = local.hour * 100 + local.minute
        in_orb = p.or_start_time < time <= p.or_end_time
        in_vwap = p.vwap_start_time < time <= p.vwap_end_time
        in_entry = p.entry_start_time < time <= p.entry_end_time
        self.adx_value = self._adx.update(self._history)
        self._adx_history.append(self.adx_value)
        old_adx = self._adx_history[0] if len(self._adx_history) > p.adx_decay_lb else D(0)
        adx_ok = ((not p.use_adx_elev or self.adx_value >= p.adx_elev_thr)
                  and (not p.use_adx_decay or self.adx_value <= old_adx))

        if self.current_bar == 1 or (time > p.day_reset_time and self._previous_time <= p.day_reset_time):
            self.trades_today = 0
            self.orb_ready = False
            self._clear_latches()
        if in_orb and not self._previous_orb:
            self.orb_high, self.orb_low = bar.high, bar.low
            self.orb_ready = False
        if in_orb:
            self.orb_high = max(self.orb_high, bar.high)
            self.orb_low = min(self.orb_low, bar.low)
        if not in_orb and self._previous_orb:
            self.orb_ready = True
        if in_vwap:
            volume = bar.volume if bar.volume > 0 else D(1)
            pv = (bar.high + bar.low + bar.close) / D(3) * volume
            if not self._previous_vwap:
                self._cum_pv, self._cum_vol = pv, volume
            else:
                self._cum_pv += pv
                self._cum_vol += volume
            self.ny_vwap = self._cum_pv / self._cum_vol
        for strength, prefix in ((p.stop_swing_len, "stop"), (p.target_swing_len, "target")):
            high, low = self._pivots(strength)
            if high is not None:
                setattr(self, f"last_{prefix}_high", high)
            if low is not None:
                setattr(self, f"last_{prefix}_low", low)
        track = self.orb_ready and not in_orb
        if track and bar.close > self.orb_high:
            self.long_orb_broken = True
        if track and bar.close < self.orb_low:
            self.short_orb_broken = True
        long_signal = short_signal = False
        if track and in_vwap and in_entry:
            if self.long_orb_broken:
                if p.retest_mode == 1:
                    self.long_vwap_touched |= bar.low <= self.ny_vwap
                    long_signal = self.long_vwap_touched and bar.close > self.ny_vwap
                else:
                    self.long_closed_through |= bar.close < self.ny_vwap
                    long_signal = self.long_closed_through and bar.close > self.ny_vwap
            if self.short_orb_broken:
                if p.retest_mode == 1:
                    self.short_vwap_touched |= bar.high >= self.ny_vwap
                    short_signal = self.short_vwap_touched and bar.close < self.ny_vwap
                else:
                    self.short_closed_through |= bar.close > self.ny_vwap
                    short_signal = self.short_closed_through and bar.close < self.ny_vwap
        long_latched = self.long_vwap_touched or self.long_closed_through
        short_latched = self.short_vwap_touched or self.short_closed_through
        if long_latched:
            self.pullback_low = (bar.low if not self._previous_long_latched else min(self.pullback_low, bar.low))
        if short_latched:
            self.pullback_high = (bar.high if not self._previous_short_latched else max(self.pullback_high, bar.high))
        # PL's longLatched/shortLatched series survive the entry block's flag clear.
        self._previous_long_latched, self._previous_short_latched = long_latched, short_latched
        self._previous_time, self._previous_orb, self._previous_vwap = time, in_orb, in_vwap

        if position is not None:
            if p.use_eod_flat and p.eod_flat_time <= time < p.day_reset_time:
                return CloseIntent("eod_flat", timing="next_open")
            return BracketIntent(self.active_stop, self.active_target)
        if self.trades_today >= p.max_trades_per_day or not adx_ok:
            return None
        buffer = p.buffer_amount * self.config.tick_size if p.buffer_mode == 1 else p.buffer_amount
        for side, signal, enabled, latched, pivot, extreme, target in (
            ("long", long_signal, p.trade_longs, long_latched, self.last_stop_low, self.pullback_low, self.last_target_high),
            ("short", short_signal, p.trade_shorts, short_latched, self.last_stop_high, self.pullback_high, self.last_target_low),
        ):
            if not signal or not enabled or target is None or (p.stop_mode == 1 and pivot is None) or (p.stop_mode == 2 and not latched):
                continue
            direction = 1 if side == "long" else -1
            stop = (extreme if p.stop_mode == 2 else pivot) - direction * buffer
            distance = direction * (bar.close - stop)
            reward = direction * (target - bar.close)
            if distance <= 0 or reward <= 0:
                continue
            if p.max_stop_points != 0 and distance > p.max_stop_points:
                continue
            if p.min_rr != 0 and reward < p.min_rr * distance:
                continue
            quantity = self._quantity(distance)
            if quantity < 1:
                continue
            self.active_stop, self.active_target = stop, target
            self.trades_today += 1
            self._clear_latches()
            if p.plot_trade_levels:
                LOG.info("%s %s qty=%s close=%s stop=%s target=%s stopDist=%s adx=%s",
                         local.isoformat(), side.upper(), quantity, bar.close, stop, target, distance, self.adx_value)
            return EntryIntent(quantity, "vwap_pullback", side=side, timing="next_open")
        return None

    def on_finish(self, last_bar: Bar, position: Position | None):
        # Explicit repository completion policy, additional to the PL source.
        return CloseIntent("end_of_data") if position is not None else None

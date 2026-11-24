"""RelStrength_v3 on synchronized, close-labelled NQ/ES one-minute bars."""

from dataclasses import dataclass, field, fields
from decimal import Decimal
import hashlib
from math import log, sqrt
from pathlib import Path
from zoneinfo import ZoneInfo

from ..datasets import PAIRED_COLUMNS
from ..execution import ExecutionError
from ..session_calendar import CalendarError, resolve_calendar
from ..strategy import BracketIntent, CloseIntent, EntryIntent
from ..strategy_sizing import SizingSupport
from .vwap_pullback_risk_sizing import boolean, integer


STRATEGY_ID = "relative_strength"
DESCRIPTION = (
    "Relative Strength trades NQ or MNQ continuation when its 09:00 CT move diverges "
    "from the move implied by ES. Requires aligned one-minute OHLCV with an ESClose column."
)
EXECUTION_ASSUMPTION = "relative_strength_1m_next_open_delayed_bracket_v1"
CT = ZoneInfo("America/Chicago")
SIZING_SUPPORT = SizingSupport(
    fixed_path_check=lambda p: None,
    native_check=lambda p: (
        "Relative Strength has no controlled sizing replay. Its original stop, when "
        "enabled, is submitted after the entry bar closes."
    ),
)

# Exact union of the source's NYSE full holidays and early closes. Chart date
# codes are YYYYMMDD with year minus 1900, as in the supplied PowerLanguage.
HOLIDAYS = frozenset({
    1100101, 1100118, 1100215, 1100402, 1100531, 1100705, 1100906, 1101125, 1101126, 1101224,
    1110117, 1110221, 1110422, 1110530, 1110704, 1110905, 1111124, 1111125, 1111226, 1120102,
    1120116, 1120220, 1120406, 1120528, 1120703, 1120704, 1120903, 1121029, 1121030, 1121122,
    1121123, 1121224, 1121225, 1130101, 1130121, 1130218, 1130329, 1130527, 1130703, 1130704,
    1130902, 1131128, 1131129, 1131224, 1131225, 1140101, 1140120, 1140217, 1140418, 1140526,
    1140703, 1140704, 1140901, 1141127, 1141128, 1141224, 1141225, 1150101, 1150119, 1150216,
    1150403, 1150525, 1150703, 1150907, 1151126, 1151127, 1151224, 1151225, 1160101, 1160118,
    1160215, 1160325, 1160530, 1160704, 1160905, 1161124, 1161125, 1161226, 1170102, 1170116,
    1170220, 1170414, 1170529, 1170703, 1170704, 1170904, 1171123, 1171124, 1171225, 1180101,
    1180115, 1180219, 1180330, 1180528, 1180703, 1180704, 1180903, 1181122, 1181123, 1181205,
    1181224, 1181225, 1190101, 1190121, 1190218, 1190419, 1190527, 1190703, 1190704, 1190902,
    1191128, 1191129, 1191224, 1191225, 1200101, 1200120, 1200217, 1200410, 1200525, 1200703,
    1200907, 1201126, 1201127, 1201224, 1201225, 1210101, 1210118, 1210215, 1210402, 1210531,
    1210705, 1210906, 1211125, 1211126, 1211224, 1220117, 1220221, 1220415, 1220530, 1220620,
    1220704, 1220905, 1221124, 1221125, 1221226, 1230102, 1230116, 1230220, 1230407, 1230529,
    1230619, 1230703, 1230704, 1230904, 1231123, 1231124, 1231225, 1240101, 1240115, 1240219,
    1240329, 1240527, 1240619, 1240703, 1240704, 1240902, 1241128, 1241129, 1241224, 1241225,
    1250101, 1250109, 1250120, 1250217, 1250418, 1250526, 1250619, 1250703, 1250704, 1250901,
    1251127, 1251128, 1251224, 1251225, 1260101, 1260119, 1260216, 1260403, 1260525, 1260619,
    1260703, 1260907, 1261126, 1261127, 1261224, 1261225, 1270101, 1270118, 1270215, 1270326,
    1270531, 1270618, 1270705, 1270906, 1271125, 1271126, 1271224,
})


def digits(default, description):
    return field(default=Decimal(default), metadata={"description": description})


@dataclass(frozen=True, slots=True)
class Parameters:
    decide_hhmm: int = integer(900, "First eligible decision close in Central HHMM.", 0, 2359)
    z_min: Decimal = digits("1.25", "Symmetric entry Z threshold.")
    beta_days: int = integer(20, "Day-equivalent span of the exponential return moments.")
    stop_frac: Decimal = digits("0.6", "Stop distance as a multiple of average RTH high–low range. Zero or negative disables the stop.")
    tgt_frac: Decimal = digits("1.0", "Target distance as a multiple of average RTH high–low range. Zero or negative disables the target.")
    atr_days: int = integer(20, "Completed clean RTH ranges to average. The source clamps this to 1–60.", -2147483648, 2147483647)
    trade_dir: int = field(default=0, metadata={"description": "Trade direction. −1 short only, 0 both, 1 long only.",
                                                "minimum": -1, "maximum": 1, "refinement_kind": "categorical"})
    num_contracts: int = integer(1, "Fixed contracts of the selected primary instrument.")
    rth_start_hhmm: int = integer(830, "Central RTH start. Include closes strictly after this time.", 0, 2359)
    rth_end_hhmm: int = integer(1500, "Central RTH end. Include closes through this time.", 0, 2359)
    flat_hhmm: int = integer(1500, "Flatten on the current Close at or after this Central HHMM.", 0, 2359)
    skip_holidays: bool = boolean(True, "Skip the original NYSE full and early closures from 2010 through 2027.")

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if item.type is int:
                if type(value) is not int or not item.metadata["minimum"] <= value <= item.metadata.get("maximum", value):
                    raise ValueError(f"{item.name} is outside its supported integer range.")
                if item.name.endswith("_hhmm") and value % 100 >= 60:
                    raise ValueError(f"{item.name} must be a valid Central HHMM time.")
            elif item.type is bool:
                if type(value) is not bool:
                    raise ValueError(f"{item.name} must be a boolean.")
            elif not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{item.name} must be a finite Decimal.")


def source_fingerprint():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in (Path(__file__), root / "strategy.py", root / "execution.py",
                 root / "ohlc_path.py", root / "datasets.py", root / "backtest_data.py"):
        digest.update(path.name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def validate_instrument(parameters, symbol):
    try:
        resolve_calendar(symbol)
    except CalendarError:
        raise ValueError("Relative Strength requires an explicit NQ or MNQ primary symbol.") from None


def validate_dataset(dataset):
    if dataset.get("columns") != PAIRED_COLUMNS or dataset.get("tick_data"):
        raise ValueError("Relative Strength requires paired one-minute NQ/MNQ and ES data with an ESClose column.")


def backtest_assumptions(parameters):
    return dict(enabled=True, mode="relative_strength_chart_close_v1", timezone=CT.key,
                flat_time=parameters.flat_hhmm, rth_start=parameters.rth_start_hhmm,
                order_timing="same_close", holiday_table="Supplied NYSE dates 2010–2027",
                skip_holidays=parameters.skip_holidays,
                signal_data="ESClose at the same timestamp in the hashed primary dataset",
                entry_protection="Stop and target first active after the entry bar closes")


def _minutes(hhmm):
    return hhmm // 100 * 60 + hhmm % 100


class RelativeStrength:
    def __init__(self, parameters):
        self.p = parameters
        self.bars_day = max(_minutes(parameters.rth_end_hhmm) - _minutes(parameters.rth_start_hhmm), 1)
        self.alpha = 2 / (parameters.beta_days * self.bars_day + 1)
        self.z_min = float(parameters.z_min)
        self.stop_frac = float(parameters.stop_frac)
        self.tgt_frac = float(parameters.tgt_frac)
        self.atr_use = min(max(parameters.atr_days, 1), 60)
        self.ranges = []
        self.range_index = 0
        self.average_range = 0.0
        self.previous_clock = None
        self.first_calculation = True
        self.day_ok = True
        self.entries_today = 0
        self.rth_high = self.rth_low = None
        self.last_rth_ok = False
        self.anchor_nq = self.anchor_es = 0.0
        self.bars_since_anchor = 0
        self.decided = True
        self.samples = 0
        self.covariance = self.nq_second_moment = self.es_second_moment = 0.0
        self.beta = self.residual_variance = 0.0
        self.previous_side = None
        self.bracket = None

    def _start_rth(self, high, low, last_nq, last_es):
        if self.last_rth_ok:
            extent = self.rth_high - self.rth_low
            if len(self.ranges) < self.atr_use:
                self.ranges.append(extent)
            else:
                self.ranges[self.range_index] = extent
            self.range_index = (self.range_index + 1) % self.atr_use
        if self.ranges:
            self.average_range = sum(self.ranges, 0.0) / len(self.ranges)
        self.rth_high, self.rth_low = high, low
        self.last_rth_ok = self.day_ok
        self.anchor_nq, self.anchor_es = last_nq, last_es
        self.bars_since_anchor = 0
        self.decided = False

    def _update_moments(self, nq, es, last_nq, last_es):
        ret_nq = 10000 * log(nq / last_nq)
        ret_es = 10000 * log(es / last_es)
        product, nq_squared, es_squared = ret_nq * ret_es, ret_nq * ret_nq, ret_es * ret_es
        if self.samples == 0:
            self.covariance, self.nq_second_moment, self.es_second_moment = product, nq_squared, es_squared
        else:
            self.covariance += self.alpha * (product - self.covariance)
            self.nq_second_moment += self.alpha * (nq_squared - self.nq_second_moment)
            self.es_second_moment += self.alpha * (es_squared - self.es_second_moment)
        self.samples += 1
        if self.nq_second_moment > 0 and self.es_second_moment > 0:
            self.beta = self.covariance / self.es_second_moment
            self.residual_variance = (self.nq_second_moment - 2 * self.beta * self.covariance
                                      + (self.beta * self.beta) * self.es_second_moment)

    def _decide(self, nq, es):
        self.decided = True
        if not (self.day_ok and self.bars_since_anchor >= 1 and self.samples >= 5 * self.bars_day
                and self.residual_variance > 0 and self.anchor_nq > 0 and self.anchor_es > 0 and es > 0):
            return 0
        residual = 10000 * log(nq / self.anchor_nq) - self.beta * 10000 * log(es / self.anchor_es)
        z = residual / sqrt(self.residual_variance * self.bars_since_anchor)
        if z <= -self.z_min:
            return -1
        return int(z >= self.z_min)

    def _entry_bracket(self, position):
        if self.average_range <= 0:
            return None
        direction = 1 if position.side == "long" else -1
        fill = float(position.entry_fill_price)
        stop = Decimal(str(fill - direction * self.stop_frac * self.average_range)) if self.stop_frac > 0 else None
        target = Decimal(str(fill + direction * self.tgt_frac * self.average_range)) if self.tgt_frac > 0 else None
        return BracketIntent(stop, target) if stop is not None or target is not None else None

    def on_bar(self, bar, position):
        if bar.es_close is None:
            raise ExecutionError("Relative Strength requires the aligned ES close on every bar.")
        stamp = bar.timestamp_utc.astimezone(CT)
        day, hhmm = stamp.date(), stamp.hour * 100 + stamp.minute
        nq, es = float(bar.close), float(bar.es_close)
        previous = self.previous_clock
        self.previous_clock = (day, hhmm, nq, es)
        if previous is None:  # One leading bar for Close[1] and Data2's prior close.
            return None
        last_day, last_hhmm, last_nq, last_es = previous
        p = self.p
        if self.first_calculation or day != last_day:
            self.entries_today = 0
            self.day_ok = not p.skip_holidays or (day.year - 1900) * 10000 + day.month * 100 + day.day not in HOLIDAYS
        if self.first_calculation:
            last_es = 0.0  # C2[1] is the initialized series variable on CurrentBar 1.
            self.first_calculation = False
        rth = p.rth_start_hhmm < hhmm <= p.rth_end_hhmm
        new_rth = rth and (day != last_day or not p.rth_start_hhmm < last_hhmm <= p.rth_end_hhmm)

        side = position.side if position else None
        if position is not None and side != self.previous_side:
            self.entries_today += 1
            self.bracket = self._entry_bracket(position)
        self.previous_side = side

        if new_rth:
            self._start_rth(float(bar.high), float(bar.low), last_nq, last_es)
        elif rth:  # The source's uninitialized range variables are zero.
            self.rth_high = max(self.rth_high or 0.0, float(bar.high))
            self.rth_low = min(self.rth_low or 0.0, float(bar.low))
        if rth and self.anchor_nq > 0:
            self.bars_since_anchor += 1
        if rth and self.day_ok and last_nq > 0 and last_es > 0 and es > 0:
            self._update_moments(nq, es, last_nq, last_es)

        signal = self._decide(nq, es) if rth and not self.decided and hhmm >= p.decide_hhmm else 0
        if position is not None:
            if hhmm >= p.flat_hhmm or hhmm <= p.rth_start_hhmm:
                return CloseIntent("RS.LF" if side == "long" else "RS.SF")
            return self.bracket
        if signal and self.entries_today == 0 and hhmm < p.flat_hhmm:
            if signal > 0 and p.trade_dir >= 0:
                return EntryIntent(p.num_contracts, "RS.L", side="long", timing="next_open")
            if signal < 0 and p.trade_dir <= 0:
                return EntryIntent(p.num_contracts, "RS.S", side="short", timing="next_open")
        return None

    def on_finish(self, last_bar, position):
        return CloseIntent("end_of_data") if position else None

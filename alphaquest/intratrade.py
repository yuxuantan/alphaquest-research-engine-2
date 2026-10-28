"""Streaming OHLC excursion bounds over the bars actually held by a position.

These are account-equity excursions including entry costs, not tick MAE/MFE.
A limit exit's unknown ordering is retained as a bound, never a fabricated path.
"""
from dataclasses import dataclass
import json
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from .decimal_math import subtract, multiply

VERSION = 'held-ohlc-equity-bounds-v1'
ZERO = Decimal(0)
CHICAGO = ZoneInfo('America/Chicago')


def session(stamp):
    return (stamp.astimezone(CHICAGO).replace(tzinfo=None) + timedelta(hours=7)).date()


@dataclass(frozen=True, slots=True)
class IntratradeRisk:
    trade_number: int
    side: str
    entry_time_utc: datetime
    exit_time_utc: datetime
    contracts: int
    net_pnl: Decimal
    mae_lower: Decimal
    mae_upper: Decimal
    mfe_lower: Decimal
    mfe_upper: Decimal
    entry_phase: str
    exit_phase: str
    full_bars: int
    cross_session: bool
    adverse_path: str


class RiskCapture:
    def __init__(self, position, config, commission, reference, phase):
        self.position, self.config, self.commission = position, config, commission
        self.entry_phase = phase
        self.mae_lower = self.mae_upper = self.mfe_lower = self.mfe_upper = ZERO
        self.full_bars = 0
        self.cross_session = False
        self.adverse_path = []
        self.observe_price(reference, gap=True)

    def value(self, price):
        signed = self.position.contracts * (1 if self.position.side == 'long' else -1)
        return subtract(multiply(multiply(subtract(price, self.position.entry_fill_price), Decimal(signed)), self.config.point_value), self.commission)

    def observe_value(self, value, *, bounded=False, gap=False):
        adverse, favorable = max(ZERO, value.copy_negate()), max(ZERO, value)
        if adverse > self.mae_upper:
            self.adverse_path.append([str(adverse), gap])
        self.mae_upper = max(self.mae_upper, adverse)
        self.mfe_upper = max(self.mfe_upper, favorable)
        if not bounded:
            self.mae_lower = max(self.mae_lower, adverse)
            self.mfe_lower = max(self.mfe_lower, favorable)

    def observe_price(self, price, *, bounded=False, gap=False):
        self.observe_value(self.value(price), bounded=bounded, gap=gap)

    def observe_bar(self, bar, phase='held', reference=None):
        self.cross_session |= session(bar.timestamp_utc) != session(self.position.entry_time_utc)
        self.observe_price(bar.open, gap=True)
        if phase == 'held':
            self.observe_price(bar.high)
            self.observe_price(bar.low)
            self.full_bars += 1
        elif phase == 'stop':
            # Before a stop fill the adverse stop level is reached; prices past
            # it are outside the holding interval. Favorable ordering is unknown.
            favorable = bar.high if self.position.side == 'long' else bar.low
            self.observe_price(favorable, bounded=True)
            self.observe_price(reference)
        elif phase == 'target':
            adverse = bar.low if self.position.side == 'long' else bar.high
            self.observe_price(adverse, bounded=True)
            self.observe_price(reference)

    def finish(self, trade, phase):
        self.observe_value(trade.net_pnl, gap=True)
        return IntratradeRisk(trade.trade_number, trade.side, trade.entry_time_utc,
            trade.exit_time_utc, trade.contracts, trade.net_pnl, self.mae_lower,
            self.mae_upper, self.mfe_lower, self.mfe_upper, self.entry_phase, phase,
            self.full_bars, self.cross_session, json.dumps(self.adverse_path,separators=(",", ":")))

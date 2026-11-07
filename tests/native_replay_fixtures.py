"""Synthetic observed MNQ bars and independent native-replay arithmetic oracles."""
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import json

from alphaquest.strategies.vwap_pullback_risk_sizing import Parameters
from alphaquest.reporting import json_value
from alphaquest.strategy import Bar

CT = ZoneInfo('America/Chicago')


def parameters(*, eod=True):
    return Parameters(use_vol_sizing=False, position_size=1, trade_longs=True, trade_shorts=False,
                      use_adx_elev=False, use_adx_decay=False, stop_swing_len=1, target_swing_len=1,
                      max_trades_per_day=1, day_reset_time=700, use_eod_flat=eod, plot_trade_levels=False)


def parameter_values():
    """Actual native backtest request values, including required EOD-flat support."""
    return json.loads(json.dumps(asdict(parameters()), default=json_value))


def bars(*, days=3, gap=False, skip_retry=False, payout=False):
    """Every minute is generated synthetic input, never imputed missing market data.

    Full sessions are previous-day 17:01 through session-date 16:00 Chicago.
    Stops and targets are confirmed pivots before the 09:01 signal close.
    Brackets activate only after the actual next-open entry bar.
    """
    result = []
    day = date(2026, 1, 5)
    for index in range(days):
        while day.weekday() > 4:
            day += timedelta(days=1)
        current = datetime.combine(day - timedelta(days=1), time(17, 1), CT)
        close = datetime.combine(day, time(16), CT)
        while current <= close:
            local_time = current.strftime('%H:%M')
            prices = ('116', '117', '115', '116')
            if current.date() == day:
                if local_time == '08:00': prices = ('116', '128', '115', '116')
                if local_time == '08:10': prices = ('116', '117', '108' if index == 2 else '113', '116')
                if local_time == '09:01': prices = ('116', '119', '115', '118')
                if local_time == '09:02': prices = ('120' if gap and index == 0 else '118', '121', '117', '120')
                if local_time == '09:03': prices = ('120', '120.5', '112', '114') if index == 0 else ('120', '129', '119', '128')
                if payout:
                    if local_time == '08:00': prices = ('116', '268', '115', '116')
                    if local_time == '08:10': prices = ('116', '117', '113', '116')
                    if local_time == '09:03': prices = ('120', '269', '119', '268')
                if skip_retry and index == 0:
                    later = {
                        '09:04': ('118', '119', '118', '118'),
                        '09:05': ('118', '118.5', '117.75', '118'),
                        '09:06': ('118', '118.5', '118', '118'),
                        '09:07': ('118', '118.5', '118', '118.25'),
                        '09:08': ('118.25', '121.25', '118', '121'),
                    }
                    prices = later.get(local_time, prices)
            stamp = current.astimezone(timezone.utc)
            cells = (stamp.strftime('%m/%d/%Y'), stamp.strftime('%H:%M'), *prices, '1', '1', '0')
            result.append(Bar(len(result) + 1, stamp, cells[0], cells[1], *map(Decimal, cells[2:]), cells))
            current += timedelta(minutes=1)
        day += timedelta(days=1)
    return result


def source_bytes(**kwargs):
    header = 'Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol\n'
    return (header + ''.join(','.join(row.source_fields) + '\n' for row in bars(**kwargs))).encode()


EXPECTED = {
    'instrument': {'symbol': 'MNQ', 'point_value': '2', 'tick_size': '0.25'},
    'source_costs': {'slippage_ticks': 0, 'commission_per_contract_per_side': '0'},
    'signal_closes': ['118', '118', '118'], 'known_stops': ['113', '113', '108'],
    'normal_source_quantities': [1, 1, 1], 'normal_source_nets': ['-10', '20', '20'],
    'percentage': {'risk_percent': '0.2', 'decision_balances': ['50000', '49900', '50080'],
                   'quantities': [10, 9, 5], 'trade_nets': ['-100', '180', '100'], 'final_balance': '50180'},
    'gap_percentage': {'first_fill': '120', 'decision_balances': ['50000', '49860', '50040'],
                       'quantities': [10, 9, 5], 'trade_nets': ['-140', '180', '100'], 'final_balance': '50140'},
    'fixed_dollars': {'risk_dollars': '100', 'quantities': [10, 10, 5],
                      'trade_nets': ['-100', '200', '100'], 'final_balance': '50200'},
    'skip_retry': {'risk_dollars': '1', 'later_decision_chicago': '09:06', 'later_stop': '117.75',
                   'later_entry_chicago': '09:07', 'quantity': 2, 'target': '121', 'trade_net': '12'},
    'payout': {'days': 7, 'contracts': 3, 'daily_net': '900', 'trading_profit': '6300',
               'gross_deduction': '1500', 'cash_received': '1500', 'pending_cash': '0',
               'request_date': '2026-01-09', 'receipt_date': '2026-01-11',
               'final_provider_balance': '54800', 'final_native_trading_equity': '16300'},
}

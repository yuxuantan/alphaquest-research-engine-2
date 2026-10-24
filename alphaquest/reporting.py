"""Strategy-agnostic summaries and disk-backed exports of authoritative events."""

from collections.abc import Callable, Iterable
import csv
from dataclasses import asdict, fields
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from .decimal_math import add, multiply, subtract
from .execution import EquityPoint, TIMESTAMP_CONVENTION, Trade
from .strategy import ExecutionConfig


ZERO = Decimal(0)
TRADE_FIELDS = [field.name for field in fields(Trade)]
EQUITY_FIELDS = ["trade_number", "exit_time_utc", "net_pnl", "equity"]


class ReportError(ValueError):
    """The event stream cannot produce a reconciled completed report."""


def json_value(value):
    """Money stays exact decimal text; timestamps use aware UTC ISO 8601."""
    if isinstance(value, Decimal) and value.is_finite():
        return str(value)
    if isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() == timedelta(0):
        return value.isoformat().replace("+00:00", "Z")
    raise TypeError(f"Unsupported report value: {type(value).__name__}")


def _record(event) -> dict:
    for field in fields(event):
        value = getattr(event, field.name)
        if field.type is Decimal and (not isinstance(value, Decimal) or not value.is_finite()):
            raise ReportError(f"{type(event).__name__}.{field.name} must be a finite Decimal.")
        if field.type is int and type(value) is not int:
            raise ReportError(f"{type(event).__name__}.{field.name} must be an integer.")
    return asdict(event)


def _utc(value) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ReportError(message)


def _csv_record(record: dict) -> dict:
    return {key: json_value(value) if isinstance(value, (Decimal, datetime)) else value for key, value in record.items()}


def generate_report(
    events: Iterable[Trade | EquityPoint], output_directory: Path, config: ExecutionConfig,
    *, metadata: dict | None = None, expected_bar_count: int | None = None,
    on_saving: Callable[[], None] | None = None,
) -> dict:
    """Exhaust engine outputs once and publish report.json, trades.csv, equity.csv.

    The returned manifest has summary/checks, while the JSON on disk additionally
    contains full `trades` and `equity` arrays. Arrays and CSVs stream through
    temporary files with bounded memory. A new output directory is required;
    errors remove staging files and publish no completed report. Pass the saved
    row count to detect a prematurely truncated stream that happened to be flat.

    No strategy is called here, and no fill, commission, or unrealized-P&L formula
    is repeated. Equity values and all trade details are preserved from events.
    equity.csv contains starting equity and one row per completed trade, using
    the corresponding flat engine equity point after all exit costs. The JSON
    retains the full bar-close equity series for reconciliation.
    """
    if type(config) is not ExecutionConfig:
        raise ReportError("config must be an ExecutionConfig.")
    if expected_bar_count is not None and (type(expected_bar_count) is not int or expected_bar_count < 1):
        raise ReportError("expected_bar_count must be an integer >= 1.")
    destination = Path(output_directory)
    if destination.exists():
        raise FileExistsError(f"Report output directory already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    total_gross = total_commissions = total_net = total_slippage = ZERO
    trade_count = winning = losing = breakeven = 0
    previous_trade = pending_trade = initial = last = None
    saw_exposure = False
    with TemporaryDirectory(prefix=".alphaquest-report-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "complete"
        staging.mkdir()
        trades_path, equity_path = Path(temporary) / "trades.array", Path(temporary) / "equity.array"
        with (
            trades_path.open("w", encoding="utf-8") as trade_array,
            equity_path.open("w", encoding="utf-8") as equity_array,
            (staging / "trades.csv").open("w", encoding="utf-8", newline="") as trades_csv,
            (staging / "equity.csv").open("w", encoding="utf-8", newline="") as equity_csv,
        ):
            trade_writer = csv.DictWriter(trades_csv, fieldnames=TRADE_FIELDS)
            equity_writer = csv.DictWriter(equity_csv, fieldnames=EQUITY_FIELDS)
            trade_writer.writeheader()
            equity_writer.writeheader()
            trade_array.write("[")
            equity_array.write("[")
            for event in events:
                _check(type(event) in (Trade, EquityPoint), f"Unsupported report event: {type(event).__name__}")
                record = _record(event)
                if type(event) is Trade:
                    _check(last is not None, "Initial equity must precede trades.")
                    _check(pending_trade is None, "Missing equity point after completed trade.")
                    _check(event.trade_number == trade_count + 1, "Trade numbers must be contiguous from 1.")
                    _check(event.side == "long" and event.contracts > 0, "Unsupported trade side or quantity.")
                    _check(1 <= event.entry_bar_number <= event.exit_bar_number == last.bar_number + 1,
                           "Trade bar numbers do not match the equity stream.")
                    _check(_utc(event.entry_time_utc) and _utc(event.exit_time_utc)
                           and event.entry_time_utc <= event.exit_time_utc, "Trade timestamps must be chronological UTC.")
                    _check(event.exit_deadline_utc is None or (_utc(event.exit_deadline_utc)
                           and event.exit_deadline_utc >= event.entry_time_utc), "Invalid trade deadline.")
                    if previous_trade is not None:
                        _check(event.entry_bar_number > previous_trade.exit_bar_number
                               and event.entry_time_utc > previous_trade.exit_time_utc, "Trades overlap or re-enter on an exit bar.")
                    _check(subtract(event.gross_pnl, event.total_commissions) == event.net_pnl,
                           "Trade gross P&L minus commissions does not equal its net P&L.")
                    _check(add(event.entry_commission, event.exit_commission) == event.total_commissions,
                           "Trade commission fields do not reconcile.")
                    total_gross = add(total_gross, event.gross_pnl)
                    total_commissions = add(total_commissions, event.total_commissions)
                    total_net = add(total_net, event.net_pnl)
                    total_slippage = add(total_slippage, event.slippage_cost)
                    winning += event.net_pnl > 0
                    losing += event.net_pnl < 0
                    breakeven += event.net_pnl == 0
                    if trade_count:
                        trade_array.write(",\n")
                    json.dump(record, trade_array, default=json_value, allow_nan=False)
                    trade_writer.writerow(_csv_record(record))
                    trade_count += 1
                    previous_trade = pending_trade = event
                else:
                    _check(event.position_contracts >= 0, "Position quantity must be non-negative.")
                    saw_exposure = saw_exposure or event.position_contracts != 0
                    _check(add(event.cash_balance, event.unrealized_pnl) == event.equity, "Equity does not equal cash plus unrealized P&L.")
                    _check(subtract(event.cash_balance, config.initial_capital) == event.realized_net_pnl,
                           "Realized net P&L does not reconcile with cash.")
                    _check(event.position_contracts != 0 or event.unrealized_pnl == 0, "Flat equity has nonzero unrealized P&L.")
                    if last is None:
                        _check(event.bar_number == 0 and event.timestamp_utc is None and event.position_contracts == 0
                               and event.cash_balance == event.equity == config.initial_capital,
                               "Initial equity must be bar 0, null timestamp, flat, and equal to initial capital.")
                        initial = event
                        equity_writer.writerow(_csv_record({
                            "trade_number": 0, "exit_time_utc": None,
                            "net_pnl": ZERO, "equity": event.equity,
                        }))
                    else:
                        _check(event.bar_number == last.bar_number + 1 and _utc(event.timestamp_utc),
                               "Equity points must be contiguous bars with UTC timestamps.")
                        _check(last.timestamp_utc is None or event.timestamp_utc > last.timestamp_utc,
                               "Equity timestamps must be strictly increasing.")
                        equity_array.write(",\n")
                    if pending_trade is not None:
                        _check(event.bar_number == pending_trade.exit_bar_number
                               and event.timestamp_utc == pending_trade.exit_time_utc and event.position_contracts == 0,
                               "Exit equity must match the trade's exit bar/time and finish flat.")
                        _check(last.position_contracts == (pending_trade.contracts if pending_trade.entry_bar_number < pending_trade.exit_bar_number else 0),
                               "Closing trade quantity does not match the preceding position.")
                        equity_writer.writerow(_csv_record({
                            "trade_number": pending_trade.trade_number,
                            "exit_time_utc": pending_trade.exit_time_utc,
                            "net_pnl": pending_trade.net_pnl, "equity": event.equity,
                        }))
                        pending_trade = None
                    elif last is not None and last.position_contracts:
                        _check(event.position_contracts == last.position_contracts,
                               "Position changed without a completed trade.")
                    json.dump(record, equity_array, default=json_value, allow_nan=False)
                    last = event
            trade_array.write("]")
            equity_array.write("]")
        _check(initial is not None and last.bar_number > 0, "Report requires initial equity and at least one observed bar.")
        _check(pending_trade is None, "Missing final equity point after trade.")
        _check(expected_bar_count is None or last.bar_number == expected_bar_count, "Equity bar count does not match the saved dataset.")
        _check(last.position_contracts == 0 and last.unrealized_pnl == 0, "Completed report must finish flat.")
        _check(subtract(total_gross, total_commissions) == total_net, "Aggregate gross/commission/net P&L does not reconcile.")
        _check(last.equity == add(config.initial_capital, total_net), "Final equity does not equal initial capital plus trade net P&L.")
        if not trade_count:
            _check(not saw_exposure and total_gross == total_commissions == total_net == total_slippage == 0,
                   "No-trade results cannot contain exposure or nonzero monetary totals.")
        win_rate = None if not trade_count else Context(prec=28, rounding=ROUND_HALF_EVEN).divide(
            multiply(Decimal(winning), Decimal(100)), Decimal(trade_count),
        )
        summary = {
            "initial_capital": initial.equity, "final_equity": last.equity,
            "trades_taken": trade_count, "winning_trades": winning, "losing_trades": losing,
            "breakeven_trades": breakeven, "win_rate_pct": win_rate,
            "total_gross_pnl": total_gross, "total_slippage_cost": total_slippage,
            "total_commissions": total_commissions, "total_net_pnl": total_net,
            "ending_position_contracts": last.position_contracts,
        }
        manifest = {
            "format_version": 1, "status": "complete",
            "created_at_utc": datetime.now(timezone.utc),
            "timestamp_convention": TIMESTAMP_CONVENTION,
            "execution_assumption": "same_close_full_fill",
            "execution_settings": asdict(config), "run_metadata": metadata or {},
            "summary": summary,
            "reconciliation": {
                "total_net_equals_sum_trade_net": True,
                "gross_minus_commissions_equals_net": True,
                "final_equity_equals_initial_plus_net": True,
                "equity_equals_cash_plus_unrealized_at_every_point": True,
                "realized_net_equals_cash_minus_initial_at_every_point": True,
                "final_position_flat": True,
                "observed_bar_count": last.bar_number,
                "expected_bar_count": expected_bar_count,
            },
            "artifacts": {"report": "report.json", "trades_csv": "trades.csv", "equity_csv": "equity.csv"},
        }
        if on_saving is not None:
            on_saving()
        with (staging / "report.json").open("w", encoding="utf-8") as report:
            header = json.dumps(manifest, default=json_value, allow_nan=False, indent=2)
            report.write(header[:-1])
            for name, path in (("trades", trades_path), ("equity", equity_path)):
                report.write(f',\n"{name}": ')
                with path.open(encoding="utf-8") as source:
                    shutil.copyfileobj(source, report, length=1024 * 1024)
            report.write("\n}\n")
        if destination.exists():
            raise FileExistsError(f"Report output directory already exists: {destination}")
        staging.rename(destination)
    return manifest

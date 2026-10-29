"""Saved price-series holding comparisons using authoritative native equity/fills.

The holding account shares the execution engine's fill, cost and mark arithmetic.
Only observations from the selected replay enter this bounded-memory recorder.
No strategy is replayed when a saved comparison is read.
"""

import csv
from dataclasses import asdict
from decimal import Context, Decimal
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .decimal_math import add, multiply, subtract
from .drawdown import Drawdown
from .execution import _Account
from .strategy import CloseIntent, EntryIntent


VERSION = "price-series-holding-v1"
ZERO = Decimal(0)
FIELDS = ["bar_number", "timestamp_utc", "close", "strategy_equity", "holding_equity",
          "excess_net_pnl", "strategy_contracts", "holding_contracts"]
SERIES = ("strategy_equity", "holding_equity", "excess_net_pnl")


class BenchmarkSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contracts: StrictInt = Field(default=1, ge=1, le=9007199254740991)


def ratio(numerator, denominator):
    return Context(prec=28).divide(numerator, denominator) if denominator else None


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class MarketBenchmark:
    def __init__(self, config, settings, metadata, bar_count, *, source_backtest_id=None):
        self.config = config
        self.settings = BenchmarkSettings.model_validate(settings or {})
        self.metadata = metadata
        self.bar_count = bar_count
        self.source_backtest_id = source_backtest_id
        self.account = _Account(config)
        self.bar = None
        self.count = 0
        self.trackers = None
        self.minimum = [config.initial_capital, config.initial_capital]
        self.notional_total = [ZERO, ZERO]
        self.notional_max = [ZERO, ZERO]
        self.max_contracts = [0, self.settings.contracts]
        self.previous = [config.initial_capital, config.initial_capital]
        self.months = {}
        self.zone = ZoneInfo(metadata["dataset"]["source_timezone"])

    def set_bar(self, bar):
        # Called in actual execution order, after any strategy preparation pass.
        # execute emits the preceding equity before advancing this observation.
        self.bar = bar

    def start(self, staging, stack):
        stream = stack.enter_context((staging / "market_equity.csv").open("w", encoding="utf-8", newline=""))
        self.writer = csv.DictWriter(stream, fieldnames=FIELDS)
        self.writer.writeheader()

    def observe(self, point):
        if point.bar_number == 0:
            self.writer.writerow(dict(bar_number=0, timestamp_utc="", close="",
                                      strategy_equity=self.config.initial_capital,
                                      holding_equity=self.config.initial_capital,
                                      excess_net_pnl=0, strategy_contracts=0, holding_contracts=0))
            return
        bar = self.bar
        if bar is None or point.bar_number != self.count + 1 or bar.bar_number != point.bar_number or bar.timestamp_utc != point.timestamp_utc:
            raise ValueError("Market comparison bars and native equity do not align.")
        self.count += 1
        if self.count == 1:
            self.start_time = bar.timestamp_utc
            self.trackers = [Drawdown(self.config.initial_capital, bar.timestamp_utc) for _ in range(2)]
            self.account.apply(EntryIntent(self.settings.contracts, "holding_start"), bar, reference=bar.open, phase="open")
            self.entry = dict(bar_number=bar.bar_number, timestamp_utc=bar.timestamp_utc,
                              reference_price=bar.open, fill_price=self.account.position.entry_fill_price)
        if self.count == self.bar_count:
            self.trade = self.account.apply(CloseIntent("holding_end"), bar, finishing=True)
        held = self.account.mark(bar)
        values = [point.equity, held.equity]
        month = bar.timestamp_utc.astimezone(self.zone).strftime("%Y-%m")
        totals = self.months.setdefault(month, [ZERO, ZERO])
        for i, (value, quantity) in enumerate(zip(values, [point.position_contracts, held.position_contracts])):
            self.trackers[i].observe(bar.timestamp_utc, value)
            self.minimum[i] = min(self.minimum[i], value)
            self.max_contracts[i] = max(self.max_contracts[i], quantity)
            notional = multiply(multiply(bar.close, Decimal(quantity)), self.config.point_value).copy_abs()
            self.notional_total[i] = add(self.notional_total[i], notional)
            self.notional_max[i] = max(self.notional_max[i], notional)
            totals[i] = add(totals[i], subtract(value, self.previous[i]))
        self.previous = values
        self.end_time = bar.timestamp_utc
        self.writer.writerow(dict(bar_number=point.bar_number, timestamp_utc=bar.timestamp_utc.isoformat().replace("+00:00", "Z"),
                                  close=bar.close, strategy_equity=point.equity, holding_equity=held.equity,
                                  excess_net_pnl=subtract(point.equity, held.equity),
                                  strategy_contracts=point.position_contracts, holding_contracts=held.position_contracts))

    def finish(self, staging, summary):
        from .reporting import json_value
        if self.count != self.bar_count or self.previous[0] != summary["final_equity"]:
            raise ValueError("Market comparison does not reconcile to the native report.")
        # Read authoritative trades, including quantities/exposure completed on
        # a single bar which cannot be inferred from post-close positions.
        duration_quantity = duration = ZERO
        shorts = 0
        with (staging / "trades.csv").open(encoding="utf-8", newline="") as source:
            for trade in csv.DictReader(source):
                held_seconds = multiply(Decimal(trade["actual_holding_minutes"]), Decimal(60))
                duration = add(duration, held_seconds)
                quantity = int(trade["contracts"])
                duration_quantity = add(duration_quantity, multiply(held_seconds, Decimal(quantity)))
                self.max_contracts[0] = max(self.max_contracts[0], quantity)
                shorts += trade["side"] == "short"
        elapsed = self.end_time - self.start_time
        seconds = Decimal(f"{elapsed.days * 86400 + elapsed.seconds}.{elapsed.microseconds:06d}")
        accounts = {}
        for i, name in enumerate(("strategy", "holding")):
            pnl = subtract(self.previous[i], self.config.initial_capital)
            accounts[name] = dict(net_pnl=pnl, final_equity=self.previous[i],
                                  return_pct=ratio(multiply(pnl, Decimal(100)), self.config.initial_capital),
                                  **self.trackers[i].finish(self.end_time),
                                  minimum_equity=self.minimum[i], nonpositive_equity=self.minimum[i] <= 0,
                                  max_contracts=self.max_contracts[i],
                                  average_bar_close_notional=ratio(self.notional_total[i], Decimal(self.count)),
                                  maximum_bar_close_notional=self.notional_max[i],
                                  maximum_bar_close_leverage=ratio(self.notional_max[i], self.config.initial_capital))
        accounts["strategy"].update(total_commissions=summary["total_commissions"], total_slippage_cost=summary["total_slippage_cost"],
                                     time_in_market_pct=ratio(multiply(duration, Decimal(100)), seconds),
                                     average_contracts_while_held=ratio(duration_quantity, duration), short_trades=shorts)
        accounts["holding"].update(total_commissions=self.trade.total_commissions, total_slippage_cost=self.trade.slippage_cost,
                                    time_in_market_pct=Decimal(100) if seconds else None,
                                    average_contracts_while_held=Decimal(self.settings.contracts))
        periods = [dict(period=month, strategy_net_pnl=values[0], holding_net_pnl=values[1], excess_net_pnl=subtract(*values))
                   for month, values in self.months.items()]
        years = {}
        for month, values in self.months.items():
            total = years.setdefault(month[:4], [ZERO, ZERO])
            for i in range(2):
                total[i] = add(total[i], values[i])
        data = dict(version=VERSION, settings=self.settings.model_dump(), classification="price_series_comparison",
                    calculation_source_sha256={name: file_hash(Path(__file__).with_name(name)) for name in ('market_benchmark.py', 'execution.py', 'reporting.py', 'drawdown.py', 'decimal_math.py')},
                    executable_futures_performance="unverified",
                    source=dict(backtest_id=self.source_backtest_id, dataset=self.metadata["dataset"], instrument=self.metadata["instrument"],
                                selection=self.metadata["selection"], research=self.metadata.get("research"),
                                strategy=self.metadata["strategy"], execution_settings=asdict(self.config)),
                    source_checks=dict(selected_bars_equal_native_equity=True, final_strategy_equity_reconciles=True,
                                       original_source_integrity="validated by the backtest source reader",
                                       contract_identity="not established by the dataset contract",
                                       roll_prices_and_costs="not recorded", corporate_actions="not recorded"),
                    assumptions=["Fixed long quantity chosen before replay; no compounding or risk matching.",
                                 "Holding enters at the first selected Open and exits at the final selected Close; both fills include native adverse slippage and commission.",
                                 "Timestamps identify bar closes, including Open fills; they are not measured execution times.",
                                 "Bar-close mark-to-market drawdowns exclude intrabar paths. Existing trade-close metrics are preserved.",
                                 "Exposure duration uses saved fill-bar timestamps; average/maximum notional samples post-fill bar closes and can miss intrabar peaks.",
                                 "No contract rolls, dividends, cash interest, borrowing charges or margin liquidation are modelled. Do not add carry costs already embedded in futures prices.",
                                 "A stitched price gap may distort holding P&L. This is a price-series diagnostic, not verified executable futures or ETF total return.",
                                 "After nonpositive equity, hypothetical arithmetic continues without margin enforcement; no annualized return is reported.",
                                 "Strategy historical execution assumptions, including any session-close lookahead, still apply."],
                    period_start_utc=self.start_time, period_end_utc=self.end_time, observed_bar_count=self.count,
                    initial_capital=self.config.initial_capital, accounts=accounts,
                    excess_net_pnl=subtract(accounts["strategy"]["net_pnl"], accounts["holding"]["net_pnl"]),
                    entry=self.entry, holding_trade=asdict(self.trade), monthly=periods,
                    yearly=[dict(period=year, strategy_net_pnl=v[0], holding_net_pnl=v[1], excess_net_pnl=subtract(*v)) for year, v in years.items()])
        equity_hash = file_hash(staging / "market_equity.csv")
        data["equity_sha256"] = equity_hash
        (staging / "market_benchmark.json").write_text(json.dumps(data, default=json_value, allow_nan=False, indent=2) + "\n", encoding="utf-8")
        return dict(version=VERSION, settings=self.settings.model_dump(), observed_bar_count=self.count,
                    sha256=file_hash(staging / "market_benchmark.json"), equity_sha256=equity_hash)


def load_comparison(folder, descriptor):
    path = folder / "market_benchmark.json"
    if file_hash(path) != descriptor["sha256"]:
        raise ValueError("Saved market comparison integrity check failed.")
    result = json.loads(path.read_text(encoding="utf-8"))
    if result["version"] != descriptor["version"] or result["settings"] != descriptor["settings"]:
        raise ValueError("Saved market comparison specification changed.")
    return result


def comparison_preview(folder, descriptor, limit):
    """Stream full data, retaining endpoints and each series' bucket extremes."""
    path = folder / "market_equity.csv"
    if file_hash(path) != descriptor["equity_sha256"]:
        raise ValueError("Saved comparison equity integrity check failed.")
    total = descriptor["observed_bar_count"] + 1
    buckets = max(1, (limit - 2) // 6)
    items, extremes = [], {}
    previous_bucket = None
    seen = 0

    def flush():
        items.extend(sorted({p["bar_number"]: p for p in extremes.values()}.values(), key=lambda p: p["bar_number"]))
        extremes.clear()

    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != FIELDS:
            raise ValueError("Unsupported market comparison equity schema.")
        for point in reader:
            if None in point or any(value is None for value in point.values()):
                raise ValueError("Incomplete market comparison equity.")
            point["bar_number"] = int(point["bar_number"])
            if point["bar_number"] != seen:
                raise ValueError("Non-contiguous comparison equity.")
            seen += 1
            if total <= limit or point["bar_number"] in (0, total - 1):
                if point["bar_number"] == total - 1:
                    flush()
                items.append(point)
                continue
            bucket = (point["bar_number"] - 1) * buckets // (total - 2)
            if bucket != previous_bucket:
                flush()
                previous_bucket = bucket
            for field in SERIES:
                for direction in ("min", "max"):
                    key = (field, direction)
                    if key not in extremes or (Decimal(point[field]) < Decimal(extremes[key][field]) if direction == "min" else Decimal(point[field]) > Decimal(extremes[key][field])):
                        extremes[key] = point
    if seen != total:
        raise ValueError("Saved comparison equity count differs from the report.")
    return dict(items=items, total=total, sampled=total > limit, limit=limit, method="bar_bucket_extremes_all_three_series")

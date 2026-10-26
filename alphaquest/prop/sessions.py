"""Prepare immutable, reconciled, disk-backed source sessions from a saved run.

No strategies or prop-account transitions are executed. All result iterators
are valid inside prepare_backtest()'s resource context, after full validation.
"""

from contextlib import contextmanager
import csv
from dataclasses import dataclass, field, fields
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
from typing import Literal
from zoneinfo import ZoneInfo

from ..backtest_runs import RunStore
from ..decimal_math import add, multiply, subtract
from ..execution import EquityPoint, Trade
from ..reporting import EQUITY_FIELDS, TRADE_FIELDS, generate_report, json_value
from ..strategy import ExecutionConfig
from ._report_reader import InputError, ReportReader, require
from .calendar import SessionCalendar, microseconds
from .rules import ResolvedSimulation, _canonical_json, _digest, _read_json
from .types import Value, _decimal, _hash, _integer, _url
from .instruments import ResolvedInstrumentProfile, require_supported_account


ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class InstrumentDeclaration(Value):
    """Explicit source-unit interpretation, never inferred from a ticker."""

    symbol: str
    currency: str
    tick_size: Decimal
    point_value: Decimal
    contract_limit_weight: Decimal
    contract_limit_source_url: str
    basis: str
    profile: ResolvedInstrumentProfile | None = field(default=None, metadata={"omit_none": True})

    @classmethod
    def from_dict(cls, payload):
        if type(payload) is dict and "profile" not in payload:
            payload = {**payload, "profile": None}
        return super(InstrumentDeclaration, cls).from_dict(payload)

    def __post_init__(self):
        super(InstrumentDeclaration, self).__post_init__()
        require(re.fullmatch(r"[A-Z]{3}", self.currency) is not None, "Invalid declared currency.")
        for name in ("tick_size", "point_value", "contract_limit_weight"):
            _decimal(name, getattr(self, name), positive=True)
        _url("contract_limit_source_url", self.contract_limit_source_url)
        if self.profile is not None:
            p = self.profile.profile
            require(all(getattr(self, name) == getattr(p, name) for name in (
                "symbol", "currency", "tick_size", "point_value", "contract_limit_weight", "contract_limit_source_url")),
                "Instrument declaration differs from its captured profile.")
            require(self.basis == p.basis, "Instrument interpretation differs from its captured profile.")


@dataclass(frozen=True, slots=True)
class ArtifactDigest(Value):
    name: str
    sha256: str
    byte_count: int

    def __post_init__(self):
        super(ArtifactDigest, self).__post_init__()
        _hash("artifact sha256", self.sha256)
        _integer("byte_count", self.byte_count, 0)


@dataclass(frozen=True, slots=True)
class SourceSnapshot(Value):
    run_id: str
    manifest_json: str
    calendar_json: str
    instrument: InstrumentDeclaration
    artifacts: tuple[ArtifactDigest, ...]
    source_contracts: int | None
    observed_bar_count: int
    trade_count: int
    total_net_pnl: Decimal
    limitations: tuple[str, ...] = (
        "Trade-close and bar-close samples do not establish intratrade compliance.",
        "Fixed source signals, constant quantity, and no overnight exposure only.",
    )

    def __post_init__(self):
        super(SourceSnapshot, self).__post_init__()
        _integer("observed_bar_count", self.observed_bar_count)
        _integer("trade_count", self.trade_count, 0)
        if self.source_contracts is not None:
            _integer("source_contracts", self.source_contracts)
        require((self.trade_count == 0) == (self.source_contracts is None), "Source quantity/trade count mismatch.")
        require(self.trade_count != 0 or self.total_net_pnl == 0, "No-trade source cannot have nonzero net P&L.")

    @property
    def sha256(self):
        return _digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class Session:
    trading_date: date
    status: Literal["covered", "closed"]
    open_utc: datetime
    close_utc: datetime
    reset_utc: datetime
    bar_count: int
    trade_count: int
    net_pnl: Decimal


@dataclass(frozen=True, slots=True)
class ScaledTrade:
    source: Trade
    contracts: int
    reference_gross_pnl: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    entry_commission: Decimal
    exit_commission: Decimal
    total_commissions: Decimal
    slippage_cost: Decimal


@dataclass(frozen=True, slots=True)
class Observation:
    """Cumulative P&L relative to this trade's baseline; do not sum bar marks.

    Commission fields describe expenses already embedded in the observed P&L.
    Flat marks between trades have zero relative change and no trade identity.
    """

    bar_number: int
    timestamp_utc: datetime
    trade_number: int | None
    source_contracts: int | None
    contracts: int
    position_contracts: int
    source_equity: Decimal
    source_realized_net_pnl: Decimal
    source_unrealized_pnl: Decimal
    source_equity_change: Decimal
    realized_net_pnl: Decimal
    unrealized_pnl: Decimal
    equity_change: Decimal
    entry_commission: Decimal
    exit_commission: Decimal


def scale_money(value, source_contracts, contracts):
    """Exact rational normalization; reject repeating Decimal output, never round."""
    _decimal("value", value)
    require(type(source_contracts) is int and source_contracts > 0 and type(contracts) is int and contracts > 0,
            "Scaling requires positive integer quantities.")
    ratio = Fraction(value) * contracts / source_contracts
    denominator = ratio.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    require(denominator == 1, "Scaling produces a repeating decimal; candidate unsupported.")
    places = max(twos, fives)
    coefficient = ratio.numerator * 2 ** (places - twos) * 5 ** (places - fives)
    digits = tuple(map(int, str(abs(coefficient))))
    return Decimal((int(coefficient < 0), digits, -places))


def _dump(value):
    return json.dumps(value, default=json_value, separators=(",", ":"), allow_nan=False)


def _record(kind, payload, *, csv_input=False):
    require(type(payload) is dict and payload.keys() == {f.name for f in fields(kind)}, f"Invalid {kind.__name__} fields.")
    values = dict(payload)
    for field in fields(kind):
        value = values[field.name]
        if field.type is Decimal:
            require(type(value) is str and len(value) <= 1024, f"{field.name} must be an exact decimal string.")
            require(re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value) is not None,
                    f"Invalid {field.name} decimal.")
            value = Decimal(value)
            require(value.is_finite(), f"Nonfinite {field.name}.")
        elif field.type is int:
            if csv_input:
                require(type(value) is str and re.fullmatch(r"0|[1-9][0-9]*", value) is not None, f"Invalid {field.name} integer.")
                value = int(value)
            require(type(value) is int, f"{field.name} must be an integer.")
        elif field.name.endswith("time_utc") or field.name in ("timestamp_utc", "exit_deadline_utc"):
            if csv_input and value == "":
                value = None
            if value is not None:
                require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is not None,
                        f"Invalid {field.name} UTC timestamp.")
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            require(type(value) is str and bool(value.strip()), f"Invalid {field.name}.")
        values[field.name] = value
    return kind(**values)


def _payload(record):
    return {field.name: getattr(record, field.name) for field in fields(record)}


def _exact_equal(actual, expected, *, decimal_text=True):
    """JSON numbers remain strict; decimal text may differ in insignificant zeros."""
    if type(actual) is dict and type(expected) is dict:
        return actual.keys() == expected.keys() and all(_exact_equal(actual[k], expected[k], decimal_text=decimal_text) for k in actual)
    if type(actual) is list and type(expected) is list:
        return len(actual) == len(expected) and all(_exact_equal(a, b, decimal_text=decimal_text) for a, b in zip(actual, expected))
    if decimal_text and type(actual) is str and type(expected) is str:
        try:
            a, b = Decimal(actual), Decimal(expected)
            if a.is_finite() and b.is_finite():
                return a == b
        except ArithmeticError:
            pass
    return type(actual) is type(expected) and actual == expected


def _copy_artifact(source, destination):
    digest, size = sha256(), 0
    require(source.is_file() and not source.is_symlink(), f"Missing or unsupported source artifact: {source.name}.")
    with source.open("rb") as original, destination.open("wb") as copy:
        for chunk in iter(lambda: original.read(65536), b""):
            copy.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return ArtifactDigest(source.name, digest.hexdigest(), size)


def _read_catalog(runs, run_id):
    require(type(run_id) is str and re.fullmatch(r"[0-9a-f]{32}", run_id) is not None, "Invalid completed run ID.")
    # Avoid RunStore.get()'s optional legacy enrichment: source reads do not write.
    with runs.connect() as conn:
        row = conn.execute("SELECT manifest FROM runs WHERE id=?", (run_id,)).fetchone()
    require(row is not None, "Completed source backtest not found.")
    require(len(row[0]) <= 1048576, "Source manifest exceeds supported size limit.")
    manifest = _read_json(row[0])
    require(type(manifest) is dict and manifest.get("id") == run_id
            and manifest.get("status") == "complete", "Source run is not complete.")
    return manifest


def _stage_report(path, conn):
    conn.executescript("""
        PRAGMA cache_size=-2048;
        CREATE TABLE trades (n INTEGER PRIMARY KEY, entry_bar INTEGER, exit_bar INTEGER,
                             baseline TEXT, session TEXT, payload TEXT NOT NULL);
        CREATE UNIQUE INDEX trade_exit ON trades(exit_bar);
        CREATE TABLE marks (n INTEGER PRIMARY KEY, session TEXT, trade INTEGER, payload TEXT NOT NULL);
        CREATE INDEX mark_session ON marks(session,n);
        CREATE INDEX trades_session ON trades(session,n);
    """)
    header, trade_count, bar_count = {}, 0, -1
    with path.open(encoding="utf-8") as source:
        for key, record in ReportReader(source).records():
            if key == "trades":
                trade = _record(Trade, record)
                trade_count += 1
                require(trade.trade_number == trade_count, "Source trade numbers are not contiguous.")
                conn.execute("INSERT INTO trades VALUES (?,?,?,?,?,?)",
                             (trade.trade_number, trade.entry_bar_number, trade.exit_bar_number, None, None, _dump(record)))
            elif key == "equity":
                mark = _record(EquityPoint, record)
                bar_count += 1
                require(mark.bar_number == bar_count, "Source equity bar numbers are not contiguous.")
                conn.execute("INSERT INTO marks VALUES (?,?,?,?)", (mark.bar_number, None, None, _dump(record)))
            else:
                header[key] = record
    require(bar_count > 0, "Source requires observed bars.")
    return header, trade_count, bar_count


def _events(conn):
    trades = iter(conn.execute("SELECT payload FROM trades ORDER BY n"))
    row = next(trades, None)
    pending = _record(Trade, json.loads(row[0])) if row else None
    for row in conn.execute("SELECT payload FROM marks ORDER BY n"):
        mark = _record(EquityPoint, json.loads(row[0]))
        if pending is not None:
            if pending.exit_bar_number == mark.bar_number:
                yield pending
                row = next(trades, None)
                pending = _record(Trade, json.loads(row[0])) if row else None
        yield mark
    require(pending is None, "Source trade exits after source equity ends.")


def _validate_csvs(directory, conn, config):
    for name, expected_fields in (("trades.csv", TRADE_FIELDS), ("equity.csv", EQUITY_FIELDS)):
        with (directory / name).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            require(reader.fieldnames == expected_fields, f"Unsupported {name} columns.")
            if name == "trades.csv":
                for row in conn.execute("SELECT payload FROM trades ORDER BY n"):
                    actual = next(reader, None)
                    require(actual is not None and _record(Trade, actual, csv_input=True) == _record(Trade, json.loads(row[0])),
                            "trades.csv does not match report trades.")
            else:
                first = next(reader, None)
                require(first is not None and set(first) == set(EQUITY_FIELDS) and first["trade_number"] == "0"
                        and first["exit_time_utc"] == "" and Decimal(first["net_pnl"]) == 0
                        and Decimal(first["equity"]) == config.initial_capital, "Invalid initial equity.csv row.")
                equity = config.initial_capital
                for row in conn.execute("SELECT payload FROM trades ORDER BY n"):
                    trade = _record(Trade, json.loads(row[0]))
                    equity = add(equity, trade.net_pnl)
                    actual = next(reader, None)
                    require(actual is not None and set(actual) == set(EQUITY_FIELDS)
                            and actual["trade_number"] == str(trade.trade_number)
                            and actual["exit_time_utc"] == json_value(trade.exit_time_utc)
                            and Decimal(actual["net_pnl"]) == trade.net_pnl and Decimal(actual["equity"]) == equity,
                            "equity.csv does not match completed trades.")
            require(next(reader, None) is None, f"Unexpected extra rows in {name}.")


def _execution(header):
    require(header.get("format_version") == 1 and type(header["format_version"]) is int
            and header.get("status") == "complete", "Unsupported or incomplete source report.")
    require(header.get("timestamp_convention") == "bar_close", "Unsupported source timestamp convention.")
    require(header.get("execution_assumption") in ("same_close_full_fill", "next_open_market_next_bar_bracket_stop_first"),
            "Unsupported source execution assumption.")
    raw = header["execution_settings"]
    require(type(raw) is dict and raw.keys() == {f.name for f in fields(ExecutionConfig)}, "Invalid saved execution settings.")
    require(type(raw["slippage_ticks"]) is int, "Source slippage must be an integer.")
    for name in raw.keys() - {"slippage_ticks"}:
        require(type(raw[name]) is str, "Source execution money must be decimal text.")
    return ExecutionConfig(**{k: v if k == "slippage_ticks" else Decimal(v) for k, v in raw.items()})


def _bind_source(header, config, instrument):
    metadata = header["run_metadata"]
    dataset, strategy = metadata["dataset"], metadata["strategy"]
    for value in (dataset["id"], strategy["id"], dataset["source_timezone"]):
        require(type(value) is str and bool(value), "Missing source identity.")
    _hash("dataset hash", dataset["sha256"])
    _hash("strategy source hash", strategy["source_sha256"])
    require(type(strategy["parameters"]) is dict, "Missing source strategy parameters.")
    ZoneInfo(dataset["source_timezone"])
    require(instrument.symbol == config.instrument and instrument.currency == config.currency
            and instrument.contract_limit_weight == config.contract_limit_weight
            and instrument.contract_limit_source_url == config.contract_limit_source_url,
            "Instrument declaration does not match simulation settings.")
    require((instrument.profile.profile_sha256 if instrument.profile else None) == config.instrument_profile_sha256,
            "Instrument profile identity does not match simulation settings.")
    saved_symbol = dataset.get("symbol")
    require(not saved_symbol or saved_symbol == instrument.symbol, "Declared instrument conflicts with saved symbol.")
    saved_currency = dataset.get("currency")
    require(not saved_currency or saved_currency == instrument.currency, "Declared currency conflicts with saved currency.")
    execution = _execution(header)
    require(execution.tick_size == instrument.tick_size and execution.point_value == instrument.point_value,
            "Declared tick size/point value does not match actual source execution settings.")
    return execution


def _validate_trade_money(conn, execution):
    """Reconcile recorded prices/cost components, without calculating new fills."""
    for row in conn.execute("SELECT payload FROM trades"):
        trade = _record(Trade, json.loads(row[0]))
        commission = multiply(Decimal(trade.contracts), execution.commission_per_contract_per_side)
        require(trade.entry_commission == trade.exit_commission == commission,
                "Recorded trade commission differs from captured execution settings.")
        signed_value = multiply(Decimal(trade.contracts if trade.side == "long" else -trade.contracts), execution.point_value)
        require(trade.gross_pnl == multiply(subtract(trade.exit_fill_price, trade.entry_fill_price), signed_value)
                and trade.reference_gross_pnl == multiply(subtract(trade.exit_reference_price, trade.entry_reference_price), signed_value),
                "Recorded trade P&L does not reconcile with its preserved prices and point value.")
        require(trade.slippage_cost == subtract(trade.reference_gross_pnl, trade.gross_pnl),
                "Informational slippage does not reconcile with recorded gross P&L.")


def _partition(conn, header, calendar):
    days = {day.trading_date: day for day in calendar.days}
    bounds = {day.trading_date: calendar.bounds(day) for day in calendar.days}
    require(all(day.status != "missing" for day in calendar.days), "Calendar contains missing/unknown coverage.")
    counts = {(day.trading_date, i): 0 for day in calendar.days for i in range(len(day.windows))}
    summaries = {day.trading_date: [0, 0, ZERO] for day in calendar.days}
    zone = ZoneInfo(calendar.policy.timezone)

    def locate(stamp, *, containing_bar=False):
        local = stamp.astimezone(zone)
        label = local.date() + timedelta(days=1) if local.time() >= calendar.policy.open_time else local.date()
        day = days.get(label)
        require(day is not None and day.status == "covered", "Observation falls outside declared covered sessions.")
        opened, closed, _ = bounds[label]
        require(opened <= stamp <= closed, "Observation falls in maintenance break or outside prop session.")
        for i, window in enumerate(day.windows):
            if window.first_utc <= stamp <= window.last_utc:
                step = window.bar_interval_seconds * 1000000
                require(microseconds(stamp - window.first_utc) % step == 0, "Observation violates declared bar cadence.")
                if containing_bar:
                    require(stamp - timedelta(seconds=window.bar_interval_seconds) >= opened,
                            "Ambiguous containing-bar fill crosses prop-session open.")
                return label, i
        raise InputError("Observation falls outside declared strategy data windows.")

    source_quantity, total = None, ZERO
    for row in conn.execute("SELECT n,payload FROM trades ORDER BY n"):
        trade = _record(Trade, json.loads(row[1]))
        if source_quantity is None:
            source_quantity = trade.contracts
        require(trade.contracts == source_quantity, "Variable source quantities are unsupported; no sizing policy is divided out.")
        containing = header["execution_assumption"] != "same_close_full_fill"
        entry, _ = locate(trade.entry_time_utc, containing_bar=containing)
        exited, _ = locate(trade.exit_time_utc, containing_bar=containing)
        require(entry == exited, "Exposure spans prop-session boundaries/overnight; unsupported.")
        baseline = add(Decimal(header["summary"]["initial_capital"]), total)
        conn.execute("UPDATE trades SET session=?,baseline=? WHERE n=?", (entry.isoformat(), str(baseline), row[0]))
        total = add(total, trade.net_pnl)
        summaries[entry][1] += 1
        summaries[entry][2] = add(summaries[entry][2], trade.net_pnl)

    trades = iter(conn.execute("SELECT n,baseline,payload FROM trades ORDER BY n"))
    pending = next(trades, None)
    trade = _record(Trade, json.loads(pending[2])) if pending else None
    realized = ZERO
    first = last = None
    initial = Decimal(header["summary"]["initial_capital"])
    for n, payload in conn.execute("SELECT n,payload FROM marks WHERE n>0 ORDER BY n"):
        mark = _record(EquityPoint, json.loads(payload))
        label, window_id = locate(mark.timestamp_utc)
        first = first or mark.timestamp_utc
        last = mark.timestamp_utc
        counts[label, window_id] += 1
        summaries[label][0] += 1
        active = trade is not None and trade.entry_bar_number <= n <= trade.exit_bar_number
        expected_position = trade.contracts if active and n < trade.exit_bar_number else 0
        require(mark.position_contracts == expected_position, "Source exposure is not backed by completed trades.")
        if active:
            require(trade.entry_time_utc == mark.timestamp_utc if n == trade.entry_bar_number else True,
                    "Source entry timestamp does not match its bar.")
            if n == trade.exit_bar_number:
                realized = add(realized, trade.net_pnl)
                expected_cash = add(initial, realized)
            else:
                expected_cash = subtract(add(initial, realized), trade.entry_commission)
            trade_id = trade.trade_number
        else:
            expected_cash, trade_id = add(initial, realized), None
        require(mark.cash_balance == expected_cash, "Source cash/entry costs do not reconcile with accepted trade history.")
        conn.execute("UPDATE marks SET session=?,trade=? WHERE n=?", (label.isoformat(), trade_id, n))
        if active and n == trade.exit_bar_number:
            pending = next(trades, None)
            trade = _record(Trade, json.loads(pending[2])) if pending else None
    for day in calendar.days:
        for i, window in enumerate(day.windows):
            require(counts[day.trading_date, i] == window.bar_count,
                    f"Missing source coverage on {day.trading_date}; not a zero-trade session.")
    selection = header["run_metadata"].get("selection")
    require(type(selection) is dict, "Selected source-period metadata is required.")
    require(selection["start_utc"] == json_value(first) and selection["end_utc"] == json_value(last),
            "Selected source period does not match observed equity.")
    require(selection["source_timezone"] == header["run_metadata"]["dataset"]["source_timezone"],
            "Selected source timezone differs from saved dataset interpretation.")
    require(selection["row_count"] == sum(value[0] for value in summaries.values())
            and type(selection["row_count"]) is int, "Selected source bar count does not reconcile.")
    require(header["period_start_utc"] == json_value(first) and header["period_end_utc"] == json_value(last),
            "Report period differs from the observed source period.")
    start_row, end_row = selection["first_source_bar_number"], selection["last_source_bar_number"]
    require(type(start_row) is type(end_row) is int and 1 <= start_row <= end_row
            and end_row - start_row + 1 == selection["row_count"]
            and end_row <= header["run_metadata"]["dataset"]["row_count"], "Invalid original selected source-row bounds.")
    return source_quantity, total, summaries


class PreparedBacktest:
    """Validated source view. Iterators are reusable while the context is open."""

    def __init__(self, conn, snapshot, calendar, summaries, config):
        self._conn, self.snapshot, self.calendar = conn, snapshot, calendar
        self._summaries, self.config, self._closed = summaries, config, False

    def _check(self):
        require(not self._closed, "Prepared source context has closed.")

    def _quantity(self, quantity):
        q = self.config.quantity if quantity is None else quantity
        require(type(q) is int and q > 0, "Quantity must be a positive integer.")
        allowed = {self.config.quantity, *(self.config.sizing.quantities if self.config.sizing else ())}
        require(q in allowed, "Quantity was not included in the validated simulation settings/grid.")
        return q

    def sessions(self, *, quantity=None):
        self._check()
        q = self._quantity(quantity)
        for day in self.calendar.days:
            self._check()
            bars, trades, net = self._summaries[day.trading_date]
            scaled = scale_money(net, self.snapshot.source_contracts, q) if self.snapshot.source_contracts else ZERO
            yield Session(day.trading_date, day.status, *self.calendar.bounds(day), bars, trades, scaled)

    def trades(self, trading_date=None, *, quantity=None):
        self._check()
        q = self._quantity(quantity)
        query, args = "SELECT payload FROM trades", ()
        if trading_date is not None:
            require(type(trading_date) is date and trading_date in self._summaries, "Unknown trading_date in source calendar.")
            query += " WHERE session=?"
            args = (trading_date.isoformat(),)
        for row in self._conn.execute(query + " ORDER BY n", args):
            self._check()
            trade = _record(Trade, json.loads(row[0]))
            names = ("reference_gross_pnl", "gross_pnl", "net_pnl", "entry_commission", "exit_commission", "total_commissions", "slippage_cost")
            yield ScaledTrade(trade, q, **{name: scale_money(getattr(trade, name), trade.contracts, q) for name in names})

    def observations(self, trading_date, *, mode=None, quantity=None):
        self._check()
        require(type(trading_date) is date and trading_date in self._summaries, "Unknown trading_date in source calendar.")
        mode = self.config.observation_mode if mode is None else mode
        require(mode in ("trade_close", "bar_close"), "Only trade_close and bar_close observations are supported.")
        q = self._quantity(quantity)
        query = """SELECT m.payload,t.payload,t.baseline FROM marks m
                   LEFT JOIN trades t ON t.n=m.trade WHERE m.session=?"""
        if mode == "trade_close":
            query += " AND m.n=t.exit_bar"
        for mark_payload, trade_payload, baseline in self._conn.execute(query + " ORDER BY m.n", (trading_date.isoformat(),)):
            self._check()
            mark = _record(EquityPoint, json.loads(mark_payload))
            trade = _record(Trade, json.loads(trade_payload)) if trade_payload else None
            if trade:
                relative = subtract(mark.equity, Decimal(baseline))
                realized = subtract(mark.cash_balance, Decimal(baseline))
                size = trade.contracts
                scaling = lambda value: scale_money(value, size, q)
                entry_fee = trade.entry_commission if mode == "trade_close" or mark.bar_number == trade.entry_bar_number else ZERO
                exit_fee = trade.exit_commission if mark.bar_number == trade.exit_bar_number else ZERO
            else:
                relative = realized = ZERO
                scaling = lambda value: value
                entry_fee = exit_fee = ZERO
            yield Observation(mark.bar_number, mark.timestamp_utc, trade.trade_number if trade else None,
                              trade.contracts if trade else None, q if trade else 0,
                              q if mark.position_contracts else 0, mark.equity,
                              realized, mark.unrealized_pnl, relative,
                              scaling(realized), scaling(mark.unrealized_pnl), scaling(relative),
                              scaling(entry_fee), scaling(exit_fee))


@contextmanager
def prepare_backtest(runs: RunStore, resolved: ResolvedSimulation, calendar: SessionCalendar,
                     instrument: InstrumentDeclaration, *, temporary_parent: Path | None = None):
    """Snapshot and exhaustively validate before yielding any usable source.

    No source files or catalog rows are modified. All temporary copies and the
    disk index are removed on failure, early consumer exit, and normal close.
    """
    require(type(resolved) is ResolvedSimulation and type(calendar) is SessionCalendar
            and type(instrument) is InstrumentDeclaration, "Explicit resolved settings, calendar and instrument declaration required.")
    config = resolved.config
    if instrument.profile is not None:
        try:
            require_supported_account(instrument.profile.profile, resolved.rules.profile)
        except ValueError as exc:
            raise InputError(str(exc)) from None
    require(calendar.policy == resolved.rules.profile.session and calendar.id == config.calendar_id
            and calendar.sha256 == config.calendar_sha256 and calendar.mode == config.calendar_mode
            and calendar.timezone_data_version == config.timezone_data_version
            and calendar.coverage_assumption == config.coverage_assumption, "Calendar does not match resolved settings/profile.")
    with TemporaryDirectory(prefix="alphaquest-prop-input-", dir=temporary_parent) as temporary:
        directory = Path(temporary)
        conn, prepared = None, None
        try:
            catalog = _read_catalog(runs, config.source_backtest_id)
            artifacts = tuple(_copy_artifact(runs.root / config.source_backtest_id / name, directory / name)
                              for name in ("report.json", "trades.csv", "equity.csv"))
            conn = sqlite3.connect(directory / "source.sqlite3")
            header, trades, bars = _stage_report(directory / "report.json", conn)
            for key, value in header.items():
                if key == "summary":
                    # RunStore can enrich old drawdown summaries, never source financial totals.
                    require(all(k in catalog[key] and _exact_equal(v, catalog[key][k]) for k, v in value.items()),
                            "Source report summary differs from completed catalog.")
                else:
                    require(key in catalog and _exact_equal(value, catalog[key], decimal_text=False),
                            "Source report metadata differs from completed catalog.")
            execution = _bind_source(header, config, instrument)
            _validate_trade_money(conn, execution)
            _validate_csvs(directory, conn, execution)
            manifest = generate_report(_events(conn), directory / "validated", execution, expected_bar_count=bars,
                                       execution_assumption=header["execution_assumption"])
            checked = json.loads(_dump(manifest))
            require(_exact_equal(header["summary"], checked["summary"]), "Source summary does not reconcile with its full observations.")
            require(header["reconciliation"]["observed_bar_count"] == bars
                    and type(header["reconciliation"]["observed_bar_count"]) is int, "Source bar count mismatch.")
            source_q, total, summaries = _partition(conn, header, calendar)
            require(trades == header["summary"]["trades_taken"], "Trade count mismatch.")
            # Validate every requested scale before publishing a usable source view.
            quantities = {config.quantity, *(config.sizing.quantities if config.sizing else ())}
            if source_q:
                for q in quantities:
                    for row in conn.execute("SELECT payload FROM trades"):
                        trade = _record(Trade, json.loads(row[0]))
                        for name in ("reference_gross_pnl", "gross_pnl", "net_pnl", "entry_commission", "exit_commission", "total_commissions", "slippage_cost"):
                            scale_money(getattr(trade, name), source_q, q)
                    for row in conn.execute("SELECT m.payload,t.baseline FROM marks m JOIN trades t ON t.n=m.trade"):
                        mark = _record(EquityPoint, json.loads(row[0]))
                        for value in (subtract(mark.equity, Decimal(row[1])), subtract(mark.cash_balance, Decimal(row[1])), mark.unrealized_pnl):
                            scale_money(value, source_q, q)
            conn.commit()
            snapshot = SourceSnapshot(config.source_backtest_id, _canonical_json(catalog), calendar.to_json(), instrument,
                                      artifacts, source_q, bars, trades, total)
            prepared = PreparedBacktest(conn, snapshot, calendar, summaries, config)
            yield prepared
        except InputError:
            raise
        except (ValueError, TypeError, KeyError, OSError, ArithmeticError, sqlite3.Error, csv.Error, RecursionError) as exc:
            if prepared is not None:
                # The context body belongs to the caller (e.g. a future account
                # engine). Preserve its exceptions instead of blaming the input.
                raise
            raise InputError(f"Cannot adapt completed backtest: {exc}") from exc
        finally:
            if prepared:
                prepared._closed = True
            if conn:
                conn.close()

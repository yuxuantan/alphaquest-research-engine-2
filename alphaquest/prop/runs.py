"""Durable prop setups and input checks. Account simulation is not implemented.

Setups and checks are immutable records. Saving changed settings creates a new
setup ID; a check always consumes the captured profile, never today's template.
"""

from contextlib import contextmanager
import csv
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import json
import platform
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from ..decimal_math import add
from ..reporting import json_value
from .calendar import SessionCalendar
from .rules import ResolvedSimulation
from .sessions import InputError, InstrumentDeclaration, prepare_backtest
from .engine import ENGINE_VERSION, ReplaySession, SimulationError, replay_evaluation
from ..strategy import ExecutionConfig


def dump(value):
    return json.dumps(value, default=json_value, allow_nan=False, separators=(",", ":"))


def write_json(path, value):
    path.write_text(dump(value) + "\n", encoding="utf-8")


def catalog_record(runs, run_id):
    with runs.connect() as conn:
        row = conn.execute("SELECT manifest FROM runs WHERE id=?", (UUID(run_id).hex,)).fetchone()
    if row and len(row[0]) > 1048576:
        raise ValueError("Source manifest exceeds the supported metadata size limit.")
    return json.loads(row[0]) if row else None


class PropRunStore:
    def __init__(self, directory):
        self.root = Path(directory) / "prop_runs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = Path(directory) / "prop_simulations.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS prop_setups (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prop_checks (
                    id TEXT PRIMARY KEY, setup_id TEXT NOT NULL REFERENCES prop_setups(id),
                    created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS prop_setup_source ON prop_setups(source_id, created_at);
                CREATE INDEX IF NOT EXISTS prop_check_setup ON prop_checks(setup_id, created_at);
                CREATE TABLE IF NOT EXISTS prop_results (
                    id TEXT PRIMARY KEY, setup_id TEXT NOT NULL REFERENCES prop_setups(id),
                    created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS prop_result_setup ON prop_results(setup_id, created_at);
                CREATE TABLE IF NOT EXISTS prop_profile_fees (
                    profile_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get_profile_fees(self, profile_id):
        from .types import ProfileFees
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM prop_profile_fees WHERE profile_id=?", (profile_id,)).fetchone()
        return ProfileFees.from_dict(json.loads(row[0])) if row else None

    def save_profile_fees(self, profile_id, fees):
        from .types import ProfileFees
        if type(fees) is not ProfileFees:
            raise ValueError("Profile fees must be a ProfileFees value.")
        with self.connect() as conn:
            conn.execute("INSERT INTO prop_profile_fees VALUES (?,?) ON CONFLICT(profile_id) DO UPDATE SET payload=excluded.payload",
                         (profile_id, dump(fees.to_dict())))

    def _publish(self, path, table, record, parent_id):
        import shutil
        destination = self.root / record["id"]
        published = False
        try:
            with self.connect() as conn:
                conn.execute(f"INSERT INTO {table} VALUES (?, ?, ?, ?)",
                             (record["id"], parent_id, record["created_at_utc"], dump(record)))
                path.rename(destination)
                published = True
        except BaseException:
            if published:
                shutil.rmtree(destination)
            raise

    def save_setup(self, resolved, calendar, instrument, declaration):
        record = dict(id=uuid4().hex, kind="setup", status="draft", format_version=1,
                      source_backtest_id=resolved.config.source_backtest_id,
                      created_at_utc=json_value(datetime.now(timezone.utc)),
                      resolved=resolved.to_dict(), calendar=calendar.snapshot_dict(),
                      instrument=instrument.to_dict(), declaration=declaration)
        with TemporaryDirectory(prefix=".setup-", dir=self.root) as temp:
            path = Path(temp) / "output"
            path.mkdir()
            write_json(path / "setup.json", record)
            write_json(path / "profile.json", resolved.rules.to_dict())
            write_json(path / "simulation.json", resolved.to_dict())
            (path / "calendar.json").write_text(calendar.to_json() + "\n", encoding="utf-8")
            self._publish(path, "prop_setups", record, resolved.config.source_backtest_id)
        return record

    def get_setup(self, setup_id):
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM prop_setups WHERE id=?", (UUID(setup_id).hex,)).fetchone()
            check = conn.execute("SELECT payload FROM prop_checks WHERE setup_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
                                 (UUID(setup_id).hex,)).fetchone()
        if row is None:
            return None
        record = json.loads(row[0])
        # Reload independently of mutable templates. Recheck saved hashes.
        resolved = ResolvedSimulation.from_dict(record["resolved"])
        calendar = SessionCalendar.from_json(dump(record["calendar"]))
        instrument = InstrumentDeclaration.from_dict(record["instrument"])
        if calendar.sha256 != resolved.config.calendar_sha256 or calendar.policy != resolved.rules.profile.session:
            raise ValueError("Saved calendar does not match the resolved setup.")
        if (instrument.symbol, instrument.currency, instrument.contract_limit_weight, instrument.contract_limit_source_url) != (
                resolved.config.instrument, resolved.config.currency, resolved.config.contract_limit_weight, resolved.config.contract_limit_source_url):
            raise ValueError("Saved instrument declaration does not match the resolved setup.")
        return {**record, "latest_check": json.loads(check[0]) if check else None}

    def list_setups(self, source_id, offset=0, limit=25):
        with self.connect() as conn:
            count = conn.execute("SELECT count(*) FROM prop_setups WHERE source_id=?", (source_id,)).fetchone()[0]
            rows = conn.execute("SELECT id,created_at,payload FROM prop_setups WHERE source_id=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                                (source_id, limit, offset)).fetchall()
        items = []
        for setup_id, created_at, payload in rows:
            record = json.loads(payload)
            config = record["resolved"]["config"]
            items.append(dict(id=setup_id, created_at_utc=created_at, phase=config["phase"], quantity=config["quantity"],
                              platform=record["resolved"]["rules"]["profile"]["platform"],
                              profile_id=record["resolved"]["rules"]["profile"]["id"]))
        return dict(items=items, total=count, offset=offset, limit=limit)

    def check_source(self, setup_id, runs):
        setup = self.get_setup(setup_id)
        if setup is None:
            raise KeyError("Saved setup not found.")
        resolved = ResolvedSimulation.from_dict(setup["resolved"])
        calendar = SessionCalendar.from_json(dump(setup["calendar"]))
        instrument = InstrumentDeclaration.from_dict(setup["instrument"])
        record = dict(id=uuid4().hex, kind="input_check", setup_id=setup["id"],
                      created_at_utc=json_value(datetime.now(timezone.utc)), status="compatible", error=None,
                      settings_sha256=resolved.settings_sha256)
        with TemporaryDirectory(prefix=".check-", dir=self.root) as temp:
            path = Path(temp) / "output"
            path.mkdir()
            try:
                with prepare_backtest(runs, resolved, calendar, instrument) as source:
                    write_json(path / "source.json", source.snapshot.to_dict())
                    index = sqlite3.connect(path / "preview.sqlite3")
                    try:
                        index.execute("CREATE TABLE sessions (ordinal INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
                        index.execute("CREATE TABLE observations (ordinal INTEGER PRIMARY KEY, mode TEXT NOT NULL, trading_date TEXT NOT NULL, payload TEXT NOT NULL)")
                        totals = {name: Decimal(0) for name in ("gross_pnl", "total_commissions", "slippage_cost", "net_pnl")}
                        for trade in source.trades():
                            for name in totals:
                                totals[name] = add(totals[name], getattr(trade, name))
                        session_count = observation_count = zero_count = 0
                        with (path / "sessions.csv").open("w", encoding="utf-8", newline="") as session_file, (path / "observations.csv").open("w", encoding="utf-8", newline="") as mark_file:
                            session_writer = mark_writer = None
                            for session in source.sessions():
                                data = asdict(session)
                                data["trading_date"] = session.trading_date.isoformat()
                                if session_writer is None:
                                    session_writer = csv.DictWriter(session_file, fieldnames=data.keys())
                                    session_writer.writeheader()
                                session_writer.writerow({key: json_value(value) if isinstance(value, datetime) else value for key, value in data.items()})
                                index.execute("INSERT INTO sessions VALUES (?,?)", (session_count, dump(data)))
                                session_count += 1
                                zero_count += session.status == "covered" and session.trade_count == 0
                                for mode in ("trade_close", "bar_close"):
                                    for mark in source.observations(session.trading_date, mode=mode):
                                        data = dict(mode=mode, trading_date=session.trading_date.isoformat(), **asdict(mark))
                                        if mark_writer is None:
                                            mark_writer = csv.DictWriter(mark_file, fieldnames=data.keys())
                                            mark_writer.writeheader()
                                        mark_writer.writerow({key: json_value(value) if isinstance(value, datetime) else value for key, value in data.items()})
                                        index.execute("INSERT INTO observations VALUES (?,?,?,?)", (observation_count, mode, data["trading_date"], dump(data)))
                                        observation_count += 1
                        index.commit()
                        record.update(summary=dict(source_contracts=source.snapshot.source_contracts,
                                                   quantity=resolved.config.quantity, source_net_pnl=source.snapshot.total_net_pnl,
                                                   source_bar_count=source.snapshot.observed_bar_count, source_trade_count=source.snapshot.trade_count,
                                                   session_count=session_count, zero_trade_sessions=zero_count, **totals),
                                      source_sha256=source.snapshot.sha256,
                                      limitations=list(source.snapshot.limitations))
                    finally:
                        index.close()
            except InputError as exc:
                # Rejected checks are saved evidence, never successful account outcomes.
                import shutil
                shutil.rmtree(path)
                path.mkdir()
                record.update(status="rejected", error=str(exc))
            record = json.loads(dump(record))
            write_json(path / "check.json", record)
            self._publish(path, "prop_checks", record, setup["id"])
        return record

    def get_check(self, check_id):
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM prop_checks WHERE id=?", (UUID(check_id).hex,)).fetchone()
        return json.loads(row[0]) if row else None

    def execute(self, setup_id, runs):
        setup = self.get_setup(setup_id)
        if setup is None:
            raise KeyError("Saved setup not found.")
        resolved = ResolvedSimulation.from_dict(setup["resolved"])
        if resolved.config.phase != "evaluation" or resolved.config.analysis != "historical":
            raise SimulationError("Only historical evaluation execution is implemented; funded execution remains unavailable.")
        checked = setup["latest_check"]
        if not checked or checked["status"] != "compatible":
            raise SimulationError("Check source data successfully before running this setup.")
        calendar = SessionCalendar.from_json(dump(setup["calendar"]))
        instrument = InstrumentDeclaration.from_dict(setup["instrument"])
        record = dict(id=uuid4().hex, kind="simulation", status="complete", format_version=1,
                      setup_id=setup["id"], source_backtest_id=setup["source_backtest_id"],
                      created_at_utc=json_value(datetime.now(timezone.utc)), phase="evaluation", analysis="historical",
                      engine_version=ENGINE_VERSION, python_version=platform.python_version(),
                      resolved=setup["resolved"], calendar=setup["calendar"], instrument=setup["instrument"],
                      observation_mode=resolved.config.observation_mode, currency=resolved.config.currency,
                      assumptions=resolved.rules.profile.assumptions.to_dict(),
                      limitations=["Sampled observations do not establish tick-level compliance.",
                                   "Frozen source signals; no strategy rerun after account suspension or liquidation.",
                                   "Historical start is the first session open; end is a declared session reset.",
                                   "No funded execution, receipts, or Monte Carlo in this result."],
                      source_check_id=checked["id"])
        with TemporaryDirectory(prefix=".simulation-", dir=self.root) as temporary:
            path = Path(temporary) / "output"
            path.mkdir()
            with prepare_backtest(runs, resolved, calendar, instrument) as source:
                if source.snapshot.sha256 != checked["source_sha256"]:
                    raise SimulationError("Source identity changed since its compatibility check. Check source data again before running.")
                record["source_snapshot"] = source.snapshot.to_dict()
                record["source_sha256"] = source.snapshot.sha256
                write_json(path / "source.json", source.snapshot.to_dict())
                write_json(path / "simulation.json", resolved.to_dict())
                write_json(path / "profile.json", resolved.rules.to_dict())
                (path / "calendar.json").write_text(calendar.to_json() + "\n", encoding="utf-8")
                raw_settings = json.loads(source.snapshot.manifest_json)["execution_settings"]
                execution = ExecutionConfig(**{key: value if key == "slippage_ticks" else Decimal(value) for key, value in raw_settings.items()})
                index = sqlite3.connect(path / "events.sqlite3")
                try:
                    index.execute("PRAGMA cache_size=-2048")
                    index.execute("CREATE TABLE events (ordinal INTEGER PRIMARY KEY, observed INTEGER NOT NULL, payload TEXT NOT NULL)")
                    realized, external = Decimal(0), Decimal(0)
                    event_counts = {}
                    with (path / "events.csv").open("w", encoding="utf-8", newline="") as stream:
                        writer = None

                        def emit(event):
                            nonlocal writer, realized, external
                            realized = add(realized, event["realized_delta"])
                            external = add(external, event["external_cost"])
                            event_counts[event["kind"]] = event_counts.get(event["kind"], 0) + 1
                            if writer is None:
                                writer = csv.DictWriter(stream, fieldnames=event.keys())
                                writer.writeheader()
                            writer.writerow({key: json_value(value) if isinstance(value, datetime) else value for key, value in event.items()})
                            index.execute("INSERT INTO events VALUES (?,?,?)", (event["sequence"], int(event["is_equity_observation"]), dump(event)))

                        sessions = (ReplaySession(session, source.trades(session.trading_date), source.observations(session.trading_date))
                                    for session in source.sessions())
                        summary = replay_evaluation(resolved, calendar, execution, sessions, emit)
                    unprocessed = source.snapshot.trade_count - summary["processed_trades"] - summary["skipped_trades"]
                    if (add(summary["initial_balance"], realized) != summary["balance"] or external != summary["external_costs"]
                            or summary["balance"] != summary["equity"] or unprocessed < 0
                            or summary["completed_source_trades"] + summary["forced_exits"] != summary["processed_trades"]
                            or event_counts.get("entry_accepted", 0) != summary["processed_trades"]
                            or event_counts.get("trade_skipped", 0) != summary["skipped_trades"]
                            or event_counts.get("liquidated", 0) != summary["forced_exits"]
                            or sum(event_counts.values()) != summary["event_count"]):
                        raise SimulationError("Account event ledger failed reconciliation; no completed result published.")
                    summary.update(source_trade_count=source.snapshot.trade_count, unprocessed_trades=unprocessed)
                    record.update(summary=summary, reconciliation=dict(passed=True, realized_ledger_total=realized,
                                                                       external_cost_ledger_total=external,
                                                                       source_trade_count=source.snapshot.trade_count))
                    index.execute("CREATE INDEX observed_events ON events(observed,ordinal)")
                    index.commit()
                finally:
                    index.close()
            # The manifest identifies all downloadable financial artifacts. The
            # event index is an implementation detail; CSV/manifest are portable.
            record["artifacts"] = {}
            for filename in ("events.csv", "source.json", "simulation.json", "profile.json", "calendar.json"):
                digest, size = sha256(), 0
                with (path / filename).open("rb") as stream:
                    for chunk in iter(lambda: stream.read(65536), b""):
                        digest.update(chunk)
                        size += len(chunk)
                record["artifacts"][filename] = dict(sha256=digest.hexdigest(), byte_count=size)
            record = json.loads(dump(record))
            write_json(path / "report.json", record)
            self._publish(path, "prop_results", record, setup["id"])
        return record

    def get_result(self, result_id):
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM prop_results WHERE id=?", (UUID(result_id).hex,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_results(self, setup_id, offset=0, limit=25):
        with self.connect() as conn:
            count = conn.execute("SELECT count(*) FROM prop_results WHERE setup_id=?", (setup_id,)).fetchone()[0]
            rows = conn.execute("SELECT payload FROM prop_results WHERE setup_id=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                                (setup_id, limit, offset)).fetchall()
        items = [dict(id=value["id"], created_at_utc=value["created_at_utc"], summary=value["summary"])
                 for value in (json.loads(row[0]) for row in rows)]
        return dict(items=items, total=count, offset=offset, limit=limit)

    def events(self, result_id, offset, limit):
        result = self.get_result(result_id)
        if result is None:
            raise KeyError("Simulation result not found.")
        with sqlite3.connect(self.root / result["id"] / "events.sqlite3") as conn:
            rows = conn.execute("SELECT payload FROM events ORDER BY ordinal LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return dict(items=[json.loads(row[0]) for row in rows], total=result["summary"]["event_count"], offset=offset, limit=limit)

    def chart(self, result_id, max_points):
        """Bounded actual saved points: equity extrema and bucket endpoints."""
        result = self.get_result(result_id)
        if result is None:
            raise KeyError("Simulation result not found.")
        with sqlite3.connect(self.root / result["id"] / "events.sqlite3") as conn:
            total = conn.execute("SELECT count(*) FROM events WHERE observed=1").fetchone()[0]
            if total <= max_points:
                rows = conn.execute("SELECT payload FROM events WHERE observed=1 ORDER BY ordinal").fetchall()
                items = [json.loads(row[0]) for row in rows]
            else:
                buckets = max(1, (max_points - 2) // 3)
                size = (total + buckets - 1) // buckets
                selected, low, high, first, last = [], None, None, None, None
                for i, (payload,) in enumerate(conn.execute("SELECT payload FROM events WHERE observed=1 ORDER BY ordinal")):
                    point = json.loads(payload)
                    if first is None:
                        first = point
                    last = point
                    if low is None or Decimal(point["equity"]) < Decimal(low["equity"]):
                        low = point
                    if high is None or Decimal(point["equity"]) > Decimal(high["equity"]):
                        high = point
                    if (i + 1) % size == 0 or i == total - 1:
                        selected.extend((low, high, point))
                        low = high = None
                items = sorted({point["sequence"]: point for point in [first, *selected, last]}.values(), key=lambda x: x["sequence"])
        return dict(items=items, total=total, sampled=total > max_points)

    def page(self, check_id, kind, offset, limit, mode="bar_close", trading_date=None):
        if kind not in {"sessions", "observations"}:
            raise ValueError("Unknown preview kind.")
        record = self.get_check(check_id)
        if record is None:
            raise KeyError("Input check not found.")
        if record["status"] != "compatible":
            raise ValueError("This source check was rejected; no preview is available.")
        with sqlite3.connect(self.root / UUID(check_id).hex / "preview.sqlite3") as conn:
            if kind == "sessions":
                condition, values = "1=1", []
            else:
                condition, values = "mode=?", [mode]
                if trading_date:
                    condition += " AND trading_date=?"
                    values.append(trading_date)
            count = conn.execute(f"SELECT count(*) FROM {kind} WHERE {condition}", values).fetchone()[0]
            rows = conn.execute(f"SELECT payload FROM {kind} WHERE {condition} ORDER BY ordinal LIMIT ? OFFSET ?", [*values, limit, offset]).fetchall()
        return dict(items=[json.loads(row[0]) for row in rows], total=count, offset=offset, limit=limit)

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
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from ..decimal_math import add
from ..reporting import json_value
from .calendar import SessionCalendar
from .rules import ResolvedSimulation
from .sessions import InputError, InstrumentDeclaration, prepare_backtest


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
                              platform=record["resolved"]["rules"]["profile"]["platform"]))
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

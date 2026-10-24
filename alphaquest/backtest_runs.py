"""Durable completed runs and indexed pages, streamed from report CSVs."""

from contextlib import contextmanager
import csv
from dataclasses import fields
import json
from pathlib import Path
import shutil
import sqlite3

from .execution import Trade
from .drawdown import saved_drawdown
from .reporting import json_value


INTEGER_TRADE_FIELDS = {field.name for field in fields(Trade) if field.type is int}


class RunStore:
    def __init__(self, directory: Path):
        self.root = Path(directory) / "backtest_runs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = Path(directory) / "backtests.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, manifest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_trades (
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS run_equity (
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, ordinal)
                );
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _rows(self, source: Path, kind: str):
        with source.open(encoding="utf-8", newline="") as stream:
            for ordinal, row in enumerate(csv.DictReader(stream)):
                if kind == "trades":
                    for key in INTEGER_TRADE_FIELDS:
                        row[key] = int(row[key])
                    row["exit_deadline_utc"] = row["exit_deadline_utc"] or None
                else:
                    row["trade_number"] = int(row["trade_number"])
                    row["exit_time_utc"] = row["exit_time_utc"] or None
                yield ordinal, json.dumps(row, allow_nan=False)

    def complete(self, run_id: str, report_directory: Path, manifest: dict) -> dict:
        """Commit the catalogue only after all rows and artifacts are saved.

        A crash between the directory rename and SQLite commit may leave an
        unlisted directory, but never a retrievable successful run. Exceptions
        roll back all indexed rows and remove any published directory.
        """
        destination = self.root / run_id
        if destination.exists():
            raise FileExistsError(f"Run artifacts already exist: {run_id}")
        record = json.loads(json.dumps({"id": run_id, **manifest}, default=json_value, allow_nan=False))
        published = False
        try:
            with self.connect() as conn:
                conn.execute("INSERT INTO runs VALUES (?, ?, ?)", (run_id, record["created_at_utc"], json.dumps(record)))
                for kind, table in (("trades", "run_trades"), ("equity", "run_equity")):
                    conn.executemany(f"INSERT INTO {table} VALUES (?, ?, ?)", (
                        (run_id, ordinal, payload) for ordinal, payload in self._rows(report_directory / f"{kind}.csv", kind)
                    ))
                report_directory.rename(destination)
                published = True
        except BaseException:
            if published:
                shutil.rmtree(destination)
            raise
        return record

    def get(self, run_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT manifest FROM runs WHERE id=?", (run_id,)).fetchone()
        return self._with_drawdown(json.loads(row[0])) if row else None

    def _with_drawdown(self, record):
        """One-time catalogue enrichment; stream outside the DB connection."""
        if not {"max_drawdown_amount", "max_drawdown_pct", "max_drawdown_duration_seconds"} <= record["summary"].keys():
            record.update(saved_drawdown(self.root / record["id"], record))
            record = json.loads(json.dumps(record, default=json_value, allow_nan=False))
            with self.connect() as conn:
                conn.execute("UPDATE runs SET manifest=? WHERE id=?", (json.dumps(record), record["id"]))
        return record

    def list(self, offset: int, limit: int) -> dict:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            rows = conn.execute("SELECT manifest FROM runs ORDER BY created_at DESC, id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return {"items": [self._with_drawdown(json.loads(row[0])) for row in rows], "offset": offset, "limit": limit, "total": total}

    def page(self, run_id: str, kind: str, offset: int, limit: int) -> dict | None:
        record = self.get(run_id)
        if record is None:
            return None
        table = {"trades": "run_trades", "equity": "run_equity"}[kind]
        with self.connect() as conn:
            rows = conn.execute(f"SELECT payload FROM {table} WHERE run_id=? AND ordinal>=? ORDER BY ordinal LIMIT ?",
                                (run_id, offset, limit)).fetchall()
        total = record["summary"]["trades_taken"] + (1 if kind == "equity" else 0)
        return {"items": [json.loads(row[0]) for row in rows], "offset": offset, "limit": limit, "total": total}

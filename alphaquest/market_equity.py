"""Daily comparison storage with immutable, shared holding observations.

Daily means the last selected bar of each source-local calendar date. Financial
metrics are still accumulated from every bar by MarketBenchmark.
"""

import csv
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import io
from itertools import zip_longest
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo


FIELDS = ["bar_number", "timestamp_utc", "close", "strategy_equity", "holding_equity",
          "excess_net_pnl", "strategy_contracts", "holding_contracts"]
DAY_FIELDS = FIELDS + ["date"]
HOLDING_FIELDS = ["bar_number", "date", "timestamp_utc", "close", "holding_equity", "holding_contracts"]
STRATEGY_FIELDS = ["bar_number", "strategy_equity", "strategy_contracts"]
STORAGE_VERSION = "daily-shared-v1"
STRATEGY_FILE = "strategy_equity_day.csv"
HOLDING_FILE = "holding_equity_day.csv"


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class DailyEquityWriter:
    def __init__(self, folder, stack, timezone):
        self.date_for = SourceDate(timezone)
        self.pending = None
        self.days = 0
        self.writers = []
        for name, fields in ((STRATEGY_FILE, STRATEGY_FIELDS), (HOLDING_FILE, HOLDING_FIELDS)):
            stream = stack.enter_context((folder / name).open("w", encoding="utf-8", newline=""))
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            self.writers.append(writer)

    def observe(self, point):
        point = dict(point)
        point["date"] = self.date_for(point["timestamp_utc"])
        if int(point["bar_number"]) == 0:
            for writer in self.writers:
                writer.writerow(point)
            return
        if self.pending and self.pending["date"] != point["date"]:
            self.finish_day()
        self.pending = point

    def finish_day(self):
        if self.pending:
            for writer in self.writers:
                writer.writerow(self.pending)
            self.days += 1
            self.pending = None


class SourceDate:
    """Cache source-date UTC boundaries, including DST, for canonical UTC labels."""
    def __init__(self, zone):
        self.zone = ZoneInfo(zone)
        self.start = self.end = self.date = ''

    def __call__(self, timestamp):
        if not timestamp:
            return ''
        key = timestamp[:19]
        if not self.start <= key < self.end:
            local = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).astimezone(self.zone).date()
            start = datetime.combine(local, time.min, self.zone)
            end = datetime.combine(local + timedelta(days=1), time.min, self.zone)
            self.start = start.astimezone(timezone.utc).isoformat()[:19]
            self.end = end.astimezone(timezone.utc).isoformat()[:19]
            self.date = local.isoformat()
        return self.date


def legacy_daily_rows(folder, descriptor, zone):
    """Verify all legacy rows, materializing dictionaries only at daily closes."""
    path = folder / 'market_equity.csv'
    if file_hash(path) != descriptor['equity_sha256']:
        raise ValueError('Saved comparison equity integrity check failed.')
    date_for = SourceDate(zone)
    previous = None
    previous_date = None
    seen = 0
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.reader(stream)
        if next(reader, None) != FIELDS:
            raise ValueError('Unsupported market comparison equity schema.')
        for row in reader:
            if len(row) != len(FIELDS) or int(row[0]) != seen:
                raise ValueError('Incomplete or non-contiguous comparison equity.')
            date = date_for(row[1])
            if previous is not None and date != previous_date:
                yield dict(zip(FIELDS, previous))
            previous, previous_date = row, date
            seen += 1
        if seen != descriptor['observed_bar_count'] + 1:
            raise ValueError('Saved comparison equity count differs from the report.')
        if previous is not None:
            yield dict(zip(FIELDS, previous))


def daily_storage(folder, data, days):
    """Identity excludes strategy/run IDs, and includes every holding input."""
    source = data["source"]
    dataset = source["dataset"]
    identity = dict(version=data["version"], storage_version=STORAGE_VERSION,
                    settings=data["settings"],
                    dataset={k: dataset.get(k) for k in ("sha256", "source_timezone", "instrument_settings")},
                    instrument=source["instrument"], selection=source["selection"],
                    execution_settings=source["execution_settings"],
                    calculation_source_sha256=data["calculation_source_sha256"])
    key = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    return dict(version=STORAGE_VERSION, granularity="DAY", timezone=dataset["source_timezone"],
                day_boundary="last_selected_bar_of_source_calendar_date", observed_day_count=days,
                strategy_sha256=file_hash(folder / STRATEGY_FILE), holding_key=key,
                holding_sha256=file_hash(folder / HOLDING_FILE))


def holding_path(folder, descriptor):
    storage = descriptor["storage"]
    if storage["version"] != STORAGE_VERSION or storage["granularity"] != "DAY":
        raise ValueError("Unsupported saved comparison storage.")
    key = storage["holding_key"]
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
        raise ValueError("Invalid saved holding reference.")
    # Unpublished reports have a private staging file. Published reports resolve
    # against the data directory, never against another run's lifetime.
    local = folder / HOLDING_FILE
    return local if local.is_file() else folder.resolve().parent.parent / "market_benchmarks" / (key + ".csv")


def publish_holding(folder, data_directory, descriptor):
    if "storage" not in descriptor:
        return
    source = folder / HOLDING_FILE
    expected = descriptor["storage"]["holding_sha256"]
    # Validate reference syntax before using it as a filename.
    holding_path(folder, descriptor)
    if file_hash(source) != expected:
        raise ValueError("Staged daily holding integrity check failed.")
    root = Path(data_directory) / "market_benchmarks"
    root.mkdir(parents=True, exist_ok=True)
    target = root / (descriptor["storage"]["holding_key"] + ".csv")
    try:
        # Atomic publication works across concurrent optimizations/processes.
        # No run owns the shared link; deleting a run cannot remove it.
        os.link(source, target)
    except FileExistsError:
        if target.is_symlink() or file_hash(target) != expected:
            raise ValueError("Shared daily holding integrity check failed; existing data preserved.") from None
    source.unlink()


def equity_rows(folder, descriptor):
    """Verify saved artifacts and join daily series without source-data replay."""
    if "storage" not in descriptor:
        path = folder / "market_equity.csv"
        if file_hash(path) != descriptor["equity_sha256"]:
            raise ValueError("Saved comparison equity integrity check failed.")
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != FIELDS:
                raise ValueError("Unsupported market comparison equity schema.")
            for ordinal, point in enumerate(reader):
                if None in point or any(v is None for v in point.values()) or int(point["bar_number"]) != ordinal:
                    raise ValueError("Incomplete or non-contiguous comparison equity.")
                yield point
            if reader.line_num != descriptor["observed_bar_count"] + 2:
                raise ValueError("Saved comparison equity count differs from the report.")
        return
    storage = descriptor["storage"]
    holding = holding_path(folder, descriptor)
    strategy = folder / STRATEGY_FILE
    if file_hash(strategy) != storage["strategy_sha256"] or file_hash(holding) != storage["holding_sha256"]:
        raise ValueError("Saved daily comparison equity integrity check failed.")
    with strategy.open(encoding="utf-8", newline="") as a, holding.open(encoding="utf-8", newline="") as b:
        strategies, holdings = csv.DictReader(a), csv.DictReader(b)
        if strategies.fieldnames != STRATEGY_FIELDS or holdings.fieldnames != HOLDING_FIELDS:
            raise ValueError("Unsupported daily comparison schema.")
        previous = -1
        previous_date = ""
        count = 0
        for s, h in zip_longest(strategies, holdings):
            if s is None or h is None or None in s or None in h or any(v is None for v in [*s.values(), *h.values()]):
                raise ValueError("Daily comparison series do not align.")
            number = int(h["bar_number"])
            if s["bar_number"] != h["bar_number"] or number <= previous:
                raise ValueError("Daily comparison bars do not align.")
            if count == 0:
                if number != 0 or h["date"] or h["timestamp_utc"]:
                    raise ValueError("Missing daily comparison initial balance.")
            else:
                timestamp = datetime.fromisoformat(h["timestamp_utc"].replace("Z", "+00:00"))
                if h["date"] <= previous_date or timestamp.astimezone(ZoneInfo(storage["timezone"])).date().isoformat() != h["date"]:
                    raise ValueError("Daily comparison source dates do not align.")
            from .decimal_math import subtract
            point = {**h, **s, "excess_net_pnl": str(subtract(Decimal(s["strategy_equity"]), Decimal(h["holding_equity"])))}
            yield point
            previous, previous_date = number, h["date"]
            count += 1
        if count != storage["observed_day_count"] + 1 or previous != descriptor["observed_bar_count"]:
            raise ValueError("Saved daily comparison count differs from the report.")


def equity_csv(folder, descriptor):
    """Generate the ordinary aligned download; never persist duplicate holding data."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=DAY_FIELDS if "storage" in descriptor else FIELDS)
    writer.writeheader()
    for point in equity_rows(folder, descriptor):
        writer.writerow(point)
    return output.getvalue().encode("utf-8")

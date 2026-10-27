"""Read a saved dataset into completed bars, using a disk-backed snapshot."""

import argparse
import csv
import hashlib
import io
import json
import os
import re
from contextlib import contextmanager, ExitStack
from collections.abc import Generator, Iterator
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .datasets import COLUMNS, DatasetStore, InvalidDataset, invalid, parse_csv_row, validate_csv, validate_csv_header
from .strategy import Bar


class DatasetReadError(ValueError):
    """The selected saved dataset is missing or cannot be read consistently."""


class UnsupportedDatasetSchema(DatasetReadError):
    pass


@dataclass(frozen=True)
class DateRange:
    """Inclusive calendar dates in the dataset's saved source timezone."""

    from_date: date | None = None
    to_date: date | None = None

    def __post_init__(self):
        if any(value is not None and type(value) is not date for value in (self.from_date, self.to_date)):
            raise ValueError("Date bounds must be dates, without a time of day.")
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("From date must be on or before To date.")

    @classmethod
    def parse(cls, from_date=None, to_date=None):
        values = []
        for name, value in (("From date", from_date), ("To date", to_date)):
            if value is None:
                values.append(None)
                continue
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError(f"{name} must use YYYY-MM-DD, or be omitted.")
            try:
                values.append(date.fromisoformat(value))
            except ValueError:
                raise ValueError(f"{name} must be a valid calendar date.") from None
        return cls(*values)

    @property
    def active(self):
        return self.from_date is not None or self.to_date is not None

    def contains(self, timestamp, zone):
        local_date = timestamp.astimezone(zone).date()
        return ((self.from_date is None or local_date >= self.from_date)
                and (self.to_date is None or local_date <= self.to_date))


@dataclass(frozen=True)
class SelectedBars:
    bars: Iterator[Bar]
    metadata: dict

    @property
    def row_count(self):
        return self.metadata["row_count"]


def _iter_bars(text, zone: ZoneInfo, expected_rows: int) -> Generator[Bar, None, None]:
    reader = csv.reader(text, strict=True)
    previous = None
    count = 0
    try:
        validate_csv_header(next(reader, None))
        for count, row in enumerate(reader, 1):
            timestamp, numbers = parse_csv_row(row, zone, previous, reader.line_num)
            previous = timestamp
            yield Bar(
                bar_number=count, timestamp_utc=timestamp, date=row[0], time=row[1],
                open=numbers[0], high=numbers[1], low=numbers[2], close=numbers[3],
                volume=numbers[4], up_vol=numbers[5], down_vol=numbers[6], source_fields=tuple(row),
            )
    except UnicodeDecodeError:
        raise InvalidDataset([invalid("The CSV must be UTF-8 encoded.")]) from None
    except csv.Error as exc:
        raise InvalidDataset([invalid(f"Malformed CSV: {exc}", reader.line_num)]) from None
    if not count:
        raise InvalidDataset([invalid("Include at least one data row below the header.")])
    if count != expected_rows:
        raise DatasetReadError("The CSV row count does not match its saved metadata.")


@contextmanager
def read_bars(store: DatasetStore, dataset_id: str) -> Iterator[Iterator[Bar]]:
    """Snapshot by saved ID, release SQLite, then lazily parse bars.

    Use as `with read_bars(store, id) as bars:`. The iterator is valid only
    inside that context. No source CSV or metadata is updated. A partial
    consumer validates the rows it consumes; full iteration checks row count.
    """
    metadata = store.get(dataset_id)
    if metadata is None:
        raise DatasetReadError(f"Dataset {dataset_id!r} was not found.")
    if metadata.get("columns") != COLUMNS:
        raise UnsupportedDatasetSchema("Unsupported dataset schema. Backtest reading requires: " + ",".join(COLUMNS))
    source_timezone = metadata.get("source_timezone")
    if not isinstance(source_timezone, str) or not source_timezone:
        raise DatasetReadError("The dataset has no saved source timezone; it cannot be inferred.")
    try:
        zone = ZoneInfo(source_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise DatasetReadError(f"Invalid saved source timezone: {source_timezone!r}.") from None
    with ExitStack() as stack:
        open_snapshot = getattr(store, "open_snapshot", None)
        snapshot = stack.enter_context(open_snapshot(dataset_id) if open_snapshot else TemporaryFile(mode="w+b"))
        digest = hashlib.sha256()
        size = 0
        chunks = iter(lambda: snapshot.read(1024 * 1024), b"") if open_snapshot else store.iter_csv(dataset_id)
        for chunk in chunks:
            if not open_snapshot:
                snapshot.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        # iter_csv has fully exited its database context before any bar is yielded.
        if size != metadata.get("bytes") or digest.hexdigest() != metadata.get("sha256"):
            raise DatasetReadError("Saved CSV bytes do not match the dataset metadata; the dataset may be unavailable or incomplete.")
        snapshot.seek(0)
        with io.TextIOWrapper(snapshot, encoding="utf-8-sig", newline="") as text:
            bars = _iter_bars(text, zone, metadata.get("row_count"))
            try:
                yield bars
            finally:
                bars.close()


@contextmanager
def read_selected_bars(store: DatasetStore, dataset_id: str, date_range: DateRange | None = None):
    """Prepare an exact replay count without retaining selected bars in RAM.

    The original CSV is snapshotted and fully validated with the shared reader.
    A range spools matching source fields to a temporary CSV, then replays them
    with contiguous bar numbers starting at one. Source bytes and metadata stay
    untouched. No bars outside the range are supplied as strategy warm-up.
    """
    date_range = date_range or DateRange()
    dataset = store.get(dataset_id)
    if dataset is None:
        raise DatasetReadError(f"Dataset {dataset_id!r} was not found.")
    selection = {"from_date": date_range.from_date.isoformat() if date_range.from_date else None,
                 "to_date": date_range.to_date.isoformat() if date_range.to_date else None,
                 "source_timezone": dataset.get("source_timezone"), "warmup": "none"}
    with read_bars(store, dataset_id) as source:
        if not date_range.active:
            selection.update(row_count=dataset["row_count"], start_utc=dataset["start"], end_utc=dataset["end"],
                             first_source_bar_number=1, last_source_bar_number=dataset["row_count"])
            yield SelectedBars(source, selection)
            return
        zone = ZoneInfo(dataset["source_timezone"])
        with TemporaryFile(mode="w+", encoding="utf-8", newline="") as snapshot:
            writer = csv.writer(snapshot)
            writer.writerow(COLUMNS)
            count = 0
            for bar in source:
                if date_range.contains(bar.timestamp_utc, zone):
                    writer.writerow(bar.source_fields)
                    if not count:
                        selection.update(start_utc=bar.timestamp_utc.isoformat().replace("+00:00", "Z"),
                                         first_source_bar_number=bar.bar_number)
                    selection.update(end_utc=bar.timestamp_utc.isoformat().replace("+00:00", "Z"),
                                     last_source_bar_number=bar.bar_number)
                    count += 1
            if not count:
                raise DatasetReadError("No bars fall within the selected date range in the dataset's source timezone.")
            selection["row_count"] = count
            snapshot.seek(0)
            bars = _iter_bars(snapshot, zone, count)
            try:
                yield SelectedBars(bars, selection)
            finally:
                bars.close()


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _print_bars(store, dataset_id, limit):
    with read_bars(store, dataset_id) as bars:
        for bar in islice(bars, limit):
            print(json.dumps(asdict(bar), default=_json_value))


def main():
    parser = argparse.ArgumentParser(description="Print normalized bars from a saved dataset. No backtest is run.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset-id", help="Existing saved dataset ID")
    source.add_argument("--demo", action="store_true", help="Save/read the small gap_deadline fixture in an isolated temporary database")
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("ALPHAQUEST_DATA_DIR", "data")) / "datasets.sqlite3")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be >= 1")
    try:
        if args.demo:
            fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/backtest_contract/gap_deadline.csv"
            raw = fixture.read_bytes()
            with TemporaryDirectory(prefix="alphaquest-reader-demo-") as directory:
                store = DatasetStore(Path(directory) / "datasets.sqlite3")
                metadata = validate_csv(raw, fixture.name, "America/New_York")
                saved = store.save(raw, metadata, "Reader review fixture", "SYNTHETIC")
                _print_bars(store, saved["id"], args.limit)
        else:
            if not args.database.is_file():
                raise DatasetReadError(f"Dataset database does not exist: {args.database}")
            _print_bars(DatasetStore(args.database), args.dataset_id, args.limit)
    except (DatasetReadError, InvalidDataset, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

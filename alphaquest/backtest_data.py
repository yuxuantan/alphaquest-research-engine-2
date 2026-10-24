"""Read a saved dataset into completed bars, using a disk-backed snapshot."""

import argparse
import csv
import hashlib
import io
import json
import os
from contextlib import contextmanager
from collections.abc import Generator, Iterator
from dataclasses import asdict
from datetime import datetime
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
    with TemporaryFile(mode="w+b") as snapshot:
        digest = hashlib.sha256()
        size = 0
        for chunk in store.iter_csv(dataset_id):
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

"""Pair standard close-labelled NQ/MNQ and ES bar CSVs by exact UTC timestamp."""

import argparse
import csv
from itertools import zip_longest
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .datasets import COLUMNS, PAIRED_COLUMNS, parse_csv_row


def _bars(path, zone):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != COLUMNS:
            raise ValueError(f"{path.name} must use the standard OHLCV header: " + ",".join(COLUMNS))
        previous = None
        for row in reader:
            try:
                stamp, values = parse_csv_row(row, zone, previous, reader.line_num)
            except ValueError as exc:
                raise ValueError(f"{path.name} row {reader.line_num}: {exc}") from exc
            if values[3] <= 0:
                raise ValueError(f"{path.name} row {reader.line_num}: Close must be positive.")
            yield stamp, row
            previous = stamp


def pair(primary, es, output, primary_timezone, es_timezone=None):
    primary_zone = ZoneInfo(primary_timezone)
    es_zone = ZoneInfo(es_timezone or primary_timezone)
    previous = None
    consecutive = False
    count = 0
    with NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=output.parent) as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(PAIRED_COLUMNS)
        for count, (left, right) in enumerate(zip_longest(_bars(primary, primary_zone), _bars(es, es_zone)), 1):
            if left is None or right is None or left[0] != right[0]:
                nq_stamp = left[0].isoformat() if left else "EOF"
                es_stamp = right[0].isoformat() if right else "EOF"
                raise ValueError(f"Unmatched bar {count}: primary {nq_stamp}, ES {es_stamp}.")
            stamp, row = left
            if previous is not None and (stamp - previous).total_seconds() == 60:
                consecutive = True
            writer.writerow([*row, right[1][5]])
            previous = stamp
        if not consecutive:
            raise ValueError("Paired data must contain consecutive one-minute bars.")
        stream.flush()
        output.hardlink_to(stream.name)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary", type=Path, help="Standard NQ or MNQ OHLCV CSV")
    parser.add_argument("es", type=Path, help="Standard ES OHLCV CSV")
    parser.add_argument("output", type=Path, help="New paired CSV (primary timezone)")
    parser.add_argument("--timezone", required=True, help="Saved source timezone of the primary CSV")
    parser.add_argument("--es-timezone", help="ES source timezone, if different")
    args = parser.parse_args()
    try:
        count = pair(args.primary, args.es, args.output, args.timezone, args.es_timezone)
    except (ValueError, OSError, csv.Error, ZoneInfoNotFoundError) as exc:
        parser.error(str(exc))
    print(f"Paired {count} bars. Upload {args.output} with source timezone {args.timezone}.")


if __name__ == "__main__":
    main()

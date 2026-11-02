"""Check the manually maintained NQ closure CSV without changing it or trading.

This validates file structure and declared date bounds, not exchange accuracy
or holiday completeness. Verify new rows against the notices in calendars/README.md.
Uses only the Python standard library; no application server is needed.
"""

import argparse
from collections import Counter
import csv
from datetime import date, time
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "coverage_start", "coverage_end",
    "session_date", "closure_type", "close_time_local", "timezone", "event",
    "source_url", "source_note", "verified_on",
]


def validate(path, start=None, end=None):
    raw = path.read_bytes()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != FIELDS:
            raise ValueError("Headers must be exactly: " + ",".join(FIELDS))
        rows = list(reader)
    if not rows:
        raise ValueError("The calendar has no exception rows.")
    declared_start = date.fromisoformat(rows[0]["coverage_start"])
    declared_end = date.fromisoformat(rows[0]["coverage_end"])
    if start is not None and start != declared_start or end is not None and end != declared_end:
        raise ValueError("Requested coverage must match coverage_start/coverage_end in the CSV.")
    start, end = declared_start, declared_end
    if start > end:
        raise ValueError("Coverage start must be on/before coverage end.")
    previous = None
    for number, row in enumerate(rows, 2):
        prefix = f"CSV line {number}: "
        if None in row or any(value is None for value in row.values()):
            raise ValueError(prefix + "wrong number of columns.")
        if any(value != value.strip() for value in row.values()):
            raise ValueError(prefix + "leading/trailing whitespace is not allowed.")
        if any(not row[field] for field in FIELDS if field != "close_time_local"):
            raise ValueError(prefix + "a required field is empty.")
        for field in ("coverage_start", "coverage_end", "session_date", "verified_on"):
            value = row[field]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError(prefix + field + " must use YYYY-MM-DD.")
            date.fromisoformat(value)
        if row["coverage_start"] != start.isoformat() or row["coverage_end"] != end.isoformat():
            raise ValueError(prefix + "all rows must declare the same coverage bounds.")
        day = date.fromisoformat(row["session_date"])
        if not start <= day <= end:
            raise ValueError(prefix + "session_date is outside declared coverage.")
        if day.weekday() >= 5:
            raise ValueError(prefix + "ordinary weekend closures are not exception rows.")
        if previous is not None and day <= previous:
            raise ValueError(prefix + "dates must be unique and strictly increasing.")
        previous = day
        if row["timezone"] != "America/Chicago":
            raise ValueError(prefix + "timezone must be America/Chicago.")
        kind, close = row["closure_type"], row["close_time_local"]
        if kind == "full_close":
            if close:
                raise ValueError(prefix + "full_close must have an empty close_time_local.")
        elif kind == "early_close":
            if not re.fullmatch(r"\d{2}:\d{2}", close):
                raise ValueError(prefix + "early_close requires a 24-hour HH:MM time.")
            if not time.fromisoformat(close) < time(16):
                raise ValueError(prefix + "early_close must be before the regular 16:00 close.")
        else:
            raise ValueError(prefix + "closure_type must be early_close or full_close.")
        source = urlparse(row["source_url"])
        if source.scheme != "https" or not source.netloc:
            raise ValueError(prefix + "source_url must be an absolute HTTPS URL.")
    by_year = Counter(row["session_date"][:4] for row in rows)
    return {
        "status": "valid_structure",
        "file": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "declared_coverage_start": start.isoformat(),
        "declared_coverage_end": end.isoformat(),
        "rows": len(rows),
        "by_type": dict(sorted(Counter(row["closure_type"] for row in rows).items())),
        "by_year": dict(sorted(by_year.items())),
        "source_urls": len({row["source_url"] for row in rows}),
        "missing_exception_years": [year for year in range(start.year, end.year + 1)
                                    if str(year) not in by_year],
        "scope": "Structure only; does not verify source contents or holiday completeness.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=ROOT / "calendars/cme_nq_closures.csv")
    parser.add_argument("--start-date", type=date.fromisoformat, help="Assert the declared CSV coverage start.")
    parser.add_argument("--end-date", type=date.fromisoformat, help="Assert the declared CSV coverage end.")
    parser.add_argument("--output", type=Path, help="Save a new validation JSON; refuses to overwrite.")
    args = parser.parse_args()
    try:
        result = validate(args.file, args.start_date, args.end_date)
        rendered = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
    except (ValueError, OSError, csv.Error) as error:
        parser.exit(1, f"Calendar validation failed: {error}\n")
    print(rendered, end="")


if __name__ == "__main__":
    main()

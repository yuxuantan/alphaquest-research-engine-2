"""CSV contract and atomic persistence, independent of the web interface."""

import csv
import hashlib
import io
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

COLUMNS = ["Date", "Time", "Open", "High", "Low", "Close", "Volume", "UpVol", "DownVol"]
MAX_BYTES = 1_000_000_000
CHUNK_BYTES = 4 * 1024 * 1024
MAX_ERRORS = 20
DATE = re.compile(r"\d{2}/\d{2}/\d{4}", re.ASCII)
TIME = re.compile(r"\d{2}:\d{2}", re.ASCII)
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,4})?", re.ASCII)


class InvalidDataset(ValueError):
    def __init__(self, errors: list[dict], truncated: bool = False):
        self.errors = errors
        self.truncated = truncated
        super().__init__(errors[0]["message"])


def invalid(message: str, line: int | None = None, column: str | None = None):
    return {"line": line, "column": column, "message": message}


def parse_timestamp(date_value: str, time_value: str, source_zone: ZoneInfo) -> datetime:
    if not DATE.fullmatch(date_value) or not TIME.fullmatch(time_value):
        raise ValueError("Date must use MM/DD/YYYY and Time must use 24-hour HH:MM.")
    parsed = datetime.strptime(f"{date_value} {time_value}", "%m/%d/%Y %H:%M")
    candidates = {
        candidate.astimezone(timezone.utc)
        for fold in (0, 1)
        if (candidate := parsed.replace(tzinfo=source_zone, fold=fold))
        .astimezone(timezone.utc).astimezone(source_zone).replace(tzinfo=None) == parsed
    }
    if not candidates:
        raise ValueError("This local time does not exist due to a daylight-saving change; check the source timezone or export in UTC.")
    if len(candidates) > 1:
        raise ValueError("This local time is ambiguous due to a daylight-saving change; export in an unambiguous timezone such as UTC.")
    return candidates.pop()


def validate_csv_header(header) -> None:
    if header != COLUMNS:
        raise InvalidDataset([invalid("The header must be exactly: " + ",".join(COLUMNS), 1)])


def parse_csv_row(row: list[str], source_zone: ZoneInfo, previous_timestamp: datetime | None = None, line: int | None = None) -> tuple[datetime, tuple[Decimal, ...]]:
    """Shared upload/reader rules; return UTC time and seven ordered Decimals."""
    if len(row) != len(COLUMNS):
        raise InvalidDataset([invalid("Every row must contain exactly 9 non-empty fields; blank rows are not allowed.", line)])
    errors = []
    values = [value.strip() for value in row]
    timestamp = None
    try:
        timestamp = parse_timestamp(values[0], values[1], source_zone)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ValueError("Timestamps must be unique and strictly increasing in UTC; the file is never auto-sorted.")
    except (ValueError, OverflowError) as exc:
        errors.append(invalid(str(exc), line, "Date/Time"))
    numeric = {}
    for column, value in zip(COLUMNS[2:], values[2:]):
        if not NUMBER.fullmatch(value):
            errors.append(invalid("Must be a finite number (no missing values, NaN, or infinity).", line, column))
        else:
            numeric[column] = Decimal(value)
    for column in ("Volume", "UpVol", "DownVol"):
        if column in numeric and numeric[column] < 0:
            errors.append(invalid(f"{column} must be non-negative.", line, column))
    if all(column in numeric for column in ("Open", "High", "Low", "Close")):
        if not (numeric["Low"] <= min(numeric["Open"], numeric["Close"]) <= max(numeric["Open"], numeric["Close"]) <= numeric["High"]):
            errors.append(invalid("Require Low ≤ Open/Close ≤ High.", line, "High/Low"))
    if errors:
        raise InvalidDataset(errors)
    return timestamp, tuple(numeric[column] for column in COLUMNS[2:])


def validate_csv(raw: bytes, filename: str, source_timezone: str = "UTC") -> dict:
    return validate_csv_file(io.BytesIO(raw), filename, source_timezone)


def validate_csv_file(source, filename: str, source_timezone: str = "UTC", progress=None) -> dict:
    """Validate a seekable binary file without loading the whole CSV into memory."""
    if not filename.lower().endswith(".csv"):
        raise InvalidDataset([invalid("Choose a file with a .csv extension.")])
    try:
        zone = ZoneInfo(source_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise InvalidDataset([invalid("Choose a valid IANA source timezone, for example UTC or America/New_York.")]) from None
    source.seek(0, io.SEEK_END)
    total_bytes = source.tell()
    source.seek(0)
    size = 0
    digest = hashlib.sha256()
    bom_bytes = 0
    if progress:
        progress("hashing", 0, total_bytes, 0)
    while chunk := source.read(CHUNK_BYTES):
        if size == 0 and chunk.startswith(b"\xef\xbb\xbf"):
            bom_bytes = 3
        size += len(chunk)
        if size > MAX_BYTES:
            raise InvalidDataset([invalid("The CSV exceeds the 1 GB limit.")])
        if b"\x00" in chunk:
            raise InvalidDataset([invalid("The CSV contains a NUL byte.")])
        digest.update(chunk)
        if progress:
            progress("hashing", size, total_bytes, 0)
    source.seek(0)
    text = io.TextIOWrapper(source, encoding="utf-8-sig", newline="")
    try:
        processed = bom_bytes

        def counted_lines():
            nonlocal processed
            for line in text:
                processed += len(line.encode("utf-8"))
                yield line

        def rows_progress(rows):
            progress("validating", processed, size, rows)

        if progress:
            progress("validating", 0, size, 0)
        reader = csv.reader(counted_lines() if progress else text, strict=True)
        return _validate_rows(reader, filename, source_timezone, zone, size, digest.hexdigest(), rows_progress if progress else None)
    except UnicodeDecodeError:
        raise InvalidDataset([invalid("The CSV must be UTF-8 encoded.")]) from None
    finally:
        # The caller owns the binary file and may still need it for persistence.
        text.detach()


def _validate_rows(reader, filename, source_timezone, zone, size, sha256, progress=None):
    errors, preview = [], []
    count = 0
    first = previous = last = None
    interval = None
    irregular = False
    rows_checked = 0
    try:
        validate_csv_header(next(reader, None))
        for rows_checked, row in enumerate(reader, 1):
            line = reader.line_num
            try:
                timestamp, _ = parse_csv_row(row, zone, previous, line)
            except InvalidDataset as exc:
                errors.extend(exc.errors)
            else:
                values = [v.strip() for v in row]
                if previous is not None:
                    delta = timestamp - previous
                    step = delta.days * 86400_000000 + delta.seconds * 1_000000 + delta.microseconds
                    if interval is None:
                        interval = step
                    elif step != interval:
                        irregular = True
                first = first or timestamp
                previous = last = timestamp
                count += 1
                if len(preview) < 8:
                    preview.append({**dict(zip(COLUMNS, values)), "datetime": timestamp.isoformat().replace("+00:00", "Z")})
            if len(errors) >= MAX_ERRORS:
                raise InvalidDataset(errors[:MAX_ERRORS], truncated=True)
            if progress and rows_checked % 1000 == 0:
                progress(rows_checked)
    except csv.Error as exc:
        errors.append(invalid(f"Malformed CSV: {exc}", reader.line_num))
    if errors:
        raise InvalidDataset(errors[:MAX_ERRORS])
    if not count:
        raise InvalidDataset([invalid("Include at least one data row below the header.")])
    if progress:
        progress(rows_checked)
    regular = interval is not None and not irregular
    return {
        "filename": filename.replace("\\", "/").split("/")[-1][:255],
        "bytes": size,
        "sha256": sha256,
        "row_count": count,
        "start": first.isoformat().replace("+00:00", "Z"),
        "end": last.isoformat().replace("+00:00", "Z"),
        "source_timezone": source_timezone,
        "interval_seconds": interval / 1_000000 if regular else None,
        "interval_kind": "regular" if regular else "single row" if interval is None else "irregular",
        "columns": COLUMNS,
        "preview": preview,
        "warnings": ["Bar spacing varies. Gaps are preserved; no bars are filled or removed."] if irregular else [],
    }


class DuplicateDataset(ValueError):
    def __init__(self, dataset_id: str):
        self.dataset_id = dataset_id


class DatasetStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, source_timezone TEXT NOT NULL,
                metadata TEXT NOT NULL, csv BLOB NOT NULL,
                UNIQUE(sha256, source_timezone)
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS dataset_chunks (
                dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL, data BLOB NOT NULL,
                PRIMARY KEY(dataset_id, ordinal)
            )""")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save(self, raw: bytes, metadata: dict, name: str, symbol: str) -> dict:
        return self.save_file(io.BytesIO(raw), metadata, name, symbol)

    def save_file(self, source, metadata: dict, name: str, symbol: str, progress=None) -> dict:
        dataset = {
            **metadata, "id": uuid4().hex, "name": name, "symbol": symbol,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if progress:
            progress("saving", 0, metadata["bytes"], metadata["row_count"])
        try:
            with self.connect() as conn:
                conn.execute("INSERT INTO datasets VALUES (?, ?, ?, ?, ?)", (
                    dataset["id"], dataset["sha256"], dataset["source_timezone"], json.dumps(dataset), b"",
                ))
                source.seek(0)
                written = 0
                for ordinal, chunk in enumerate(iter(lambda: source.read(CHUNK_BYTES), b"")):
                    conn.execute("INSERT INTO dataset_chunks VALUES (?, ?, ?)", (dataset["id"], ordinal, chunk))
                    written += len(chunk)
                    if progress:
                        progress("saving", written, metadata["bytes"], metadata["row_count"])
                if progress:
                    progress("committing", written, metadata["bytes"], metadata["row_count"])
        except sqlite3.IntegrityError:
            with self.connect() as conn:
                row = conn.execute("SELECT id FROM datasets WHERE sha256=? AND source_timezone=?", (
                    dataset["sha256"], dataset["source_timezone"],
                )).fetchone()
            if row:
                raise DuplicateDataset(row[0]) from None
            raise
        return dataset

    def list(self) -> list[dict]:
        with self.connect() as conn:
            return [json.loads(row[0]) for row in conn.execute("SELECT metadata FROM datasets ORDER BY rowid DESC")]

    def get(self, dataset_id: str, download: bool = False):
        with self.connect() as conn:
            row = conn.execute("SELECT metadata FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        if not row:
            return None
        return b"".join(self.iter_csv(dataset_id)) if download else json.loads(row[0])

    def iter_csv(self, dataset_id: str):
        with self.connect() as conn:
            # Pin one read snapshot across the root/chunk queries, including deletion races.
            conn.execute("BEGIN")
            row = conn.execute("SELECT rowid, length(csv) FROM datasets WHERE id=?", (dataset_id,)).fetchone()
            if row and row[1]:
                # Older single-blob datasets also stream with bounded memory.
                with conn.blobopen("datasets", "csv", row[0], readonly=True) as blob:
                    while chunk := blob.read(CHUNK_BYTES):
                        yield chunk
            else:
                for chunk in conn.execute("SELECT data FROM dataset_chunks WHERE dataset_id=? ORDER BY ordinal", (dataset_id,)):
                    yield chunk[0]

    def delete(self, dataset_id: str) -> bool:
        with self.connect() as conn:
            return conn.execute("DELETE FROM datasets WHERE id=?", (dataset_id,)).rowcount == 1

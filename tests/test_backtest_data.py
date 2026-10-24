import csv
import hashlib
import io
import json
import subprocess
import sys
import tracemalloc
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from alphaquest import backtest_data as reader_module
from alphaquest.backtest_data import DatasetReadError, UnsupportedDatasetSchema, read_bars
from alphaquest.datasets import COLUMNS, DatasetStore, InvalidDataset, validate_csv, validate_csv_file

FIXTURES = Path(__file__).parent / "fixtures/backtest_contract"
CASES = json.loads((FIXTURES / "expected.json").read_text())["fixtures"]
HEADER = ",".join(COLUMNS) + "\n"
ROW = "01/05/2026,14:00,97,98,97,98,100,60,40\n"


@pytest.fixture
def store(tmp_path):
    return DatasetStore(tmp_path / "datasets.sqlite3")


def save(store, raw=None, source_timezone="UTC", *, unchecked=False, **overrides):
    raw = raw if raw is not None else (FIXTURES / "gap_deadline.csv").read_bytes()
    metadata = validate_csv((HEADER + ROW).encode() if unchecked else raw, "fixture.csv", source_timezone)
    if unchecked:
        metadata.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    metadata.update(overrides)
    return store.save(raw, metadata, "Reader fixture", "SYNTHETIC")


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_every_reviewed_fixture_preserves_fields_and_matches_utc_clock(store, case):
    raw = (FIXTURES / case["csv"]).read_bytes()
    saved = save(store, raw, case["source_timezone"])
    source_rows = list(csv.reader(io.StringIO(raw.decode())))[1:]
    with read_bars(store, saved["id"]) as iterator:
        bars = list(iterator)
    assert len(bars) == case["bar_count"]
    for number, (bar, row, expected) in enumerate(zip(bars, source_rows, case["expected_equity"][1:]), 1):
        assert bar.bar_number == number
        assert bar.source_fields == tuple(row)
        assert (bar.date, bar.time) == tuple(row[:2])
        assert bar.timestamp_utc == datetime.fromisoformat(expected["timestamp_utc"])
        assert bar.timestamp_utc.tzinfo is timezone.utc
        for attribute, value in zip(("open", "high", "low", "close", "volume", "up_vol", "down_vol"), row[2:]):
            assert isinstance(getattr(bar, attribute), Decimal)
            assert getattr(bar, attribute) == Decimal(value)
    assert all(left.timestamp_utc < right.timestamp_utc for left, right in zip(bars, bars[1:]))
    assert store.get(saved["id"]) == saved
    assert store.get(saved["id"], download=True) == raw


def test_decimal_precision_whitespace_bom_and_crlf_are_preserved(store):
    row = [" 01/05/2026 ", " 14:00 ", "+00100." + "0" * 35 + "1", "100." + "0" * 35 + "3", "99." + "9" * 36, "100." + "0" * 35 + "2", " 1.2500 ", "0.7500", "0.5000"]
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\r\n")
    writer.writerows([COLUMNS, row])
    raw = b"\xef\xbb\xbf" + text.getvalue().encode()
    saved = save(store, raw, "America/New_York")
    with read_bars(store, saved["id"]) as bars:
        bar = next(bars)
        assert bar.source_fields == tuple(row)
        assert (bar.date, bar.time) == (row[0], row[1])
        assert str(bar.open) == "100." + "0" * 35 + "1"
        assert str(bar.volume) == "1.2500"
        assert str(bar.up_vol) == "0.7500"
        assert str(bar.down_vol) == "0.5000"
        assert bar.timestamp_utc == datetime(2026, 1, 5, 19, tzinfo=timezone.utc)
        with pytest.raises(FrozenInstanceError):
            bar.close = Decimal("0")
        with pytest.raises(TypeError):
            bar.source_fields[0] = "changed"
    assert store.get(saved["id"], download=True) == raw


def test_saved_timezone_converts_across_calendar_day_without_override(store):
    raw = (HEADER + ROW.replace("14:00", "00:01")).encode()
    saved = save(store, raw, "Asia/Singapore")
    with read_bars(store, saved["id"]) as bars:
        assert next(bars).timestamp_utc == datetime(2026, 1, 4, 16, 1, tzinfo=timezone.utc)


def test_snapshot_releases_database_and_survives_dataset_deletion(store, monkeypatch):
    saved = save(store)
    original = store.connect
    active = 0

    @contextmanager
    def connection():
        nonlocal active
        active += 1
        try:
            with original() as conn:
                yield conn
        finally:
            active -= 1

    monkeypatch.setattr(store, "connect", connection)
    with read_bars(store, saved["id"]) as bars:
        assert active == 0
        first = next(bars)
        assert active == 0
        assert store.delete(saved["id"])
        rest = list(bars)
        assert active == 0
        assert len(rest) + 1 == saved["row_count"]
        assert first.timestamp_utc < rest[0].timestamp_utc
    assert store.get(saved["id"]) is None


def test_rows_are_parsed_on_demand_and_bad_rows_are_not_skipped(store, monkeypatch):
    raw = (HEADER + ROW + ROW.replace("14:00", "14:01").replace(",60,40", ",NaN,40")).encode()
    saved = save(store, raw, unchecked=True, row_count=2)
    original = reader_module.parse_csv_row
    parsed = []

    def parse(*args, **kwargs):
        parsed.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(reader_module, "parse_csv_row", parse)
    with read_bars(store, saved["id"]) as bars:
        assert parsed == []
        assert next(bars).bar_number == 1
        assert len(parsed) == 1
        with pytest.raises(InvalidDataset) as error:
            next(bars)
        assert error.value.errors[0]["column"] == "UpVol"
        assert error.value.errors[0]["line"] == 3
        assert len(parsed) == 2


@pytest.mark.parametrize("time", ["14:00", "13:59"])
def test_duplicate_or_out_of_order_bars_fail_without_sorting(store, time):
    raw = (HEADER + ROW + ROW.replace("14:00", time)).encode()
    saved = save(store, raw, unchecked=True, row_count=2)
    with read_bars(store, saved["id"]) as bars:
        assert next(bars).time == "14:00"
        with pytest.raises(InvalidDataset, match="strictly increasing"):
            next(bars)


@pytest.mark.parametrize("local", ["03/08/2026,02:30", "11/01/2026,01:30"])
def test_reader_reuses_dst_ambiguity_and_nonexistent_time_rejections(store, local):
    raw = (HEADER + ROW.replace("01/05/2026,14:00", local)).encode()
    saved = save(store, raw, "America/New_York", unchecked=True)
    with read_bars(store, saved["id"]) as bars:
        with pytest.raises(InvalidDataset, match="daylight-saving"):
            next(bars)


@pytest.mark.parametrize("raw, message", [
    ((HEADER.replace("Date", "date") + ROW).encode(), "header must be exactly"),
    ((HEADER + ROW.replace(",98,97,98", ",90,97,98")).encode(), "Low ≤ Open/Close ≤ High"),
    ((HEADER + ROW.replace(",40\n", ",-1\n")).encode(), "DownVol must be non-negative"),
    ((HEADER + ROW.replace(",60,40", ",60")).encode(), "exactly 9"),
    ((HEADER + ROW + "\n").encode(), "exactly 9"),
    ((HEADER + ROW.replace(",40\n", ',"40\n')).encode(), "Malformed CSV"),
    ((HEADER + ROW).encode() + b"\xff", "UTF-8"),
    (HEADER.encode(), "at least one data row"),
])
def test_reader_reuses_csv_validation_rules(store, raw, message):
    saved = save(store, raw, unchecked=True)
    with read_bars(store, saved["id"]) as bars:
        with pytest.raises(InvalidDataset, match=message):
            list(bars)


def test_missing_dataset_and_unsupported_schema(store):
    with pytest.raises(DatasetReadError, match="not found"):
        with read_bars(store, "missing"):
            pass
    legacy = save(store, columns=["datetime", "open", "high", "low", "close", "volume"])
    with pytest.raises(UnsupportedDatasetSchema, match="Unsupported dataset schema"):
        with read_bars(store, legacy["id"]):
            pass


@pytest.mark.parametrize("zone", [None, "", 42, "Mars/Olympus", "/invalid/path"])
def test_missing_or_invalid_saved_timezone_is_not_guessed(store, zone):
    saved = save(store)
    if zone is None:
        saved.pop("source_timezone")
    else:
        saved["source_timezone"] = zone
    with store.connect() as conn:
        conn.execute("UPDATE datasets SET metadata=? WHERE id=?", (json.dumps(saved), saved["id"]))
    with pytest.raises(DatasetReadError, match="saved source timezone"):
        with read_bars(store, saved["id"]):
            pass


@pytest.mark.parametrize("corruption", ["bytes", "row_count"])
def test_corrupt_bytes_or_row_count_do_not_silently_pass(store, corruption):
    saved = save(store, **({"row_count": 999} if corruption == "row_count" else {}))
    if corruption == "bytes":
        with store.connect() as conn:
            conn.execute("UPDATE dataset_chunks SET data=substr(data,1,length(data)-1) WHERE dataset_id=? AND ordinal=0", (saved["id"],))
        with pytest.raises(DatasetReadError, match="do not match"):
            with read_bars(store, saved["id"]):
                pass
    else:
        with read_bars(store, saved["id"]) as bars:
            with pytest.raises(DatasetReadError, match="row count"):
                list(bars)


@pytest.mark.parametrize("raise_inside", [False, True])
def test_temporary_snapshot_is_closed_after_partial_consumption(store, monkeypatch, raise_inside):
    saved = save(store)
    original = reader_module.TemporaryFile
    files = []

    def temporary_file(*args, **kwargs):
        file = original(*args, **kwargs)
        files.append(file)
        return file

    monkeypatch.setattr(reader_module, "TemporaryFile", temporary_file)
    try:
        with read_bars(store, saved["id"]) as bars:
            next(bars)
            assert not files[0].closed
            if raise_inside:
                raise RuntimeError("caller stopped")
    except RuntimeError:
        assert raise_inside
    assert len(files) == 1 and files[0].closed
    assert list(bars) == []


@pytest.mark.parametrize("storage", ["chunks", "legacy_blob"])
def test_large_snapshot_and_partial_read_use_bounded_memory(store, tmp_path, storage):
    path = tmp_path / "large.csv"
    with path.open("w", newline="") as file:
        file.write(HEADER)
        for number in range(600):
            stamp = datetime(2026, 1, 5) + timedelta(minutes=number)
            file.write(stamp.strftime("%m/%d/%Y,%H:%M") + ",1,2,0,1," + " " * 60000 + "3,1,2\n")
    assert path.stat().st_size > 32 * 1024 * 1024
    with path.open("rb") as source:
        metadata = validate_csv_file(source, path.name)
        if storage == "chunks":
            saved = store.save_file(source, metadata, "Large", "")
            dataset_id = saved["id"]
        else:
            dataset_id = "legacy-large"
            metadata.update(id=dataset_id, name="Large legacy", symbol="")
            with store.connect() as conn:
                cursor = conn.execute("INSERT INTO datasets VALUES (?, ?, ?, ?, zeroblob(?))", (
                    dataset_id, metadata["sha256"], metadata["source_timezone"], json.dumps(metadata), metadata["bytes"],
                ))
                source.seek(0)
                with conn.blobopen("datasets", "csv", cursor.lastrowid) as blob:
                    while chunk := source.read(4 * 1024 * 1024):
                        blob.write(chunk)
    tracemalloc.start()
    try:
        with read_bars(store, dataset_id) as bars:
            first = next(bars)
            assert first.bar_number == 1
            assert first.volume == Decimal("3")
            assert len(first.source_fields[6]) == 60001
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # Joining/loading this 36 MB CSV would exceed this ceiling before parsing.
    assert peak < 16 * 1024 * 1024, f"Peak traced Python allocation: {peak} bytes"


def test_demo_command_is_runnable_and_does_not_create_a_normal_library(tmp_path, monkeypatch):
    library = tmp_path / "normal-library"
    monkeypatch.setenv("ALPHAQUEST_DATA_DIR", str(library))
    result = subprocess.run([sys.executable, "-m", "alphaquest.backtest_data", "--demo", "--limit", "3"], cwd=Path(__file__).parents[1], text=True, capture_output=True, check=True)
    bars = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(bars) == 3
    assert bars[0]["time"] == "14:00"
    assert bars[0]["timestamp_utc"] == "2026-01-05T19:00:00Z"
    assert bars[2]["close"] == "100"
    assert len(bars[0]["source_fields"]) == 9
    assert not library.exists()


def test_command_reads_an_existing_id_and_limits_parsing(store):
    raw = (HEADER + ROW + ROW.replace("14:00", "14:01").replace(",60,40", ",NaN,40")).encode()
    saved = save(store, raw, unchecked=True, row_count=2)
    result = subprocess.run([sys.executable, "-m", "alphaquest.backtest_data", "--database", str(store.path), "--dataset-id", saved["id"], "--limit", "1"], text=True, capture_output=True, check=True)
    assert len(result.stdout.splitlines()) == 1
    assert json.loads(result.stdout)["bar_number"] == 1

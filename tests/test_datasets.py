import hashlib
import io
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from alphaquest.datasets import DatasetStore, DuplicateDataset, InvalidDataset, validate_csv
from alphaquest import datasets as datasets_module

HEADER = "Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol\n"
ROW = "05/21/2017,18:01,5652.75,5654.50,5651.25,5654.00,182,83,99\n"
SAMPLE = (Path(__file__).parents[1] / "alphaquest/web/example.csv").read_bytes()


def csv(*rows):
    return (HEADER + "".join(rows)).encode()


def test_metadata_and_original_precision():
    result = validate_csv(SAMPLE, "example.csv")
    assert result["row_count"] == 5
    assert result["interval_seconds"] == 60
    assert result["interval_kind"] == "regular"
    assert result["start"] == "2017-05-21T18:01:00Z"
    assert result["end"] == "2017-05-21T18:05:00Z"
    assert result["sha256"] == hashlib.sha256(SAMPLE).hexdigest()
    assert result["preview"][0]["High"] == "5654.50"
    assert result["preview"][0]["UpVol"] == "83"
    assert result["preview"][0]["DownVol"] == "99"
    assert result["preview"][0]["Date"] == "05/21/2017"
    assert result["preview"][0]["Time"] == "18:01"
    assert result["preview"][0]["datetime"] == result["start"]
    assert result["source_timezone"] == "UTC"
    assert result["columns"] == HEADER.strip().split(",")


@pytest.mark.parametrize("raw", [
    b"", HEADER.encode(), (HEADER.strip() + ",extra\n").encode(),
    HEADER.replace("Date", "date").encode() + ROW.encode(),
    HEADER.replace("High,Low", "Low,High").encode() + ROW.encode(),
    csv(ROW.replace(",5654.50", ",")),
    csv(ROW.replace(",5654.50", ",NaN")),
    csv(ROW.replace(",5654.50", ",Infinity")),
    csv(ROW.replace(",182,", ",-1,")),
    csv(ROW.replace(",83,", ",-1,")),
    csv(ROW.replace(",99\n", ",-1\n")),
    csv(ROW.replace(",83,", ",NaN,")),
    csv(ROW.replace(",99\n", ",Infinity\n")),
    csv(ROW.replace(",5654.50", ",5600")),
    csv(ROW.replace(",5651.25", ",5660")),
    csv(ROW.replace("05/21/2017", "21/05/2017")),
    csv(ROW.replace("05/21/2017", "02/30/2017")),
    csv(ROW.replace("05/21/2017", "2017-05-21")),
    csv(ROW.replace("05/21/2017", "5/21/2017")),
    csv(ROW.replace("18:01", "24:01")),
    csv(ROW.replace("18:01", "18:60")),
    csv(ROW.replace("18:01", "6:01 PM")),
    csv(ROW.replace("18:01", "18:01:00")),
    csv(ROW.replace("18:01", "18:01Z")),
    csv(ROW, ROW),
    csv(ROW.replace("18:01", "18:02"), ROW),
    csv(ROW, "\n"),
    csv(ROW.replace(",182,", ",182,extra,")),
    csv(ROW.replace(",182,", ",1_240,")),
    csv(ROW.replace(",182,", ",\x00,")),
    csv(ROW.replace(",182,", ',"182,')),
    csv(ROW.replace(",83,99", "")),
    b"datetime,open,high,low,close,volume\n2017-05-21T18:01:00Z,1,2,0,1,1\n",
    b"\xff\xfe" + csv(ROW),
])
def test_rejects_invalid_csv(raw):
    with pytest.raises(InvalidDataset):
        validate_csv(raw, "bars.csv")


def test_error_locations():
    with pytest.raises(InvalidDataset) as exc:
        validate_csv(csv(ROW, ROW.replace("18:01", "18:02").replace(",182,", ",-1,")), "bars.csv")
    assert exc.value.errors[0]["line"] == 3
    assert exc.value.errors[0]["column"] == "Volume"


def test_error_output_is_bounded():
    with pytest.raises(InvalidDataset) as exc:
        validate_csv(csv(*(["bad\n"] * 100)), "bars.csv")
    assert len(exc.value.errors) == 20
    assert exc.value.truncated is True


def test_bom_crlf_and_zero_volume_are_supported():
    raw = b"\xef\xbb\xbf" + csv(ROW.replace(",182,83,99", ",0,0,0")).replace(b"\n", b"\r\n")
    assert validate_csv(raw, "BARS.CSV")["row_count"] == 1


def test_negative_prices_are_valid_when_ohlc_consistent():
    assert validate_csv(csv("01/05/2026,00:00,-20,-10,-30,-15,0,0,0\n"), "bars.csv")["row_count"] == 1


def test_declared_timezone_and_utc_ordering():
    result = validate_csv(csv(ROW), "bars.csv", "America/New_York")
    assert result["start"] == "2017-05-21T22:01:00Z"
    assert result["source_timezone"] == "America/New_York"
    assert result["preview"][0]["Date"] == "05/21/2017"
    assert result["preview"][0]["Time"] == "18:01"


@pytest.mark.parametrize("timestamp", ["03/08/2026,02:30", "11/01/2026,01:30"])
def test_rejects_nonexistent_or_ambiguous_dst_times(timestamp):
    with pytest.raises(InvalidDataset, match="daylight-saving"):
        validate_csv(csv(ROW.replace("05/21/2017,18:01", timestamp)), "bars.csv", "America/New_York")


def test_month_first_dates_and_cross_day_utc_conversion():
    raw = csv(ROW.replace("05/21/2017,18:01", "05/06/2017,00:01"))
    assert validate_csv(raw, "bars.csv")["start"] == "2017-05-06T00:01:00Z"
    assert validate_csv(raw, "bars.csv", "Asia/Singapore")["start"] == "2017-05-05T16:01:00Z"


def test_up_down_volume_are_preserved_without_assuming_their_sum():
    result = validate_csv(csv(ROW.replace(",182,", ",200,")), "bars.csv")
    assert result["preview"][0]["Volume"] == "200"
    assert result["preview"][0]["UpVol"] == "83"
    assert result["preview"][0]["DownVol"] == "99"


def test_gaps_are_reported_not_filled():
    raw = csv(ROW, ROW.replace("18:01", "18:02"), ROW.replace("18:01", "18:06"))
    result = validate_csv(raw, "bars.csv")
    assert result["row_count"] == 3
    assert result["interval_seconds"] is None
    assert result["interval_kind"] == "irregular"
    assert result["warnings"]


def test_filename_and_timezone_checks():
    with pytest.raises(InvalidDataset):
        validate_csv(csv(ROW), "bars.txt")
    with pytest.raises(InvalidDataset):
        validate_csv(csv(ROW), "bars.csv", "Mars/Olympus")
    assert validate_csv(csv(ROW), "../../bars.csv")["filename"] == "bars.csv"


def test_atomic_storage_restart_and_duplicate_rejection(tmp_path):
    path = tmp_path / "datasets.sqlite3"
    store = DatasetStore(path)
    metadata = validate_csv(SAMPLE, "example.csv")
    saved = store.save(SAMPLE, metadata, "ES January", "ES")
    reopened = DatasetStore(path)
    assert reopened.get(saved["id"]) == saved
    assert reopened.list() == [saved]
    assert reopened.get(saved["id"], download=True) == SAMPLE
    with pytest.raises(DuplicateDataset) as exc:
        reopened.save(SAMPLE, metadata, "Another name", "ES")
    assert exc.value.dataset_id == saved["id"]
    assert len(reopened.list()) == 1


def test_concurrent_identical_saves_create_one_dataset(tmp_path):
    store = DatasetStore(tmp_path / "datasets.sqlite3")
    metadata = validate_csv(SAMPLE, "example.csv")

    def save():
        try:
            return store.save(SAMPLE, metadata, "ES", "ES")["id"]
        except DuplicateDataset as exc:
            return exc.dataset_id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: save(), range(4)))
    assert len(set(ids)) == 1
    assert len(store.list()) == 1


def test_delete_removes_only_selected_dataset_and_allows_reupload(tmp_path):
    path = tmp_path / "datasets.sqlite3"
    store = DatasetStore(path)
    first = store.save(SAMPLE, validate_csv(SAMPLE, "first.csv"), "First", "ES")
    other_raw = SAMPLE.replace(b",182,", b",183,")
    second = store.save(other_raw, validate_csv(other_raw, "second.csv"), "Second", "ES")
    assert store.delete(first["id"]) is True
    reopened = DatasetStore(path)
    assert reopened.get(first["id"]) is None
    assert reopened.get(first["id"], download=True) is None
    assert reopened.list() == [second]
    assert reopened.get(second["id"], download=True) == other_raw
    assert reopened.delete(first["id"]) is False
    assert reopened.delete("missing") is False
    saved_again = reopened.save(SAMPLE, validate_csv(SAMPLE, "first.csv"), "First", "ES")
    assert saved_again["id"] != first["id"]


def test_validation_streams_and_enforces_exact_size_boundary(monkeypatch):
    class BoundedReader(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= datasets_module.CHUNK_BYTES
            return super().read(size)

    assert datasets_module.MAX_BYTES == 1_000_000_000
    monkeypatch.setattr(datasets_module, "MAX_BYTES", len(SAMPLE))
    source = BoundedReader(SAMPLE)
    assert datasets_module.validate_csv_file(source, "example.csv")["bytes"] == len(SAMPLE)
    assert not source.closed
    with pytest.raises(InvalidDataset, match="1 GB"):
        datasets_module.validate_csv_file(BoundedReader(SAMPLE + b"\n"), "example.csv")


def test_chunk_storage_preserves_bytes_and_deletes_all_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "CHUNK_BYTES", 32)
    store = DatasetStore(tmp_path / "datasets.sqlite3")
    saved = store.save(SAMPLE, validate_csv(SAMPLE, "example.csv"), "Chunked", "ES")
    chunks = list(store.iter_csv(saved["id"]))
    assert len(chunks) > 1
    assert all(len(chunk) <= 32 for chunk in chunks)
    assert b"".join(chunks) == SAMPLE
    with store.connect() as conn:
        assert conn.execute("SELECT length(csv) FROM datasets").fetchone()[0] == 0
    store.delete(saved["id"])
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM dataset_chunks").fetchone()[0] == 0


def test_existing_single_blob_datasets_remain_readable(tmp_path):
    store = DatasetStore(tmp_path / "datasets.sqlite3")
    metadata = {**validate_csv(SAMPLE, "example.csv"), "id": "legacy", "name": "Legacy", "symbol": "ES"}
    with store.connect() as conn:
        conn.execute("INSERT INTO datasets VALUES (?, ?, ?, ?, ?)", (
            "legacy", metadata["sha256"], metadata["source_timezone"], json.dumps(metadata), SAMPLE,
        ))
    assert store.get("legacy") == metadata
    assert b"".join(store.iter_csv("legacy")) == SAMPLE
    assert store.delete("legacy") is True


def test_interrupted_chunk_write_rolls_back_metadata_and_csv(tmp_path):
    class BrokenSource(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise OSError("Read interrupted")
            return super().read(10)

    store = DatasetStore(tmp_path / "datasets.sqlite3")
    with pytest.raises(OSError, match="interrupted"):
        store.save_file(BrokenSource(SAMPLE), validate_csv(SAMPLE, "example.csv"), "Broken", "ES")
    assert store.list() == []
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM dataset_chunks").fetchone()[0] == 0


def test_validation_reports_real_bytes_and_row_counts():
    rows = []
    for number in range(2001):
        timestamp = datetime(2026, 1, 5) + timedelta(minutes=number)
        rows.append(timestamp.strftime("%m/%d/%Y,%H:%M") + ",1,2,0,1,3,1,2\r\n")
    raw = b"\xef\xbb\xbf" + (HEADER.replace("\n", "\r\n") + "".join(rows)).encode()
    events = []
    result = datasets_module.validate_csv_file(io.BytesIO(raw), "example.csv", "UTC", lambda *event: events.append(event))
    assert events[0] == ("hashing", 0, len(raw), 0)
    checks = [event for event in events if event[0] == "validating"]
    assert [event[3] for event in checks] == [0, 1000, 2000, 2001]
    assert checks[-1] == ("validating", len(raw), len(raw), 2001)
    assert [event[1] for event in checks] == sorted(event[1] for event in checks)
    assert result["row_count"] == 2001


def test_storage_progress_reports_chunks_and_commit_before_return(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets_module, "CHUNK_BYTES", 32)
    store = DatasetStore(tmp_path / "datasets.sqlite3")
    events = []

    def report(*event):
        events.append(event)
        if event[0] == "committing":
            assert store.list() == []

    store.save_file(io.BytesIO(SAMPLE), validate_csv(SAMPLE, "example.csv"), "Progress", "ES", report)
    assert events[0] == ("saving", 0, len(SAMPLE), 5)
    assert events[-2] == ("saving", len(SAMPLE), len(SAMPLE), 5)
    assert events[-1] == ("committing", len(SAMPLE), len(SAMPLE), 5)
    assert len(store.list()) == 1

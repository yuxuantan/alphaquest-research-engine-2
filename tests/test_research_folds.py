"""Hand-declared chronological boundaries, causal prefixes and session clocks."""

from dataclasses import FrozenInstanceError, asdict
from datetime import date, datetime, timezone
import json

import pytest
from pydantic import ValidationError

from alphaquest.backtest_data import DateRange, DatasetReadError, read_selected_bars
from alphaquest.datasets import COLUMNS, DatasetStore, validate_csv
from alphaquest.optimization_cache import digest
from alphaquest.prepared_data import prepare_data
from alphaquest.research_folds import (
    SESSION_CONVENTION, FoldSettings, SessionDateRange, generate_folds,
    inventory_sessions,
)


# Hand-written weekday labels. The planner must not synthesize weekends or infer
# missing sessions from prices; callers supply the observed session inventory.
DAYS = [
    "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16",
    "2026-01-19", "2026-01-20", "2026-01-21", "2026-01-22", "2026-01-23",
    "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30",
]


def settings(**overrides):
    values = dict(outer_train_sessions=8, outer_test_sessions=2,
                  inner_train_sessions=2, inner_validation_sessions=2,
                  mode="rolling", purge_sessions=1, embargo_sessions=1,
                  minimum_inner_folds=2, minimum_outer_folds=2)
    return FoldSettings(**(values | overrides))


def test_rolling_hand_dates_exclusions_and_incomplete_tail():
    folds = generate_folds(DAYS[:15], settings())
    assert len(folds) == 2  # Jan 23 cannot form another complete two-session test.
    first, second = folds
    assert first["train"] == dict(first_session="2026-01-05", last_session="2026-01-14", sessions=DAYS[:8])
    assert first["test"] == dict(first_session="2026-01-19", last_session="2026-01-20", sessions=DAYS[10:12])
    assert first["excluded"] == dict(purge_sessions=["2026-01-15"], embargo_sessions=["2026-01-16"])
    assert first["information_cutoff_session"] == "2026-01-14"
    assert second["train"]["sessions"] == DAYS[2:10]
    assert second["test"]["sessions"] == ["2026-01-21", "2026-01-22"]
    assert second["excluded"] == dict(purge_sessions=["2026-01-19"], embargo_sessions=["2026-01-20"])
    assert [fold["index"] for fold in folds] == [1, 2]
    inner = first["inner"]
    assert len(inner) == 2
    assert inner[0]["train"]["sessions"] == ["2026-01-05", "2026-01-06"]
    assert inner[0]["excluded"] == dict(purge_sessions=["2026-01-07"], embargo_sessions=["2026-01-08"])
    assert inner[0]["validation"]["sessions"] == ["2026-01-09", "2026-01-12"]
    assert inner[1]["train"]["sessions"] == ["2026-01-07", "2026-01-08"]
    assert inner[1]["validation"]["sessions"] == ["2026-01-13", "2026-01-14"]


def test_expanding_increases_training_and_inner_evidence_only_in_past():
    folds = generate_folds(DAYS, settings(mode="expanding"))
    assert len(folds) == 5
    assert [len(f["train"]["sessions"]) for f in folds] == [8, 10, 12, 14, 16]
    assert [len(f["inner"]) for f in folds] == [2, 3, 4, 5, 6]
    assert folds[0]["inner"][1]["train"]["sessions"] == DAYS[:4]
    assert folds[1]["train"]["sessions"] == DAYS[:10]
    assert folds[-1]["test"]["sessions"] == ["2026-01-29", "2026-01-30"]
    for fold in folds:
        assert fold["train"]["first_session"] == DAYS[0]
        assert fold["information_cutoff_session"] < fold["test"]["first_session"]
        for inner in fold["inner"]:
            assert inner["train"]["last_session"] < inner["validation"]["first_session"]
            assert set(inner["train"]["sessions"] + inner["validation"]["sessions"]) <= set(fold["train"]["sessions"])
            assert inner["validation"]["last_session"] <= fold["information_cutoff_session"]


@pytest.mark.parametrize("mode", ["rolling", "expanding"])
def test_prefix_stability_nonoverlap_and_no_input_mutation(mode):
    original = list(DAYS)
    small = generate_folds(DAYS[:14], settings(mode=mode))
    large = generate_folds(DAYS, settings(mode=mode))
    assert large[:len(small)] == small
    assert DAYS == original
    tested = [day for fold in large for day in fold["test"]["sessions"]]
    assert len(tested) == len(set(tested))
    assert tested == DAYS[10:]
    for fold in large:
        assert fold["convention"] == SESSION_CONVENTION
        assert fold["boundary_policy"] == "cold_start_finish_flat"
        assert not set(fold["train"]["sessions"]) & set(fold["test"]["sessions"])
    # Returned date lists do not alias the input or another fold's dates.
    large[0]["train"]["sessions"].append("2099-01-01")
    assert DAYS == original
    assert "2099-01-01" not in large[0]["inner"][0]["train"]["sessions"]


def test_zero_gap_and_nonconsecutive_observed_sessions():
    declared = settings(outer_train_sessions=6, purge_sessions=0, embargo_sessions=0)
    # Dates omitted by the inventory remain absent, not silently filled.
    days = DAYS[:8] + DAYS[10:]
    folds = generate_folds(days, declared)
    assert folds[0]["train"]["sessions"] == DAYS[:6]
    assert folds[0]["test"]["sessions"] == ["2026-01-13", "2026-01-14"]
    assert folds[1]["test"]["sessions"] == ["2026-01-19", "2026-01-20"]
    assert folds[0]["excluded"] == dict(purge_sessions=[], embargo_sessions=[])


def test_insufficient_history_never_silently_weakens_minimums():
    with pytest.raises(ValueError, match="need at least 14.*have 13"):
        generate_folds(DAYS[:13], settings())
    with pytest.raises(ValidationError, match="minimum inner folds"):
        settings(outer_train_sessions=7)
    assert len(generate_folds(DAYS[:14], settings())) == 2


@pytest.mark.parametrize("field,value", [
    ("outer_train_sessions", True), ("outer_test_sessions", "2"),
    ("inner_train_sessions", 2.0), ("inner_validation_sessions", 0),
    ("purge_sessions", -1), ("embargo_sessions", False),
    ("minimum_inner_folds", 0), ("minimum_outer_folds", None),
    ("mode", "random"), ("outer_test_sessions", 100001),
])
def test_settings_are_strict(field, value):
    with pytest.raises(ValidationError):
        settings(**{field: value})


def test_settings_reject_unknowns_and_mutation():
    with pytest.raises(ValidationError):
        settings(future_selection=True)
    declared = settings()
    with pytest.raises(ValidationError):
        declared.mode = "expanding"
    assert FoldSettings().model_dump() == dict(
        outer_train_sessions=60, outer_test_sessions=20, inner_train_sessions=20,
        inner_validation_sessions=10, mode="rolling", purge_sessions=1,
        embargo_sessions=0, minimum_inner_folds=2, minimum_outer_folds=2,
    )


@pytest.mark.parametrize("days", [
    [], (), "2026-01-05", DAYS[:2] + [DAYS[1]], list(reversed(DAYS)),
    ["2026-1-05"], ["2026-02-30"], [date(2026, 1, 5)], [True],
])
def test_dates_require_exact_ordered_iso_labels(days):
    with pytest.raises(ValueError):
        generate_folds(days, settings())


def test_settings_object_is_required():
    with pytest.raises(TypeError, match="FoldSettings"):
        generate_folds(DAYS, settings().model_dump())


@pytest.mark.parametrize("day,before,after", [
    ("2026-01-05", "2026-01-04T22:59:00+00:00", "2026-01-04T23:00:00+00:00"),
    ("2026-03-09", "2026-03-08T21:59:00+00:00", "2026-03-08T22:00:00+00:00"),
    ("2026-11-02", "2026-11-01T22:59:00+00:00", "2026-11-01T23:00:00+00:00"),
])
def test_session_date_range_uses_chicago_evenings_and_dst(day, before, after):
    selected = SessionDateRange.parse(day, day)
    assert not selected.contains(datetime.fromisoformat(before), timezone.utc)
    assert selected.contains(datetime.fromisoformat(after), timezone.utc)
    assert selected.contains(datetime.fromisoformat(day + "T15:00:00+00:00"))
    assert not selected.contains(datetime.fromisoformat(day + "T23:01:00+00:00"))


def test_session_range_is_frozen_explicit_and_cannot_alias_calendar_cache():
    selected = SessionDateRange.parse(DAYS[0], DAYS[1])
    ordinary = DateRange.parse(DAYS[0], DAYS[1])
    assert selected.active
    assert selected.to_dict() == dict(from_date=DAYS[0], to_date=DAYS[1], convention=SESSION_CONVENTION)
    assert asdict(selected)["convention"] == SESSION_CONVENTION
    assert SESSION_CONVENTION in json.dumps(selected, default=str)
    assert digest(selected) != digest(ordinary)
    assert digest(asdict(selected)) != digest(asdict(ordinary))
    with pytest.raises(FrozenInstanceError):
        selected.convention = "source_local"
    with pytest.raises(ValueError, match="Unsupported session convention"):
        SessionDateRange(date(2026, 1, 5), date(2026, 1, 6), "source_local")
    with pytest.raises(ValueError, match="timezone-aware"):
        selected.contains(datetime(2026, 1, 5, 15))
    with pytest.raises(ValueError):
        SessionDateRange.parse(DAYS[1], DAYS[0])
    assert not SessionDateRange().active


def save_source(tmp_path, stamps=None, price=100):
    stamps = stamps or [("01/04/2026", "22:59"), ("01/04/2026", "23:01"),
                        ("01/05/2026", "15:00"), ("01/05/2026", "23:01")]
    raw = (",".join(COLUMNS) + "\n" + "\n".join(
        f"{day},{clock},{price},{price},{price},{price},10,5,5"
        for day, clock in stamps) + "\n").encode()
    store = DatasetStore(tmp_path / "datasets.sqlite3")
    saved = store.save(raw, validate_csv(raw, "synthetic.csv", "UTC"), "SYNTHETIC session boundaries", "NQ")
    return store, saved


def test_streaming_inventory_retains_only_metadata_and_does_not_infer_sessions(tmp_path):
    source, saved = save_source(tmp_path)
    result = inventory_sessions(source, saved["id"])
    assert result["sessions"] == ["2026-01-04", "2026-01-05", "2026-01-06"]
    assert result["counts"] == {"2026-01-04": 1, "2026-01-05": 2, "2026-01-06": 1}
    assert result["source"] == dict(dataset_id=saved["id"], sha256=saved["sha256"], source_timezone="UTC", row_count=4)
    assert result["bounds"]["2026-01-05"] == dict(first_utc="2026-01-04T23:01:00Z", last_utc="2026-01-05T15:00:00Z")
    assert set(result) == {"convention", "source", "sessions", "counts", "bounds", "coverage", "session_content_sha256"}
    assert result["convention"] == SESSION_CONVENTION
    assert source.get(saved["id"]) == saved
    changed, changed_saved = save_source(tmp_path / "changed", price=999)
    other = inventory_sessions(changed, changed_saved["id"])
    assert other["sessions"] == result["sessions"]
    assert other["counts"] == result["counts"]
    assert other["source"]["sha256"] != result["source"]["sha256"]


def test_inventory_checks_minimums_and_source_integrity(tmp_path, monkeypatch):
    source, saved = save_source(tmp_path)
    with pytest.raises(ValueError, match="at least 4"):
        inventory_sessions(source, saved["id"], minimum_sessions=4)
    with pytest.raises(ValueError, match="positive integer"):
        inventory_sessions(source, saved["id"], minimum_sessions=True)
    with pytest.raises(DatasetReadError, match="not found"):
        inventory_sessions(source, "missing")
    original = source.iter_csv

    def corrupt(dataset_id):
        yield from original(dataset_id)
        yield b"\n"

    monkeypatch.setattr(source, "iter_csv", corrupt)
    with pytest.raises(DatasetReadError, match="bytes"):
        inventory_sessions(source, saved["id"])


def test_normal_readers_select_same_whole_session_and_different_calendar_day(tmp_path):
    source, saved = save_source(tmp_path)
    selected = SessionDateRange.parse("2026-01-05", "2026-01-05")
    expected = ["2026-01-04T23:01:00+00:00", "2026-01-05T15:00:00+00:00"]
    with read_selected_bars(source, saved["id"], selected) as result:
        assert [bar.timestamp_utc.isoformat() for bar in result.bars] == expected
    prepared = prepare_data(source, saved["id"], selected, tmp_path / "session-bars.bin")
    with prepared.selected() as result:
        assert [bar.timestamp_utc.isoformat() for bar in result.bars] == expected
    with read_selected_bars(source, saved["id"], DateRange.parse("2026-01-05", "2026-01-05")) as result:
        assert [bar.timestamp_utc.isoformat() for bar in result.bars] == [
            "2026-01-05T15:00:00+00:00", "2026-01-05T23:01:00+00:00"]

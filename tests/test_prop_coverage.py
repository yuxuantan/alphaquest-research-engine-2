"""Expected schedules are independent of missing observations and trading activity."""

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import json
import tracemalloc

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.prop.coverage import SourceSessionProfile, build_calendar, profiles, scan_source
from alphaquest.prop.runs import PropRunStore
from alphaquest.prop.rules import get_profile
from review_execution import ScheduledStrategy
from test_backtest_api import run_fixture
from test_prop_api import setup_body, check
from test_prop_results_api import run
from test_prop_sessions import bars_at, save_run


def fixture_profile(**changes):
    values = dict(id="fixture", version="1.0.0", name="Explicit synthetic five-minute export", calendar="weekday_approximation",
                  window="custom", bar_interval_seconds=300, first_bar_time=time(5), last_bar_time=time(5, 30))
    values.update(changes)
    return SourceSessionProfile(**values)


def assign(client, source, profile=None, preset=None):
    response = client.put(f"/api/prop-simulations/sources/{source['id']}/session-profile",
                          json={"preset_id": preset} if preset else {"custom": (profile or fixture_profile()).to_dict()})
    assert response.status_code == 200, response.text
    return response.json()


def inspect(client, source, **params):
    response = client.get(f"/api/prop-simulations/sources/{source['id']}/coverage", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def automatic_body(client, source, coverage):
    body = setup_body(client, source)
    del body["calendar"]
    body.update(source_session_profile_sha256=coverage["profile_sha256"],
                account_start_utc=coverage["account_start_utc"], end_utc=coverage["end_utc"])
    return body


def selected_record(start, end, **selection):
    return {"run_metadata": {"selection": {"source_timezone": "America/New_York", "start_utc": start, "end_utc": end, **selection}}}


def test_pinned_market_model_holidays_early_closes_break_history_and_dst():
    policy = get_profile().session
    cash = profiles()[0]
    ordinary = build_calendar(cash, selected_record("2026-01-05T14:31:00Z", "2026-01-05T21:00:00Z"), policy, "test-tz")
    assert ordinary.days[0].windows[0].bar_count == 390
    assert ordinary.days[0].windows[0].first_utc.hour == 14
    holiday = build_calendar(cash, selected_record("2026-12-24T14:31:00Z", "2026-12-26T16:00:00Z"), policy, "test-tz")
    assert holiday.days[0].close_time == time(13)  # pinned schedule model, not a claim about a live exchange notice
    assert holiday.days[1].status == holiday.days[2].status == "closed"
    assert holiday.days[0].windows[0].bar_count == 210
    spring = build_calendar(cash, selected_record("2026-03-06T14:31:00Z", "2026-03-09T20:00:00Z"), policy, "test-tz")
    assert spring.days[0].windows[0].first_utc.hour == 14
    assert spring.days[-1].windows[0].first_utc.hour == 13
    overnight = profiles()[2]
    sunday = build_calendar(overnight, selected_record("2026-03-08T22:01:00Z", "2026-03-09T20:59:00Z"), policy, "test-tz")
    assert len(sunday.days) == 1 and sunday.days[0].trading_date == date(2026, 3, 9)
    assert sunday.days[0].windows[0].bar_count == 1379
    old = build_calendar(overnight, selected_record("2021-06-24T22:01:00Z", "2021-06-28T20:59:00Z"), policy, "test-tz")
    assert len(old.days[0].windows) == 2 and len(old.days[-1].windows) == 1
    assert "5.5.0" in ordinary.coverage_assumption and cash.sha256 in ordinary.coverage_assumption
    with pytest.raises(ValueError, match="2013"):
        build_calendar(cash, selected_record("2027-01-04T14:31:00Z", "2027-01-04T21:00:00Z"), policy, "test-tz")


def test_complete_coverage_save_run_download_restart_and_source_preservation(tmp_path):
    db = tmp_path / "datasets.sqlite3"
    with TestClient(create_app(db)) as client:
        _, source = run_fixture(client)
        folder = client.app.state.runs.root / source["id"]
        before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
        initial = inspect(client, source)
        assert initial["status"] == "profile_required" and initial["source"]["suggested_interval_seconds"] == 300
        assign(client, source)
        coverage = inspect(client, source)
        assert coverage["status"] == "compatible"
        assert coverage["coverage"]["summary"]["covered_sessions"] == 1
        assert coverage["coverage"]["sessions"][0]["expected_bars"] == 7
        response = client.post("/api/prop-simulations/setups", json=automatic_body(client, source, coverage))
        assert response.status_code == 201, response.text
        setup = response.json()
        assert check(client, setup)["status"] == "compatible"
        result = run(client, setup)
        assert result["summary"]["balance"] == "50026"
        for kind, identifier in (("setups", setup["id"]), ("results", result["id"])):
            exported = client.get(f"/api/prop-simulations/{kind}/{identifier}/exports/coverage.json").json()
            assert exported["source"]["report_sha256"] == coverage["source"]["report_sha256"]
            assert exported["coverage"]["calendar_sha256"] == setup["resolved"]["config"]["calendar_sha256"]
        assert all((folder / name).read_bytes() == content for name, content in before.items())
        assign(client, source, fixture_profile(last_bar_time=time(5, 35)))
        assert inspect(client, source)["status"] == "rejected"
        assert client.get(f"/api/prop-simulations/setups/{setup['id']}/coverage").json()["status"] == "compatible"
    with TestClient(create_app(db)) as client:
        assert inspect(client, source)["profile"]["last_bar_time"] == "05:35:00"
        assert client.get(f"/api/prop-simulations/results/{result['id']}").json() == result


@pytest.mark.parametrize("missing", [0, 3, 6])
def test_missing_and_partial_bars_never_become_zero_trading(tmp_path, missing):
    stamps = [datetime(2026, 1, 5, 10, tzinfo=timezone.utc) + timedelta(minutes=5*i) for i in range(7) if i != missing]
    _, source, _ = save_run(tmp_path, bars_at(stamps), ScheduledStrategy({}, {}))
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        assign(client, source)
        cov = inspect(client, source)
        assert cov["status"] == "rejected"
        row = cov["coverage"]["sessions"][0]
        assert row["missing_bars"] == 1 and row["zero_trade"] is False
        assert row["partial_boundary"] == (missing != 3)
        response = client.post("/api/prop-simulations/setups", json=automatic_body(client, source, cov))
        assert response.status_code == 422
        assert client.get("/api/prop-simulations/setups", params={"source_backtest_id": source["id"]}).json()["total"] == 0


def test_whole_missing_session_and_true_zero_trade_sessions(tmp_path):
    stamps = [datetime(2026, 1, day, 10, tzinfo=timezone.utc) + timedelta(minutes=5*i) for day in (5, 7) for i in range(7)]
    _, source, _ = save_run(tmp_path, bars_at(stamps), ScheduledStrategy({}, {}))
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        assign(client, source)
        cov = inspect(client, source)
        assert cov["coverage"]["summary"]["zero_trade_sessions"] == 2
        assert cov["coverage"]["summary"]["missing_bars"] == 7
        assert cov["coverage"]["sessions"][1]["status"] == "missing"
        page = inspect(client, source, offset=1, limit=1)["coverage"]
        assert len(page["sessions"]) == 1 and page["total"] == 3


def test_requested_empty_prefix_suffix_dates_are_preserved():
    record = selected_record("2026-01-06T14:31:00Z", "2026-01-06T21:00:00Z", from_date="2026-01-05", to_date="2026-01-07")
    calendar = build_calendar(profiles()[0], record, get_profile().session, "test-tz")
    assert [d.trading_date for d in calendar.days] == [date(2026, 1, d) for d in (5, 6, 7)]


def test_profile_race_and_source_change_reject_execution(tmp_path):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        _, source = run_fixture(client)
        assign(client, source)
        cov = inspect(client, source)
        body = automatic_body(client, source, cov)
        assign(client, source, fixture_profile(name="Changed declaration"))
        assert client.post("/api/prop-simulations/setups", json=body).status_code == 422
        body = automatic_body(client, source, inspect(client, source))
        setup = client.post("/api/prop-simulations/setups", json=body).json()
        check(client, setup)
        path = client.app.state.runs.root / source["id"] / "report.json"
        path.write_text(json.dumps(json.loads(path.read_text())))
        assert check(client, setup)["status"] == "rejected"
        assert client.post(f"/api/prop-simulations/setups/{setup['id']}/run").status_code == 422
        assert inspect(client, source)["source"]["report_sha256"] != cov["source"]["report_sha256"]


@pytest.mark.parametrize("change", [{"bar_interval_seconds": True}, {"bar_interval_seconds": 0},
                                  {"last_bar_time": time(5, 31)}, {"first_bar_time": time(17, 30)},
                                  {"timezone": "UTC"}, {"version": "2"}])
def test_invalid_profiles_are_strict(change):
    with pytest.raises(ValueError): fixture_profile(**change)


def test_off_grid_observation_is_not_a_replacement_for_a_missing_bar(tmp_path):
    stamps = [datetime(2026, 1, 5, 10, tzinfo=timezone.utc) + timedelta(minutes=5*i) for i in range(7)]
    stamps[3] += timedelta(seconds=1)
    _, source, _ = save_run(tmp_path, bars_at(stamps), ScheduledStrategy())
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        assign(client, source)
        coverage = inspect(client, source)
        assert coverage["status"] == "rejected"
        row = coverage["coverage"]["sessions"][0]
        assert (row["missing_bars"], row["unexpected_bars"], row["off_grid_bars"]) == (1, 1, 1)
        assert row["zero_trade"] is False


def test_scan_memory_is_bounded_and_cache_is_report_bound(tmp_path):
    # The native completed report exists before measurement. The scanner must
    # neither materialize its equity array nor retain one Python row per bar.
    start = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    stamps = [start + timedelta(seconds=i) for i in range(12000)]
    runs, source, _ = save_run(tmp_path, bars_at(stamps), ScheduledStrategy())
    store = PropRunStore(tmp_path)
    tracemalloc.start()
    try:
        scan = scan_source(store, runs, source, get_profile().session)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 6_000_000
    assert scan["bar_count"] == 12000
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM prop_coverage_segments").fetchone()[0] == 1
    assert scan_source(store, runs, source, get_profile().session) == scan

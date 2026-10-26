"""Saved-artifact integration and independent adapter arithmetic expectations."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import io
import json
from pathlib import Path
import tracemalloc
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from alphaquest.backtest_runs import RunStore
from alphaquest.execution import EquityPoint, execute
from alphaquest.prop import get_profile, resolve_simulation
from alphaquest.prop._report_reader import InputError, ReportReader
from alphaquest.prop.calendar import CalendarDay, DataWindow, SessionCalendar, local_utc
from alphaquest.prop.sessions import InstrumentDeclaration, prepare_backtest, scale_money
from alphaquest.prop.types import MonteCarloConfig, SimulationConfig, SizingConfig, UserFees
from alphaquest.reporting import generate_report, json_value
from alphaquest.strategy import CloseIntent, EntryIntent, ExecutionConfig
from review_execution import ScheduledStrategy
from test_execution import bar


D = Decimal
PROFILE = get_profile()
SETTINGS = ExecutionConfig(D("10000"), D(".25"), D("10"), 1, D("1"))
DECLARATION = InstrumentDeclaration("SYNTHETIC", "USD", D(".25"), D("10"), D("1"),
                                    "https://example.com/explicit-synthetic-rule-unit", "Explicit synthetic currency/instrument fixture, not inferred")


def bars_at(stamps, prices=None):
    prices = prices or ["100"] * len(stamps)
    return [replace(bar(i + 1, prices[i]), timestamp_utc=stamp) for i, stamp in enumerate(stamps)]


def save_run(tmp_path, bars=None, strategy=None, *, assumption="same_close_full_fill", settings=SETTINGS):
    bars = bars or [bar(1, "100"), bar(2, "100.5"), bar(3, "102")]
    strategy = strategy or ScheduledStrategy({1: EntryIntent(2, "entry")}, {len(bars): CloseIntent("exit")})
    run_id = uuid4().hex
    store = RunStore(tmp_path)
    dataset = {"id": "saved-dataset", "name": "fixture", "sha256": "3" * 64, "row_count": len(bars),
               "source_timezone": "UTC", "symbol": "SYNTHETIC", "instrument_settings": {"tick_size": ".25", "point_value": "10"}}
    selection = {"from_date": None, "to_date": None, "source_timezone": "UTC", "warmup": "none",
                 "row_count": len(bars), "start_utc": json_value(bars[0].timestamp_utc), "end_utc": json_value(bars[-1].timestamp_utc),
                 "first_source_bar_number": 1, "last_source_bar_number": len(bars)}
    metadata = {"dataset": dataset, "strategy": {"id": "fixture_strategy", "source_sha256": "2" * 64,
                "parameters": {"contracts": 2, "extra": {"preserved": True}}}, "selection": selection,
                "instrument_overrides": {}}
    output = tmp_path / f"staging-{run_id}"
    manifest = generate_report(execute(iter(bars), strategy, settings), output, settings, metadata=metadata,
                               expected_bar_count=len(bars), execution_assumption=assumption)
    record = store.complete(run_id, output, manifest)
    return store, record, bars


def calendar_for(bars):
    zone = ZoneInfo(PROFILE.session.timezone)
    groups = {}
    for item in bars:
        local = item.timestamp_utc.astimezone(zone)
        label = local.date() + timedelta(days=1) if local.time() >= time(18) else local.date()
        groups.setdefault(label, []).append(item.timestamp_utc)
    first, last = min(groups), max(groups)
    days = []
    for delta in range((last - first).days + 1):
        day = first + timedelta(days=delta)
        if day in groups:
            days.append(CalendarDay(day, "covered", (DataWindow(min(groups[day]), max(groups[day]), 60),)))
        else:
            days.append(CalendarDay(day, "closed" if day.weekday() >= 5 else "missing"))
    return SessionCalendar("fixture-calendar", PROFILE.session, "declared-test-tzdb", "explicit", "Complete fixture windows", tuple(days))


def resolved(record, calendar, **changes):
    args = dict(source_backtest_id=record["id"], phase="evaluation", analysis="historical", observation_mode="bar_close",
                account_start_utc=calendar.bounds(calendar.days[0])[0], end_utc=calendar.bounds(calendar.days[-1])[2],
                instrument=DECLARATION.symbol, currency="USD", contract_limit_weight=D("1"),
                contract_limit_source_url=DECLARATION.contract_limit_source_url, quantity=2, calendar_id=calendar.id,
                calendar_sha256=calendar.sha256, timezone_data_version=calendar.timezone_data_version,
                coverage_assumption=calendar.coverage_assumption, calendar_mode=calendar.mode,
                fees=UserFees("USD", attempt_fee=D("0")))
    args.update(changes)
    return resolve_simulation(SimulationConfig(**args), PROFILE)


def test_both_streams_preserve_costs_marks_and_source_provenance(tmp_path):
    store, record, bars = save_run(tmp_path)
    calendar = calendar_for(bars)
    before = {name: (store.root / record["id"] / name).read_bytes() for name in ("report.json", "trades.csv", "equity.csv")}
    with store.connect() as db:
        catalog_before = db.execute("SELECT manifest FROM runs").fetchone()[0]
    with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION) as source:
        session, = list(source.sessions())
        assert (session.bar_count, session.trade_count, session.net_pnl) == (3, 1, D("26"))
        marks = list(source.observations(session.trading_date))
        assert [m.equity_change for m in marks] == list(map(D, ("-7", "3", "26")))
        assert [m.realized_net_pnl for m in marks] == list(map(D, ("-2", "-2", "26")))
        assert [m.unrealized_pnl for m in marks] == list(map(D, ("-5", "5", "0")))
        assert [m.entry_commission for m in marks] == [D("2"), D("0"), D("0")]
        assert [m.exit_commission for m in marks] == [D("0"), D("0"), D("2")]
        assert [m.position_contracts for m in marks] == [2, 2, 0]
        closes = list(source.observations(session.trading_date, mode="trade_close"))
        assert len(closes) == 1 and closes[0].equity_change == D("26")
        trade, = source.trades()
        assert (trade.gross_pnl, trade.total_commissions, trade.slippage_cost, trade.net_pnl) == tuple(map(D, ("30", "4", "10", "26")))
        snapshot = source.snapshot
        assert len(snapshot.sha256) == 64
        assert type(snapshot).from_dict(snapshot.to_dict()) == snapshot
        metadata = json.loads(snapshot.manifest_json)["run_metadata"]
        assert metadata == record["run_metadata"]
        assert snapshot.source_contracts == 2 and snapshot.observed_bar_count == 3
        assert snapshot.instrument.basis == DECLARATION.basis
        assert all(not hasattr(m, "mae") for m in marks)
        for artifact in snapshot.artifacts:
            assert artifact.sha256 == sha256(before[artifact.name]).hexdigest()
            assert artifact.byte_count == len(before[artifact.name])
        assert json.loads(snapshot.calendar_json)["resolved_boundaries"]
        assert SessionCalendar.from_json(snapshot.calendar_json) == calendar
        with pytest.raises(FrozenInstanceError):
            snapshot.source_contracts = 100
    assert all((store.root / record["id"] / name).read_bytes() == value for name, value in before.items())
    with store.connect() as db:
        assert db.execute("SELECT manifest FROM runs").fetchone()[0] == catalog_before
    with pytest.raises(InputError, match="closed"):
        list(source.sessions())


def test_exact_quantity_scaling_preserves_original_quantity_and_no_second_cost(tmp_path):
    store, record, bars = save_run(tmp_path)
    calendar = calendar_for(bars)
    config = resolved(record, calendar, quantity=1)
    with localcontext() as ctx:
        ctx.prec = 2
        with prepare_backtest(store, config, calendar, DECLARATION) as source:
            session, = source.sessions()
            marks = list(source.observations(session.trading_date))
            assert [m.equity_change for m in marks] == list(map(D, ("-3.5", "1.5", "13")))
            assert [m.source_equity_change for m in marks] == list(map(D, ("-7", "3", "26")))
            trade, = source.trades()
            assert trade.contracts == 1 and trade.source.contracts == 2
            assert (trade.gross_pnl, trade.total_commissions, trade.slippage_cost, trade.net_pnl) == tuple(map(D, ("15", "2", "5", "13")))
            assert session.net_pnl == D("13")
            assert marks[-1].source_equity == D("10026")


def test_grid_quantities_are_validated_before_exposing_streams(tmp_path):
    store, record, bars = save_run(tmp_path)
    calendar = calendar_for(bars)
    config = resolved(record, calendar, analysis="monte_carlo", monte_carlo=MonteCarloConfig(100, 42),
                      sizing=SizingConfig((1, 2, 4)))
    with prepare_backtest(store, config, calendar, DECLARATION) as source:
        assert [next(source.trades(quantity=q)).net_pnl for q in (1, 2, 4)] == list(map(D, ("13", "26", "52")))
        session, = source.sessions(quantity=4)
        assert session.net_pnl == 52
        assert list(source.observations(session.trading_date, quantity=1))[-1].equity_change == 13
        for invalid in (True, 0, 3):
            with pytest.raises(InputError):
                list(source.trades(quantity=invalid))
        with pytest.raises(InputError, match="Unknown trading_date"):
            list(source.observations(date(2020, 1, 1)))


def test_multiple_trades_are_relative_to_their_own_baselines(tmp_path):
    bars = [bar(i + 1, price) for i, price in enumerate(("100", "102", "100", "99"))]
    strategy = ScheduledStrategy({1: EntryIntent(2, "first"), 3: EntryIntent(2, "second")}, {2: CloseIntent("one"), 4: CloseIntent("two")})
    store, record, bars = save_run(tmp_path, bars, strategy)
    calendar = calendar_for(bars)
    with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION) as source:
        session, = source.sessions()
        closes = list(source.observations(session.trading_date, mode="trade_close"))
        assert [m.equity_change for m in closes] == [D("26"), D("-34")]
        assert closes[1].source_equity == D("9992")
        assert session.net_pnl == D("-8")


def test_zero_trade_sessions_cover_entire_source_period_and_flat_marks_are_zero(tmp_path):
    stamps = [datetime(2026, 1, day, 14, tzinfo=timezone.utc) + timedelta(minutes=i)
              for day in (5, 6, 7) for i in range(3)]
    bars = bars_at(stamps)
    strategy = ScheduledStrategy({4: EntryIntent(2, "entry")}, {6: CloseIntent("exit")})
    store, record, bars = save_run(tmp_path, bars, strategy)
    calendar = calendar_for(bars)
    with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION) as source:
        sessions = list(source.sessions())
        assert [s.trade_count for s in sessions] == [0, 1, 0]
        assert [s.bar_count for s in sessions] == [3, 3, 3]
        assert list(source.observations(sessions[0].trading_date, mode="trade_close")) == []
        flat = list(source.observations(sessions[-1].trading_date))
        assert all(m.trade_number is None and m.equity_change == 0 and m.contracts == 0 for m in flat)


def test_no_trades_has_no_invented_source_size_or_trades(tmp_path):
    store, record, bars = save_run(tmp_path, strategy=ScheduledStrategy())
    calendar = calendar_for(bars)
    with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION) as source:
        assert source.snapshot.source_contracts is None
        session, = source.sessions()
        assert session.trade_count == 0 and session.net_pnl == 0
        assert list(source.trades()) == []
        assert len(list(source.observations(session.trading_date))) == 3


@pytest.mark.parametrize("case", ["missing_day", "missing_bar", "partial_first", "unknown"])
def test_missing_coverage_is_never_converted_to_zero(case, tmp_path):
    if case == "missing_day":
        bars = bars_at([datetime(2026, 1, day, 14, tzinfo=timezone.utc) for day in (5, 7)])
    elif case == "missing_bar":
        bars = bars_at([datetime(2026, 1, 5, 14, minute, tzinfo=timezone.utc) for minute in (0, 2)])
    else:
        bars = [bar(1), bar(2), bar(3)]
    store, record, bars = save_run(tmp_path, bars, ScheduledStrategy())
    calendar = calendar_for(bars)
    if case == "partial_first":
        day = calendar.days[0]
        window = replace(day.windows[0], first_utc=day.windows[0].first_utc - timedelta(minutes=1))
        calendar = replace(calendar, days=(replace(day, windows=(window,)),))
    elif case == "unknown":
        calendar = replace(calendar, days=(replace(calendar.days[0], status="missing", windows=()),))
    with pytest.raises(InputError, match="coverage"):
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION):
            pytest.fail("Invalid source was exposed")


def test_sunday_evening_is_monday_and_dst_uses_local_session_boundaries(tmp_path):
    zone = ZoneInfo("America/New_York")
    stamps = [datetime(2026, 3, 6, 9, tzinfo=zone).astimezone(timezone.utc),
              datetime(2026, 3, 8, 20, tzinfo=zone).astimezone(timezone.utc)]
    store, record, bars = save_run(tmp_path, bars_at(stamps), ScheduledStrategy())
    calendar = calendar_for(bars)
    with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION) as source:
        sessions = list(source.sessions())
        assert [s.trading_date for s in sessions] == [date(2026, 3, day) for day in (6, 7, 8, 9)]
        assert [s.status for s in sessions] == ["covered", "closed", "closed", "covered"]
        assert sessions[0].open_utc.hour == 23 and sessions[-1].open_utc.hour == 22
        assert len(list(source.observations(date(2026, 3, 9)))) == 1
        assert list(source.observations(date(2026, 3, 8))) == []


def test_early_close_and_multiple_declared_data_windows(tmp_path):
    stamps = [datetime(2026, 1, 5, hour, tzinfo=timezone.utc) for hour in (14, 17)]
    store, record, bars = save_run(tmp_path, bars_at(stamps), ScheduledStrategy())
    calendar = calendar_for(bars)
    windows = tuple(DataWindow(stamp, stamp, 60) for stamp in stamps)
    day = replace(calendar.days[0], windows=windows, close_time=time(13))
    calendar = replace(calendar, days=(day,))
    with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION) as source:
        session, = source.sessions()
        assert session.close_utc.hour == 18 and session.bar_count == 2


def test_weekday_approximation_is_explicit_and_bound_to_the_request(tmp_path):
    store, record, bars = save_run(tmp_path, strategy=ScheduledStrategy())
    calendar = replace(calendar_for(bars), mode="weekday_approximation")
    config = resolved(record, calendar)
    with prepare_backtest(store, config, calendar, DECLARATION) as source:
        assert json.loads(source.snapshot.calendar_json)["mode"] == "weekday_approximation"
    with pytest.raises(InputError, match="Calendar does not match"):
        with prepare_backtest(store, config, replace(calendar, coverage_assumption="different assumption"), DECLARATION):
            pass


@pytest.mark.parametrize("day,clock", [(date(2026, 3, 8), time(2, 30)), (date(2026, 11, 1), time(1, 30))])
def test_ambiguous_and_nonexistent_local_boundaries_are_rejected(day, clock):
    with pytest.raises(ValueError, match="Ambiguous or nonexistent"):
        local_utc(day, clock, ZoneInfo("America/New_York"))


def test_overnight_exposure_and_maintenance_break_are_rejected(tmp_path):
    bars = bars_at([datetime(2026, 1, 5, 21, 59, tzinfo=timezone.utc), datetime(2026, 1, 5, 23, 1, tzinfo=timezone.utc)])
    store, record, bars = save_run(tmp_path, bars)
    calendar = calendar_for(bars)
    with pytest.raises(InputError, match="spans prop-session"):
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION):
            pass
    # The calendar itself refuses a declared window inside the maintenance break.
    invalid = DataWindow(datetime(2026, 1, 5, 22, tzinfo=timezone.utc), datetime(2026, 1, 5, 22, tzinfo=timezone.utc), 60)
    with pytest.raises(ValueError, match="exceeds its prop session"):
        replace(calendar, days=(replace(calendar.days[0], windows=(invalid,)), calendar.days[1]))


def test_next_open_containing_bar_cannot_cross_session_open(tmp_path):
    start = datetime(2026, 1, 5, 23, tzinfo=timezone.utc)
    bars = bars_at([start + timedelta(minutes=i) for i in range(3)])
    # Test-only source marker: a containing-bar label at the session open has
    # no justified Open fill on the new session side of that boundary.
    store, record, bars = save_run(tmp_path, bars, assumption="next_open_market_next_bar_bracket_stop_first")
    calendar = calendar_for(bars)
    with pytest.raises(InputError, match="containing-bar"):
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION):
            pass


def test_valid_next_open_stream_and_source_parameters_remain_unchanged(tmp_path):
    strategy = ScheduledStrategy({1: EntryIntent(2, "next", timing="next_open")}, {3: CloseIntent("exit")})
    store, record, bars = save_run(tmp_path, strategy=strategy, assumption="next_open_market_next_bar_bracket_stop_first")
    calendar = calendar_for(bars)
    with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION) as source:
        trade, = source.trades()
        assert trade.source.entry_bar_number == 2
        assert json.loads(source.snapshot.manifest_json)["execution_assumption"] == "next_open_market_next_bar_bracket_stop_first"


def test_variable_quantities_are_rejected_in_both_modes(tmp_path):
    bars = [bar(i + 1) for i in range(4)]
    strategy = ScheduledStrategy({1: EntryIntent(2, "first"), 3: EntryIntent(1, "second")}, {2: CloseIntent("one"), 4: CloseIntent("two")})
    store, record, bars = save_run(tmp_path, bars, strategy)
    calendar = calendar_for(bars)
    for mode in ("trade_close", "bar_close"):
        with pytest.raises(InputError, match="Variable source quantities"):
            with prepare_backtest(store, resolved(record, calendar, observation_mode=mode), calendar, DECLARATION):
                pass


@pytest.mark.parametrize("change", [{"symbol": "NQ"}, {"currency": "EUR"}, {"point_value": D("20")}, {"tick_size": D(".5")}, {"contract_limit_weight": D(".1")}])
def test_instrument_and_currency_declarations_are_not_inferred_or_overridden(change, tmp_path):
    store, record, bars = save_run(tmp_path)
    calendar = calendar_for(bars)
    with pytest.raises(InputError, match="declar|Declared"):
        with prepare_backtest(store, resolved(record, calendar), calendar, replace(DECLARATION, **change)):
            pass


@pytest.mark.parametrize("artifact", ["trades.csv", "equity.csv", "report.json"])
def test_corrupted_artifacts_never_publish_an_input_and_cleanup(artifact, tmp_path):
    store, record, bars = save_run(tmp_path)
    path = store.root / record["id"] / artifact
    if artifact == "report.json":
        path.write_bytes(path.read_bytes()[:-5])
    else:
        path.write_text(path.read_text().replace("26.00", "27.00"))
    calendar = calendar_for(bars)
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    with pytest.raises(InputError):
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION, temporary_parent=temporary):
            pytest.fail("Corrupted input exposed")
    assert list(temporary.iterdir()) == []


def test_unknown_run_missing_artifact_and_traversal_are_rejected(tmp_path):
    store, record, bars = save_run(tmp_path)
    calendar = calendar_for(bars)
    for run_id in ("../outside", "f" * 32):
        with pytest.raises(InputError):
            with prepare_backtest(store, resolved({"id": run_id}, calendar), calendar, DECLARATION):
                pass
    (store.root / record["id"] / "trades.csv").unlink()
    with pytest.raises(InputError, match="Missing"):
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION):
            pass


def test_consumer_errors_are_preserved_and_corrupt_catalog_errors_are_inputs(tmp_path):
    store, record, bars = save_run(tmp_path)
    calendar = calendar_for(bars)
    temporary = tmp_path / "cleanup"
    temporary.mkdir()
    consumer_error = ValueError("caller's account engine failed")
    with pytest.raises(ValueError) as captured:
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION, temporary_parent=temporary):
            raise consumer_error
    assert captured.value is consumer_error
    assert list(temporary.iterdir()) == []
    with store.connect() as db:
        db.execute("UPDATE runs SET manifest=? WHERE id=?", ('{"truncated":', record["id"]))
    with pytest.raises(InputError, match="snapshot JSON"):
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION, temporary_parent=temporary):
            pass
    assert list(temporary.iterdir()) == []


def test_numeric_looking_dataset_identity_is_not_compared_as_money(tmp_path):
    store, record, bars = save_run(tmp_path)
    path = store.root / record["id"] / "report.json"
    report = json.loads(path.read_text())
    report["run_metadata"]["dataset"]["id"] = "0001"
    path.write_text(json.dumps(report))
    with store.connect() as db:
        catalog = json.loads(db.execute("SELECT manifest FROM runs WHERE id=?", (record["id"],)).fetchone()[0])
        catalog["run_metadata"]["dataset"]["id"] = "1"
        db.execute("UPDATE runs SET manifest=? WHERE id=?", (json.dumps(catalog), record["id"]))
    calendar = calendar_for(bars)
    with pytest.raises(InputError, match="metadata differs"):
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION):
            pass


@pytest.mark.parametrize("corruption", ["slippage", "price", "entry_cash", "selection"])
def test_balanced_summary_is_not_sufficient_evidence_of_valid_source_inputs(corruption, tmp_path):
    store, record, bars = save_run(tmp_path)
    path = store.root / record["id"] / "report.json"
    payload = json.loads(path.read_text())
    if corruption == "slippage":
        payload["trades"][0]["slippage_cost"] = "11"
        message = "slippage"
    elif corruption == "price":
        payload["trades"][0]["exit_fill_price"] = "1000"
        message = "preserved prices"
    elif corruption == "entry_cash":
        payload["equity"][1].update(cash_balance="9997", realized_net_pnl="-3", equity="9992")
        message = "cash/entry costs"
    else:
        payload["run_metadata"]["selection"]["start_utc"] = "2026-01-05T10:01:00Z"
        # Even when the matching catalog is edited, validate against actual marks.
        with store.connect() as db:
            catalog = json.loads(db.execute("SELECT manifest FROM runs WHERE id=?", (record["id"],)).fetchone()[0])
            catalog["run_metadata"] = payload["run_metadata"]
            db.execute("UPDATE runs SET manifest=? WHERE id=?", (json.dumps(catalog), record["id"]))
        message = "Selected source period"
    path.write_text(json.dumps(payload))
    calendar = calendar_for(bars)
    with pytest.raises(InputError, match=message):
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION):
            pass


def test_real_portal_run_uses_saved_instrument_defaults_and_selection(tmp_path):
    from fastapi.testclient import TestClient
    from alphaquest.app import create_app
    from test_backtest_api import run_fixture

    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        dataset, record = run_fixture(client)
        store = client.app.state.runs
        raw = json.loads((store.root / record["id"] / "report.json").read_text())
        stamps = [datetime.fromisoformat(point["timestamp_utc"]) for point in raw["equity"][1:]]
        calendar = calendar_for(bars_at(stamps))
        day = calendar.days[0]
        calendar = replace(calendar, days=(replace(day, windows=(replace(day.windows[0], bar_interval_seconds=300),)),))
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION) as source:
            captured = json.loads(source.snapshot.manifest_json)["run_metadata"]
            assert captured["dataset"]["id"] == dataset["id"]
            assert captured["dataset"]["instrument_settings"] == dataset["instrument_settings"]
            assert captured["selection"] == record["run_metadata"]["selection"]
            assert next(source.trades()).net_pnl == D("26")


def test_complete_adapter_memory_and_early_consumer_cleanup(tmp_path):
    # Retain fixture bars outside the memory measurement: the source is already
    # saved. The adapter must not materialize its 12,000-mark report array.
    stamps = []
    current = date(2026, 1, 5)
    while len(stamps) < 12000:
        if current.weekday() < 5:
            first = datetime.combine(current, time(14), timezone.utc)
            stamps.extend(first + timedelta(minutes=i) for i in range(400))
        current += timedelta(days=1)
    store, record, bars = save_run(tmp_path, bars_at(stamps), ScheduledStrategy())
    calendar = calendar_for(bars)
    temporary = tmp_path / "work"
    temporary.mkdir()
    tracemalloc.start()
    try:
        with prepare_backtest(store, resolved(record, calendar), calendar, DECLARATION, temporary_parent=temporary) as source:
            assert source.snapshot.observed_bar_count == 12000
            first = next(source.sessions())
            iterator = source.observations(first.trading_date)
            assert next(iterator).equity_change == 0
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 6_000_000
    assert list(temporary.iterdir()) == []


def test_exact_scaling_does_not_round_repeating_per_contract_quotients():
    with localcontext() as ctx:
        ctx.prec = 1
        assert scale_money(D("1"), 3, 3) == 1
        assert scale_money(D(".03"), 3, 1) == D(".01")
        assert scale_money(D("-7"), 2, 1) == D("-3.5")
        with pytest.raises(InputError, match="repeating"):
            scale_money(D("1"), 3, 1)


@pytest.mark.parametrize("content", [
    '{"trades":[],"equity":[]} trailing', '{"trades":[],"trades":[],"equity":[]}',
    '{"trades":[],"equity":[{"x":1,"x":2}]}', '{"equity":[],"trades":[]}',
    '{"trades":[],"equity":[NaN]}', '{"trades":[', '{"trades":[],"equity":[],"late":1}',
])
def test_stream_reader_rejects_malformed_duplicates_and_truncated_json(content):
    with pytest.raises(InputError):
        list(ReportReader(io.StringIO(content), chunk_size=7).records())


def test_stream_reader_handles_chunk_boundaries_and_bounds_single_records():
    text = '{"metadata":{"value":12345678901234567890,"text":"escaped\\\"string"},"trades":[],"equity":[{"bar_number":0}]}'
    for chunk in (1, 2, 7, 64):
        rows = list(ReportReader(io.StringIO(text), chunk_size=chunk).records())
        assert rows[0][1]["value"] == 12345678901234567890
        assert rows[-1] == ("equity", {"bar_number": 0})
    with pytest.raises(InputError, match="size limit"):
        list(ReportReader(io.StringIO('{"trades":[{"text":"' + "x" * 500 + '"}],"equity":[]}'), record_limit=100, chunk_size=16).records())


def test_reader_memory_is_bounded_by_record_size_not_array_length():
    class RepeatingStream:
        def __init__(self, count):
            self.count, self.started, self.finished = count, False, False

        def read(self, size):
            assert 0 < size <= 65536
            if not self.started:
                self.started = True
                return '{"trades":[],"equity":['
            if self.count:
                self.count -= 1
                return '{"bar_number":1}' + ("," if self.count else "")
            if not self.finished:
                self.finished = True
                return "]}"
            return ""

    tracemalloc.start()
    assert sum(1 for _ in ReportReader(RepeatingStream(30000)).records()) == 30000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 2_000_000

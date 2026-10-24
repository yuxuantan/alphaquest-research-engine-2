"""Hand-calculated drawdowns; full trade-close results, including old runs."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

import pytest

from alphaquest.drawdown import Drawdown
from alphaquest.execution import execute
from alphaquest.strategy import EntryIntent, CloseIntent
from alphaquest.reporting import generate_report
from alphaquest.backtest_runs import RunStore
from test_backtest_api import client, run_fixture
from test_reporting import CONFIG, events
from review_execution import fixtures, ScheduledStrategy
from test_execution import bar

D = Decimal
START = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
FIELDS = {"max_drawdown_amount", "max_drawdown_pct", "max_drawdown_duration_seconds"}


@pytest.mark.parametrize("points,end,amount,pct,seconds", [
    ([], 60, "0", "0", "0"),
    ([(10, "120"), (20, "90"), (60, "120")], 60, "30", "25", "3000"),
    ([(1, "50"), (2, "100"), (3, "1000"), (4, "900"), (5, "1000")], 5, "100", "50", "120"),
    ([(1, "80"), (2, "100"), (3, "200"), (4, "190"), (10, "200")], 10, "20", "20", "420"),
    ([(1, "100"), (10, "90"), (12, "100")], 14, "10", "10", "660"),
    ([(10, "110"), (20, "100")], 60, "10", "9.090909090909090909090909091", "3000"),
    ([(1, "-50")], 1, "150", "150", "60"),
])
def test_independently_calculated_peaks_recoveries_and_unrecovered_periods(points, end, amount, pct, seconds):
    tracker = Drawdown(D(100), START)
    for minute, equity in points:
        tracker.observe(START + timedelta(minutes=minute), D(equity))
    result = tracker.finish(START + timedelta(minutes=end))
    assert result == {"max_drawdown_amount": D(amount), "max_drawdown_pct": D(pct), "max_drawdown_duration_seconds": D(seconds)}


def test_decimal_amount_and_microsecond_duration_ignore_caller_precision():
    initial = D("100000000000000000000000000000.123456789123456789")
    low = D("100000000000000000000000000000.123456789123456788")
    with localcontext() as context:
        context.prec = 2
        tracker = Drawdown(initial, START)
        tracker.observe(START + timedelta(microseconds=1), low)
        result = tracker.finish(START + timedelta(microseconds=1234567))
        assert result["max_drawdown_amount"] == D("0.000000000000000001")
        assert result["max_drawdown_duration_seconds"] == D("1.234567")
        assert context.prec == 2


def test_final_bar_roundtrip_can_have_loss_with_zero_elapsed_duration(tmp_path):
    strategy = ScheduledStrategy({1: EntryIntent(2, "entry")}, finish=CloseIntent("end_of_data"))
    manifest = generate_report(execute([bar(1)], strategy, CONFIG), tmp_path / "report", CONFIG)
    assert manifest["summary"]["max_drawdown_amount"] == D(14)
    assert manifest["summary"]["max_drawdown_pct"] == D("0.14")
    assert manifest["summary"]["max_drawdown_duration_seconds"] == 0


def test_reporter_uses_closed_equity_after_costs_and_ignores_open_position_dips(tmp_path):
    winner = generate_report(events(), tmp_path / "winner", CONFIG)
    assert winner["summary"]["max_drawdown_amount"] == 0  # Entry equity dips to 9993, but trade wins.
    loser = generate_report(events(("100", "99", "99")), tmp_path / "loser", CONFIG)
    # 2 contracts * -1.5 filled points * 10 minus 4 fees = -34.
    assert loser["summary"]["max_drawdown_amount"] == D(34)
    assert loser["summary"]["max_drawdown_pct"] == D("0.34")
    assert loser["summary"]["max_drawdown_duration_seconds"] == D(120)
    assert loser["period_start_utc"] == START
    assert loser["period_end_utc"] == START + timedelta(minutes=2)
    saved = json.loads((tmp_path / "loser/report.json").read_text())
    assert saved["summary"]["max_drawdown_amount"] == "34.00"


def test_legacy_saved_reports_are_enriched_once_without_replaying_or_rewriting_artifacts(client, monkeypatch):
    case = next(c for c in fixtures() if c["id"] == "end_of_data")
    _, record = run_fixture(client, case)
    run_id = record["id"]
    runs = client.app.state.runs
    folder = runs.root / run_id
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    legacy = {**record, "summary": {k: v for k, v in record["summary"].items() if k not in FIELDS}}
    legacy.pop("period_start_utc")
    legacy.pop("period_end_utc")
    with runs.connect() as conn:
        conn.execute("UPDATE runs SET manifest=? WHERE id=?", (json.dumps(legacy), run_id))
    original = Path.read_text

    def no_array_loading(path, *args, **kwargs):
        if path.name == "report.json": pytest.fail("Legacy enrichment must stream")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", no_array_loading)
    response = client.get(f"/api/backtests/{run_id}")
    assert response.status_code == 200
    enriched = response.json()
    assert enriched["summary"]["max_drawdown_amount"] == "20.00"
    assert enriched["summary"]["max_drawdown_pct"] == "0.20"
    assert enriched["summary"]["max_drawdown_duration_seconds"] == "240"
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()} == before
    # A fresh store can serve both list and detail from the committed catalogue.
    monkeypatch.setattr("alphaquest.backtest_runs.saved_drawdown", lambda *args: pytest.fail("Must use durable enriched catalogue"))
    restarted = RunStore(runs.path.parent)
    assert restarted.get(run_id) == enriched
    assert restarted.list(0, 25)["items"] == [enriched]


def test_invalid_legacy_equity_is_not_cached_as_zero_drawdown(client):
    _, record = run_fixture(client)
    runs = client.app.state.runs
    record["summary"] = {k: v for k, v in record["summary"].items() if k not in FIELDS}
    with runs.connect() as conn:
        conn.execute("UPDATE runs SET manifest=? WHERE id=?", (json.dumps(record), record["id"]))
    (runs.root / record["id"] / "equity.csv").write_text("trade_number,exit_time_utc,net_pnl,equity\n0,,0,10000\n")
    with pytest.raises(ValueError, match="count does not match"):
        runs.get(record["id"])
    with runs.connect() as conn:
        persisted = json.loads(conn.execute("SELECT manifest FROM runs WHERE id=?", (record["id"],)).fetchone()[0])
    assert "max_drawdown_amount" not in persisted["summary"]

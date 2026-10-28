from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from threading import Event, get_ident
import time
from uuid import uuid4

from research_fixtures import ResearchClient as TestClient
from anyio.to_thread import current_default_thread_limiter
import pytest

from alphaquest.app import create_app
from alphaquest import backtest_api
from alphaquest.backtest_runs import RunStore
from alphaquest.strategies import consecutive_green_hold as sample
from review_execution import FIXTURES, fixtures
from review_reports import _equal_record
from research_fixtures import declaration, reserved_source


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        yield client


def save_fixture(client, case=None):
    case = case or fixtures()[0]
    response = client.post("/api/datasets", params={"filename": case["csv"], "name": case["id"],
                                                   "source_timezone": case["source_timezone"], **{k: case["execution_settings"][k] for k in ("tick_size", "point_value")}},
                           content=(FIXTURES / case["csv"]).read_bytes())
    assert response.status_code == 201, response.text
    return response.json()


def body(dataset_id, case=None):
    case = case or fixtures()[0]
    return {"reuse_results":False,"dataset_id": dataset_id, "strategy_id": "consecutive_green_hold",
            "strategy_parameters": deepcopy(case["strategy_parameters"]),
            "sample_split": declaration(dataset_id),
            "execution_settings": {k: v for k, v in case["execution_settings"].items() if k not in ("tick_size", "point_value")}}


def run_fixture(client, case=None, operation_id=None):
    dataset = save_fixture(client, case)
    response = client.post("/api/backtests", params={"progress_id": operation_id or str(uuid4())},
                           json={**body(dataset["id"], case),'report_detail':'full'})
    assert response.status_code == 201, response.text
    return dataset, response.json()


def test_strategy_registry_lists_script_owned_definitions_and_defaults(client):
    response = client.get("/api/strategies")
    assert response.status_code == 200
    strategies = response.json()
    assert {item["id"] for item in strategies} == {sample.STRATEGY_ID, "vwap_pullback_risk_sizing"}
    strategy = strategies[0]
    assert strategy["id"] == sample.STRATEGY_ID
    assert strategy["description"] == sample.DESCRIPTION
    assert strategy["source_sha256"] == hashlib.sha256(Path(sample.__file__).read_bytes()).hexdigest()
    definitions = {item["name"]: item for item in strategy["parameters"]}
    assert {name: item["default"] for name, item in definitions.items()} == asdict(sample.Parameters())
    assert all(item["minimum"] == 1 and item["description"] for item in definitions.values())


@pytest.mark.parametrize("case", fixtures(), ids=lambda case: case["id"])
def test_api_retrieves_exact_independently_reviewed_results_and_provenance(client, case):
    operation_id = str(uuid4())
    dataset, record = run_fixture(client, case, operation_id)
    run_id = record["id"]
    assert record["status"] == "complete"
    assert client.get(f"/api/backtests/{run_id}").json() == record
    assert "trades" not in record and "equity" not in record
    _equal_record(record["summary"], case["expected_summary"])
    assert record["execution_settings"] == case["execution_settings"]
    assert record["timestamp_convention"] == "bar_close"
    assert record["execution_assumption"] == "same_close_full_fill"
    provenance = record["run_metadata"]
    assert provenance["dataset"] == {key: dataset[key] for key in ("id", "name", "sha256", "source_timezone", "row_count", "instrument_settings")}
    assert provenance["strategy"]["parameters"] == case["strategy_parameters"]
    assert provenance["strategy"]["source_sha256"] == hashlib.sha256(Path(sample.__file__).read_bytes()).hexdigest()
    trades = client.get(f"/api/backtests/{run_id}/trades").json()
    assert trades["total"] == len(case["expected_trades"])
    for actual, expected in zip(trades["items"], case["expected_trades"], strict=True):
        _equal_record(actual, expected)
    equity = client.get(f"/api/backtests/{run_id}/equity").json()
    expected_equity = [{"trade_number": 0, "exit_time_utc": None, "net_pnl": "0",
                        "equity": case["execution_settings"]["initial_capital"]}] + [{
        "trade_number": trade["trade_number"], "exit_time_utc": trade["exit_time_utc"], "net_pnl": trade["net_pnl"],
        "equity": case["expected_equity"][trade["exit_bar_number"]]["equity"],
    } for trade in case["expected_trades"]]
    assert equity["total"] == len(expected_equity)
    for actual, expected in zip(equity["items"], expected_equity, strict=True):
        _equal_record(actual, expected)
    progress = client.get(f"/api/progress/{operation_id}").json()
    assert progress == {"stage": "done", "bars_processed": case["bar_count"],
                        "total_bars": case["bar_count"], "run_id": run_id}
    assert client.get(f"/api/datasets/{dataset['id']}").json() == dataset
    assert client.get(f"/api/datasets/{dataset['id']}/csv").content == reserved_source((FIXTURES / case["csv"]).read_bytes())[0]
    persisted = client.app.state.runs.root / run_id
    assert {p.name for p in persisted.iterdir()} == {"report.json", "trades.csv", "equity.csv", "intratrade_risk.csv", 'performance.json', 'market_benchmark.json', 'market_equity.csv'}
    stored_report = json.loads((persisted / "report.json").read_text())
    assert stored_report["summary"] == record["summary"]
    assert stored_report["trades"] == trades["items"]


@pytest.mark.parametrize("parameters", [
    {}, {"green_bar_count": 3, "hold_minutes": 20},
    {"green_bar_count": 3, "hold_minutes": 20, "contracts": 1, "extra": 1},
    {"green_bar_count": True, "hold_minutes": 20, "contracts": 1},
    {"green_bar_count": 3.0, "hold_minutes": 20, "contracts": 1},
    {"green_bar_count": "3", "hold_minutes": 20, "contracts": 1},
    {"green_bar_count": 0, "hold_minutes": 20, "contracts": 1},
    {"green_bar_count": 3, "hold_minutes": -1, "contracts": 1},
    {"green_bar_count": 3, "hold_minutes": 20, "contracts": False},
])
def test_strategy_parameters_are_explicit_and_script_validation_is_used(client, parameters):
    dataset = save_fixture(client)
    request = body(dataset["id"])
    request["strategy_parameters"] = parameters
    response = client.post("/api/backtests", json=request)
    assert response.status_code == 422, response.text
    assert client.get("/api/backtests").json()["total"] == 0


@pytest.mark.parametrize("field,value", [
    ("initial_capital", 10000), ("initial_capital", "0"), ("tick_size", 0.25), ("tick_size", "0"),
    ("point_value", "-10"), ("point_value", "NaN"), ("point_value", "Infinity"),
    ("commission_per_contract_per_side", "-1"), ("commission_per_contract_per_side", True),
    ("tick_size", "invalid"), ("slippage_ticks", True), ("slippage_ticks", 1.0), ("slippage_ticks", "1"),
    ("slippage_ticks", -1), ("extra", "1"),
])
def test_execution_settings_require_explicit_exact_values(client, field, value):
    dataset = save_fixture(client)
    request = body(dataset["id"])
    request["execution_settings"][field] = value
    assert client.post("/api/backtests", json=request).status_code == 422
    assert client.get("/api/backtests").json()["total"] == 0


@pytest.mark.parametrize("field", ["initial_capital", "slippage_ticks", "commission_per_contract_per_side"])
def test_missing_execution_setting_is_not_inferred_from_dataset(client, field):
    dataset = save_fixture(client)
    request = body(dataset["id"])
    del request["execution_settings"][field]
    assert client.post("/api/backtests", json=request).status_code == 422


def test_unknown_strategy_schema_missing_dataset_extra_top_level_and_origins(client):
    dataset = save_fixture(client)
    request = body(dataset["id"])
    for strategy in ("unregistered", "alphaquest.strategies.consecutive_green_hold", "../../script.py"):
        assert client.post("/api/backtests", json={**request, "strategy_id": strategy}).status_code == 422
    assert client.post("/api/backtests", json={**request, "dataset_id": "missing"}).status_code == 404
    assert client.post("/api/backtests", json={**request, "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10"}).status_code == 422
    assert client.post("/api/backtests", json=request, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get(f"/api/backtests/{uuid4()}").status_code == 404
    assert client.get(f"/api/backtests/{uuid4()}/trades").status_code == 404
    assert client.get(f"/api/backtests/{uuid4()}/equity").status_code == 404
    with client.app.state.store.connect() as conn:
        corrupt = {**dataset, "columns": ["datetime", "open", "high", "low", "close", "volume"]}
        conn.execute("UPDATE datasets SET metadata=? WHERE id=?", (json.dumps(corrupt), dataset["id"]))
    response = client.post("/api/backtests", json=request)
    assert response.status_code == 422 and "Unsupported dataset schema" in response.json()["detail"]


def test_live_progress_is_responsive_during_actual_replay_and_dataset_db_is_released(client, monkeypatch):
    dataset = save_fixture(client)
    original = sample.ConsecutiveGreenHold.on_bar
    entered, release = Event(), Event()
    operation_id = str(uuid4())
    loop_thread = []
    worker_thread = []

    async def event_loop_marker():
        loop_thread.append(get_ident())

    client.portal.call(event_loop_marker)

    def pause(self, bar, position):
        if bar.bar_number == 3:
            worker_thread.append(get_ident())
            entered.set()
            assert release.wait(5)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/api/backtests", params={"progress_id": operation_id}, json=body(dataset["id"]))
        try:
            assert entered.wait(5)
            before = time.monotonic()
            status = client.get(f"/api/progress/{operation_id}")
            assert time.monotonic() - before < 1
            assert status.headers["cache-control"] == "no-store"
            assert status.json()["stage"] == "replaying"
            assert status.json()["bars_processed"] == 2 and status.json()["total_bars"] == 7
            assert client.get("/api/backtests").json()["total"] == 0
            # Deleting the source during replay proves it is using the detached
            # snapshot; completion retains original provenance after deletion.
            assert client.delete(f"/api/datasets/{dataset['id']}").status_code == 204
        finally:
            release.set()
        response = pending.result(timeout=5)
    assert response.status_code == 201, response.text
    assert loop_thread and worker_thread and loop_thread[0] != worker_thread[0]
    assert response.json()["summary"]["total_net_pnl"] == "26.00"


@pytest.mark.parametrize("pause_stage", ["preparing", "saving_report", "saving_results"])
def test_preparation_and_saving_stages_are_visible_and_only_saved_runs_complete(client, monkeypatch, pause_stage):
    dataset = save_fixture(client)
    original_run = backtest_api.run_backtest
    entered, release = Event(), Event()
    operation_id = str(uuid4())

    def wrapped(*args, **kwargs):
        args = list(args)
        original_progress = args[-1]

        def progress(stage, processed, total):
            original_progress(stage, processed, total)
            if stage == pause_stage:
                entered.set()
                assert release.wait(5)

        args[-1] = progress
        return original_run(*args, **kwargs)

    monkeypatch.setattr(backtest_api, "run_backtest", wrapped)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/api/backtests", params={"progress_id": operation_id}, json=body(dataset["id"]))
        try:
            assert entered.wait(5)
            state = client.get(f"/api/progress/{operation_id}").json()
            assert state["stage"] == pause_stage
            assert state["bars_processed"] == (0 if pause_stage == "preparing" else 7)
            assert client.get(f"/api/backtests/{state['run_id']}").status_code == 404
            assert client.get("/api/backtests").json()["total"] == 0
        finally:
            release.set()
        response = pending.result(timeout=5)
    assert response.status_code == 201
    state = client.get(f"/api/progress/{operation_id}").json()
    assert state["stage"] == "done"
    assert (client.app.state.runs.root / state["run_id"] / "report.json").is_file()


def test_success_is_hidden_until_sqlite_index_transaction_commits(client, monkeypatch):
    dataset = save_fixture(client)
    original_rows = RunStore._rows
    entered, release = Event(), Event()
    operation_id = str(uuid4())

    def paused_rows(self, source, kind):
        if kind == "equity":
            entered.set()
            assert release.wait(5)
        yield from original_rows(self, source, kind)

    monkeypatch.setattr(RunStore, "_rows", paused_rows)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/api/backtests", params={"progress_id": operation_id}, json=body(dataset["id"]))
        try:
            assert entered.wait(5)
            progress = client.get(f"/api/progress/{operation_id}").json()
            assert progress["stage"] == "saving_results"
            assert client.get(f"/api/backtests/{progress['run_id']}").status_code == 404
            assert client.get("/api/backtests").json()["total"] == 0
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 201


@pytest.mark.parametrize("failure", ["replay", "index", "publish"])
def test_failed_runs_are_never_successful_or_persisted(client, monkeypatch, failure):
    dataset = save_fixture(client)
    if failure == "replay":
        def broken(*args):
            raise RuntimeError("test strategy failed")
        monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", broken)
    elif failure == "index":
        original_rows = RunStore._rows
        def broken_rows(self, source, kind):
            yield next(original_rows(self, source, kind))
            raise OSError("test index write failed")
        monkeypatch.setattr(RunStore, "_rows", broken_rows)
    else:
        original_rename = Path.rename
        def broken_rename(self, target):
            if target.parent == client.app.state.runs.root:
                raise OSError("test artifact publication failed")
            return original_rename(self, target)
        monkeypatch.setattr(Path, "rename", broken_rename)
    operation_id = str(uuid4())
    response = client.post("/api/backtests", params={"progress_id": operation_id}, json=body(dataset["id"]))
    assert response.status_code == 500
    progress = client.get(f"/api/progress/{operation_id}").json()
    assert progress["stage"] == "failed" and progress["error"]
    assert client.get(f"/api/backtests/{progress['run_id']}").status_code == 404
    assert client.get("/api/backtests").json()["total"] == 0
    assert list(client.app.state.runs.root.iterdir()) == []
    with client.app.state.runs.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM run_trades").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM run_equity").fetchone()[0] == 0


def test_completed_results_survive_restart_and_source_deletion(tmp_path):
    database = tmp_path / "datasets.sqlite3"
    operation_id = str(uuid4())
    with TestClient(create_app(database)) as first:
        dataset, record = run_fixture(first, operation_id=operation_id)
        run_id = record["id"]
        trades = first.get(f"/api/backtests/{run_id}/trades").json()
        equity = first.get(f"/api/backtests/{run_id}/equity").json()
        assert first.delete(f"/api/datasets/{dataset['id']}").status_code == 204
    with TestClient(create_app(database)) as restarted:
        assert restarted.get(f"/api/progress/{operation_id}").status_code == 404
        assert restarted.get(f"/api/backtests/{run_id}").json() == record
        assert restarted.get(f"/api/backtests/{run_id}/trades").json() == trades
        assert restarted.get(f"/api/backtests/{run_id}/equity").json() == equity
        assert restarted.get("/api/backtests").json()["items"] == [record]


def test_pagination_has_bounded_pages_and_isolated_run_ids(client):
    case = next(case for case in fixtures() if case["id"] == "no_pyramiding")
    dataset, first = run_fixture(client, case)
    second = client.post("/api/backtests", json=body(dataset["id"], case)).json()
    for run in (first, second):
        run_id = run["id"]
        pages = [client.get(f"/api/backtests/{run_id}/trades", params={"offset": i, "limit": 1}).json() for i in range(3)]
        assert [len(page["items"]) for page in pages] == [1, 1, 0]
        assert [page["items"][0]["trade_number"] for page in pages[:2]] == [1, 2]
        assert all(page["total"] == 2 for page in pages)
        equity = client.get(f"/api/backtests/{run_id}/equity", params={"offset": 1, "limit": 1}).json()
        assert equity["total"] == 3 and equity["items"][0]["trade_number"] == 1
    listed = client.get("/api/backtests", params={"limit": 1}).json()
    assert len(listed["items"]) == 1 and listed["total"] == 2
    for endpoint in ("/api/backtests", f"/api/backtests/{first['id']}/trades", f"/api/backtests/{first['id']}/equity"):
        for params in ({"limit": 0}, {"limit": 1001}, {"offset": -1}):
            assert client.get(endpoint, params=params).status_code == 422


def test_progress_id_reuse_and_missing_progress_are_explicit(client):
    operation_id = str(uuid4())
    dataset, record = run_fixture(client, operation_id=operation_id)
    response = client.post("/api/backtests", params={"progress_id": operation_id}, json=body(dataset["id"]))
    assert response.status_code == 409
    assert client.get("/api/backtests").json()["total"] == 1
    assert client.get(f"/api/progress/{operation_id}").json()["run_id"] == record["id"]
    assert client.get(f"/api/progress/{uuid4()}").status_code == 404


def test_large_results_use_bounded_pages_without_loading_report_arrays(client, monkeypatch):
    start = datetime(2026, 1, 5)
    lines = ["Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol"]
    for minute in range(2002):
        stamp = start + timedelta(minutes=minute)
        lines.append(stamp.strftime("%m/%d/%Y,%H:%M") + ",100,101,100,101,0,0,0")
    saved = client.post("/api/datasets", params={"filename": "many.csv", "name": "Many trades", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10"},
                        content=("\n".join(lines) + "\n").encode()).json()
    request = body(saved["id"])
    request["strategy_parameters"] = {"green_bar_count": 1, "hold_minutes": 1, "contracts": 1}
    request["execution_settings"]["slippage_ticks"] = 0
    request["execution_settings"]["commission_per_contract_per_side"] = "0"
    response = client.post("/api/backtests", json=request)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["summary"]["trades_taken"] == 1001
    original_read = Path.read_text

    def forbid_report_read(self, *args, **kwargs):
        if self.name == "report.json":
            pytest.fail("Paged retrieval must not load full report arrays")
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_report_read)
    endpoint = f"/api/backtests/{record['id']}"
    first = client.get(endpoint + "/trades").json()
    assert len(first["items"]) == 100 and first["total"] == 1001
    tail = client.get(endpoint + "/trades", params={"offset": 1000, "limit": 1000}).json()
    assert len(tail["items"]) == 1 and tail["items"][0]["trade_number"] == 1001
    equity_tail = client.get(endpoint + "/equity", params={"offset": 1000, "limit": 1000}).json()
    assert len(equity_tail["items"]) == 2 and equity_tail["total"] == 1002


def test_api_preserves_more_than_28_digit_money_in_saved_and_paged_results(client):
    opening = "99999999999999999999999999999.123456789123456789"
    entry = "100000000000000000000000000000.123456789123456789"
    exit = "100000000000000000000000000002.123456789123456789"
    raw = ("Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol\n"
           f"01/05/2026,10:00,{opening},{entry},{opening},{entry},0,0,0\n"
           f"01/05/2026,10:01,{entry},{exit},{entry},{exit},0,0,0\n").encode()
    saved = client.post("/api/datasets", params={"filename": "precise.csv", "name": "Precise", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10"}, content=raw).json()
    request = body(saved["id"])
    request["strategy_parameters"] = {"green_bar_count": 1, "hold_minutes": 1, "contracts": 2}
    request["execution_settings"]["initial_capital"] = entry
    response = client.post("/api/backtests", json=request)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["summary"]["final_equity"] == "100000000000000000000000000026.123456789123456789"
    assert Decimal(record["summary"]["total_net_pnl"]) == Decimal(26)
    trade = client.get(f"/api/backtests/{record['id']}/trades").json()["items"][0]
    assert trade["entry_fill_price"] == "100000000000000000000000000000.373456789123456789"
    equity = client.get(f"/api/backtests/{record['id']}/equity").json()["items"]
    assert equity[0]["equity"] == entry and equity[1]["equity"] == record["summary"]["final_equity"]


def test_evicted_progress_id_reused_for_upload_cannot_be_overwritten_by_old_run(client, monkeypatch):
    dataset = save_fixture(client)
    operation_id = str(uuid4())
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    def pause(self, bar, position):
        if bar.bar_number == 2:
            entered.set()
            assert release.wait(5)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/api/backtests", params={"progress_id": operation_id}, json=body(dataset["id"]))
        try:
            assert entered.wait(5)
            for _ in range(128):
                client.app.state.progress.start(str(uuid4()))
            assert client.get(f"/api/progress/{operation_id}").status_code == 404
            response = client.post("/api/datasets/validate", params={"filename": "fixture.csv", "source_timezone": "UTC", "progress_id": operation_id},
                                   content=(FIXTURES / "arithmetic_5m.csv").read_bytes())
            assert response.status_code == 200
            upload_progress = client.get(f"/api/progress/{operation_id}").json()
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 201
    assert client.get(f"/api/progress/{operation_id}").json() == upload_progress


def test_progress_does_not_need_a_free_worker_thread(client, monkeypatch):
    dataset = save_fixture(client)
    operation_id = str(uuid4())
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    async def set_capacity(capacity):
        limiter = current_default_thread_limiter()
        previous = limiter.total_tokens
        limiter.total_tokens = capacity
        return previous

    def pause(self, bar, position):
        if bar.bar_number == 2:
            entered.set()
            assert release.wait(5)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", pause)
    capacity = client.portal.call(set_capacity, 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(client.post, "/api/backtests", params={"progress_id": operation_id}, json=body(dataset["id"]))
        try:
            assert entered.wait(5)
            poll = pool.submit(client.get, f"/api/progress/{operation_id}")
            assert poll.result(timeout=1).json()["bars_processed"] == 1
        finally:
            release.set()
            client.portal.call(set_capacity, capacity)
        assert pending.result(timeout=5).status_code == 201

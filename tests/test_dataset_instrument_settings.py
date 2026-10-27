"""Saved instrument defaults and exact, isolated per-run overrides."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.strategies import consecutive_green_hold as sample
from test_api import SAMPLE, PARAMS
from test_backtest_api import client, save_fixture, body


SETTINGS = {"tick_size": "0.25", "point_value": "10"}


def test_update_preserves_csv_and_all_other_metadata_and_survives_restart(tmp_path):
    database = tmp_path / "datasets.sqlite3"
    with TestClient(create_app(database)) as client:
        saved = client.post("/api/datasets", params=PARAMS, content=SAMPLE).json()
        endpoint = f"/api/datasets/{saved['id']}"
        exact = {"tick_size": "0.250000000000000000000000001", "point_value": "20.123456789123456789123456789"}
        response = client.patch(endpoint + "/instrument-settings", json=exact)
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated == {**saved, "instrument_settings": exact}
        assert client.get(endpoint + "/csv").content == SAMPLE
        assert client.get("/api/datasets").json() == [updated]
        with client.app.state.store.connect() as conn:
            chunks = list(conn.execute("SELECT ordinal, data FROM dataset_chunks WHERE dataset_id=?", (saved['id'],)))
        assert chunks == [(0, SAMPLE)]
    with TestClient(create_app(database)) as restarted:
        assert restarted.get(endpoint).json() == updated
        assert restarted.get(endpoint + "/csv").content == SAMPLE


@pytest.mark.parametrize("field,value", [
    ("tick_size", "0"), ("tick_size", "-1"), ("tick_size", "NaN"), ("tick_size", "Infinity"),
    ("point_value", "-Infinity"), ("point_value", ""), ("point_value", "invalid"),
    ("point_value", "1_000"), ("point_value", 20), ("point_value", True), ("point_value", None),
])
def test_invalid_settings_are_rejected_atomically(client, field, value):
    saved = save_fixture(client)
    endpoint = f"/api/datasets/{saved['id']}"
    settings = {**SETTINGS, field: value}
    assert client.patch(endpoint + "/instrument-settings", json=settings).status_code == 422
    assert client.get(endpoint).json() == saved


def test_pair_required_unknown_dataset_and_cross_origin(client):
    saved = save_fixture(client)
    endpoint = f"/api/datasets/{saved['id']}/instrument-settings"
    for settings in ({"tick_size": "0.25"}, {**SETTINGS, "symbol": "NQ"}):
        assert client.patch(endpoint, json=settings).status_code == 422
    assert client.patch("/api/datasets/missing/instrument-settings", json=SETTINGS).status_code == 404
    assert client.patch(endpoint, json=SETTINGS, headers={"origin": "https://evil.example"}).status_code == 403


def test_upload_accepts_optional_pair_and_rejects_partial_or_invalid_values(client):
    for settings in ({"tick_size": "0.25"}, {"point_value": "10"}, {"tick_size": "0", "point_value": "10"}):
        assert client.post("/api/datasets", params={**PARAMS, **settings}, content=SAMPLE).status_code == 422
        assert client.get("/api/datasets").json() == []
    saved = client.post("/api/datasets", params={**PARAMS, **SETTINGS}, content=SAMPLE).json()
    assert saved["instrument_settings"] == SETTINGS


def test_legacy_dataset_requires_saved_defaults(client):
    raw = client.post("/api/datasets", params=PARAMS, content=SAMPLE).json()
    request = body(raw["id"])
    response = client.post("/api/backtests", json=request)
    assert response.status_code == 422 and "dataset's tick size" in response.json()["detail"]
    endpoint = f"/api/datasets/{raw['id']}/instrument-settings"
    assert client.patch(endpoint, json=SETTINGS).status_code == 200
    assert client.post("/api/backtests", json=request).status_code == 201


def test_running_and_completed_reports_keep_captured_settings_after_dataset_edit(client, monkeypatch):
    saved = save_fixture(client)
    endpoint = f"/api/datasets/{saved['id']}/instrument-settings"
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    def pause(self, bar, position):
        if bar.bar_number == 3:
            entered.set()
            assert release.wait(10)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, "/api/backtests", json=body(saved["id"]))
        try:
            assert entered.wait(10)
            response = client.patch(endpoint, json={"tick_size": "0.5", "point_value": "20"})
            assert response.status_code == 200
        finally:
            release.set()
        response = pending.result(timeout=10)
    assert response.status_code == 201, response.text
    first = response.json()
    assert first["execution_settings"]["tick_size"] == "0.25"
    assert first["run_metadata"]["dataset"]["instrument_settings"] == SETTINGS
    assert Decimal(first["summary"]["total_net_pnl"]) == 26
    second = client.post("/api/backtests", json=body(saved["id"])).json()
    assert second["execution_settings"]["tick_size"] == "0.5"
    assert second["execution_settings"]["point_value"] == "20"
    assert Decimal(second["summary"]["total_net_pnl"]) == 36  # (101.5 - 100.5) * 2 * 20 - 4
    assert client.get(f"/api/backtests/{first['id']}").json() == first


@pytest.mark.parametrize("overrides,expected,changed", [
    ({"tick_size": "0.5"}, "16", {"tick_size": "0.5"}),
    ({"point_value": "20"}, "56", {"point_value": "20"}),
    ({"tick_size": "0.5", "point_value": "20"}, "36", {"tick_size": "0.5", "point_value": "20"}),
    ({"tick_size": "0.2500", "point_value": "1e1"}, "26", {}),
    ({"tick_size": None, "point_value": None}, "26", {}),
])
def test_overrides_resolve_individually_preserve_defaults_and_survive_restart(client, overrides, expected, changed):
    dataset = save_fixture(client)
    request = body(dataset["id"])
    request["execution_settings"].update(overrides)
    response = client.post("/api/backtests", json=request)
    assert response.status_code == 201, response.text
    record = response.json()
    assert Decimal(record["summary"]["total_net_pnl"]) == Decimal(expected)
    assert record["run_metadata"]["instrument_overrides"] == changed
    assert record["run_metadata"]["dataset"]["instrument_settings"] == SETTINGS
    assert client.get(f"/api/datasets/{dataset['id']}").json() == dataset
    for key in SETTINGS:
        assert Decimal(record["execution_settings"][key]) == Decimal(overrides.get(key) or SETTINGS[key])
    # A future edit does not rewrite either the baseline or override in this report.
    assert client.patch(f"/api/datasets/{dataset['id']}/instrument-settings",
                        json={"tick_size": "1", "point_value": "2"}).status_code == 200
    with TestClient(create_app(client.app.state.store.path)) as restarted:
        assert restarted.get(f"/api/backtests/{record['id']}").json() == record


@pytest.mark.parametrize("field,value", [
    ("tick_size", "0"), ("tick_size", "-0.25"), ("tick_size", "NaN"), ("tick_size", "Infinity"),
    ("point_value", "0"), ("point_value", "-1"), ("point_value", "1_000"), ("point_value", ""),
    ("point_value", 20), ("point_value", True), ("point_value", "1" * 129),
])
def test_invalid_run_instrument_overrides_fail_without_saving_or_changing_dataset(client, field, value):
    dataset = save_fixture(client)
    request = body(dataset["id"])
    request["execution_settings"][field] = value
    response = client.post("/api/backtests", json=request)
    assert response.status_code == 422, response.text
    assert client.get("/api/backtests").json()["total"] == 0
    assert client.get(f"/api/datasets/{dataset['id']}").json() == dataset


def test_override_precision_is_preserved_and_no_override_follows_default_changes(client):
    dataset = save_fixture(client)
    request = body(dataset["id"])
    precise = "10.000000000000000000000000001"
    request["execution_settings"]["point_value"] = precise
    record = client.post("/api/backtests", json=request).json()
    assert record["execution_settings"]["point_value"] == precise
    assert record["run_metadata"]["instrument_overrides"] == {"point_value": precise}
    # (101.75 - 100.25) * 2 * point value - 4; no precision loss.
    assert record["summary"]["total_net_pnl"] == "26.00000000000000000000000000300"
    second = client.post("/api/backtests", json=body(dataset["id"])).json()
    assert second["run_metadata"]["instrument_overrides"] == {}
    assert Decimal(second["summary"]["total_net_pnl"]) == 26


def test_cli_instrument_overrides_share_api_resolution_and_provenance(client, tmp_path):
    import json
    import subprocess
    import sys

    dataset = save_fixture(client)
    from research_fixtures import cli_split,declaration
    output = tmp_path / "cli-override"
    completed = subprocess.run([
        sys.executable, "-m", "alphaquest.run_backtest", "--database", str(client.app.state.store.path),
        "--dataset-id", dataset["id"], "--output", str(output), "--contracts", "2", "--initial-capital", "10000",
        "--slippage-ticks", "1", "--commission-per-contract-per-side", "1", "--tick-size", "0.5", "--point-value", "20",
        *cli_split(declaration(dataset["id"])),
    ], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    report = json.loads((output / "report.json").read_text())
    assert Decimal(report["summary"]["total_net_pnl"]) == 36
    assert report["run_metadata"]["instrument_overrides"] == {"tick_size": "0.5", "point_value": "20"}
    assert report["run_metadata"]["dataset"]["instrument_settings"] == SETTINGS
    assert client.get(f"/api/datasets/{dataset['id']}").json() == dataset

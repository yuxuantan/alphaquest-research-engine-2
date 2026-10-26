from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from alphaquest.app import create_app
from alphaquest import app as app_module
from alphaquest.datasets import DatasetStore

SAMPLE = (Path(__file__).parents[1] / "alphaquest/web/example.csv").read_bytes()
PARAMS = {"filename": "example.csv", "name": "ES example", "symbol": "ES", "source_timezone": "UTC"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        yield client


def test_full_validate_save_reload_download_flow(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/example.csv").content == SAMPLE
    assert client.get("/api/datasets").json() == []
    validation = client.post("/api/datasets/validate", params=PARAMS, content=SAMPLE)
    assert validation.status_code == 200
    assert validation.json()["row_count"] == 5
    assert client.get("/api/datasets").json() == []
    response = client.post("/api/datasets", params=PARAMS, content=SAMPLE)
    assert response.status_code == 201
    saved = response.json()
    assert saved["name"] == "ES example"
    assert saved["preview"][0]["UpVol"] == "83"
    assert saved["preview"][0]["DownVol"] == "99"
    assert saved["columns"] == ["Date", "Time", "Open", "High", "Low", "Close", "Volume", "UpVol", "DownVol"]
    assert client.get("/api/datasets").json() == [saved]
    assert client.get(f'/api/datasets/{saved["id"]}').json() == saved
    download = client.get(f'/api/datasets/{saved["id"]}/csv')
    assert download.content == SAMPLE
    assert download.headers["content-disposition"].startswith("attachment;")
    assert client.post("/api/datasets", params=PARAMS, content=SAMPLE).status_code == 409


def test_timezone_choices_are_available_to_the_portal(client):
    response = client.get("/api/timezones")
    assert response.status_code == 200
    choices = response.json()
    assert choices == sorted(set(choices))
    assert {"UTC", "America/New_York", "America/Chicago", "Asia/Singapore"} <= set(choices)


def test_direct_save_without_validation_is_checked(client):
    response = client.post("/api/datasets", params=PARAMS, content=SAMPLE.replace(b"5654.50", b"NaN"))
    assert response.status_code == 422
    assert response.json()["errors"][0]["column"] == "High"
    assert client.get("/api/datasets").json() == []


def test_server_enforces_size_limit_even_without_content_length(client, monkeypatch):
    monkeypatch.setattr(app_module, "MAX_BYTES", 10)
    for endpoint in ["/api/datasets", "/api/datasets/validate"]:
        assert client.post(endpoint, params=PARAMS, content=iter([b"123456", b"123456"])).status_code == 413
    assert client.get("/api/datasets").json() == []


def test_upload_size_boundary_is_inclusive(client, monkeypatch):
    assert app_module.MAX_BYTES == 1_000_000_000
    monkeypatch.setattr(app_module, "MAX_BYTES", len(SAMPLE))
    assert client.post("/api/datasets/validate", params=PARAMS, content=SAMPLE).status_code == 200
    assert client.post("/api/datasets", params=PARAMS, content=SAMPLE).status_code == 201
    for endpoint in ["/api/datasets", "/api/datasets/validate"]:
        response = client.post(endpoint, params=PARAMS, content=SAMPLE + b"\n")
        assert response.status_code == 413
        assert response.json()["detail"] == "The CSV exceeds the 1 GB limit."


@pytest.mark.parametrize("params", [{**PARAMS, "name": " "}, {**PARAMS, "name": "x" * 121}, {**PARAMS, "symbol": "x" * 41}, {**PARAMS, "source_timezone": "invalid"}])
def test_invalid_metadata_is_not_saved(client, params):
    assert client.post("/api/datasets", params=params, content=SAMPLE).status_code == 422
    assert client.get("/api/datasets").json() == []


def test_timezone_interpretations_are_distinct(client):
    raw = SAMPLE
    one = client.post("/api/datasets", params=PARAMS, content=raw).json()
    two = client.post("/api/datasets", params={**PARAMS, "source_timezone": "America/New_York"}, content=raw).json()
    assert one["sha256"] == two["sha256"]
    assert one["start"] != two["start"]
    assert len(client.get("/api/datasets").json()) == 2


def test_unknown_dataset_and_untrusted_requests(client):
    assert client.get("/api/datasets/missing").status_code == 404
    assert client.get("/api/datasets/missing/csv").status_code == 404
    assert client.get("/", headers={"host": "evil.example"}).status_code == 400
    assert client.post("/api/datasets", params=PARAMS, content=SAMPLE, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get("/").headers["x-content-type-options"] == "nosniff"


def test_delete_dataset_and_reupload(client):
    saved = client.post("/api/datasets", params=PARAMS, content=SAMPLE).json()
    endpoint = f'/api/datasets/{saved["id"]}'
    assert client.delete(endpoint, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get(endpoint).status_code == 200
    deleted = client.delete(endpoint, headers={"origin": "http://testserver"})
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get("/api/datasets").json() == []
    assert client.get(endpoint).status_code == 404
    assert client.get(endpoint + "/csv").status_code == 404
    assert client.delete(endpoint).status_code == 404
    assert client.post("/api/datasets", params=PARAMS, content=SAMPLE).status_code == 201


@pytest.mark.parametrize("endpoint", ["/api/datasets/validate", "/api/datasets"])
def test_progress_can_be_read_while_rows_are_being_validated(client, monkeypatch, endpoint):
    entered, release = Event(), Event()
    original = app_module.validate_csv_file
    operation_id = str(uuid4())

    def paused_validation(source, filename, timezone, progress):
        progress("validating", 100, len(SAMPLE), 1234)
        entered.set()
        assert release.wait(5)
        return original(source, filename, timezone, progress)

    monkeypatch.setattr(app_module, "validate_csv_file", paused_validation)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(client.post, endpoint, params={**PARAMS, "progress_id": operation_id}, content=SAMPLE)
        try:
            assert entered.wait(5)
            status = client.get(f"/api/progress/{operation_id}")
            assert status.headers["cache-control"] == "no-store"
            assert status.json() == {"stage": "validating", "completed_bytes": 100, "total_bytes": len(SAMPLE), "rows_checked": 1234}
            assert client.get("/api/datasets").json() == []
        finally:
            release.set()
        assert request.result(timeout=5).status_code in (200, 201)
    final = client.get(f"/api/progress/{operation_id}").json()
    assert final == {"stage": "done", "completed_bytes": len(SAMPLE), "total_bytes": len(SAMPLE), "rows_checked": 5}


def test_save_progress_only_completes_after_commit(client, monkeypatch):
    entered, release = Event(), Event()
    original = DatasetStore.save_file
    operation_id = str(uuid4())

    def paused_save(self, source, metadata, name, symbol, progress):
        def report(stage, *args):
            progress(stage, *args)
            if stage == "committing":
                entered.set()
                assert release.wait(5)
        return original(self, source, metadata, name, symbol, report)

    monkeypatch.setattr(DatasetStore, "save_file", paused_save)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(client.post, "/api/datasets", params={**PARAMS, "progress_id": operation_id}, content=SAMPLE)
        try:
            assert entered.wait(5)
            assert client.get(f"/api/progress/{operation_id}").json()["stage"] == "committing"
            assert client.get("/api/datasets").json() == []
        finally:
            release.set()
        assert request.result(timeout=5).status_code == 201
    assert client.get(f"/api/progress/{operation_id}").json()["stage"] == "done"
    assert len(client.get("/api/datasets").json()) == 1


def test_failed_and_duplicate_requests_never_report_progress_done(client):
    for raw in [SAMPLE.replace(b"5654.50", b"NaN"), SAMPLE, SAMPLE]:
        operation_id = str(uuid4())
        result = client.post("/api/datasets", params={**PARAMS, "progress_id": operation_id}, content=raw)
        stage = client.get(f"/api/progress/{operation_id}").json()["stage"]
        assert stage == ("done" if result.status_code == 201 else "failed")
    assert result.status_code == 409
    assert len(client.get("/api/datasets").json()) == 1


def test_progress_identifiers_are_unique_and_storage_is_bounded(client):
    operation_id = str(uuid4())
    params = {**PARAMS, "progress_id": operation_id}
    assert client.get(f"/api/progress/{operation_id}").status_code == 404
    assert client.post("/api/datasets/validate", params=params, content=SAMPLE).status_code == 200
    assert client.post("/api/datasets/validate", params=params, content=SAMPLE).status_code == 409
    assert client.get(f"/api/progress/{operation_id}").json()["stage"] == "done"
    for _ in range(128):
        client.app.state.progress.start(str(uuid4()))
    assert len(client.app.state.progress.states) == 128
    assert client.get(f"/api/progress/{operation_id}").status_code == 404


def test_portal_revalidates_assets_and_uses_one_content_version(client, tmp_path, monkeypatch):
    import re
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text((app_module.WEB / "index.html").read_text())
    (web / "app.js").write_text("first bundle")
    monkeypatch.setattr(app_module, "WEB", web)
    first = client.get("/")
    assert first.headers["cache-control"] == "no-cache"
    versions = re.findall(r"/static/[^\" ]+\?v=([a-f0-9]{16})", first.text)
    assert len(versions) == 6 and len(set(versions)) == 1
    assert "ASSET_VERSION" not in first.text
    (web / "app.js").write_text("updated bundle")
    second = client.get("/")
    assert versions[0] not in second.text
    assert client.get("/static/backtests.js").headers["cache-control"] == "no-cache"

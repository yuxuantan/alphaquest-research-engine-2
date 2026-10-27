"""Lossless archive publication, readable portal reports, and interrupted cleanup."""

import gzip
import json
from pathlib import Path

import pytest

from alphaquest import optimization_worker
from alphaquest.compress_optimization_reports import compress_existing, digest
from test_optimization import client, optimization_body, start, wait_job
from test_backtest_api import body, save_fixture


def full_optimization(client, monkeypatch):
    original = optimization_worker.prepare_backtest_report
    def full(*args, **kwargs):
        kwargs["report_detail"] = "full"
        return original(*args, **kwargs)
    monkeypatch.setattr(optimization_worker, "prepare_backtest_report", full)
    dataset = save_fixture(client)
    job = wait_job(client, start(client, optimization_body(dataset["id"])))
    monkeypatch.setattr(optimization_worker, "prepare_backtest_report", original)
    assert job["status"] == "complete"
    rows = client.get(f"/api/optimizations/{job['id']}/results").json()["items"]
    return dataset, job, rows


def test_compress_exact_bytes_preserves_metrics_csvs_and_standalone_reports(client, monkeypatch, tmp_path):
    dataset, job, rows = full_optimization(client, monkeypatch)
    standalone = client.post("/api/backtests", json=body(dataset["id"])).json()
    root = client.app.state.runs.root
    standalone_before = {p.name: p.read_bytes() for p in (root / standalone["id"]).iterdir()}
    originals = {row["run_id"]: {p.name: p.read_bytes() for p in (root / row["run_id"]).iterdir()} for row in rows}
    result = compress_existing(root.parent, tmp_path / "compression-evidence", progress=lambda message: None)
    assert result["compressed_reports"] == 3 and result["saved_bytes"] > 0
    for run_id, files in originals.items():
        folder = root / run_id
        assert not (folder / "report.json").exists()
        assert gzip.decompress((folder / "report.json.gz").read_bytes()) == files["report.json"]
        for name in ("trades.csv", "equity.csv"):
            assert (folder / name).read_bytes() == files[name]
        download = client.get(f"/api/backtests/{run_id}/exports/report")
        assert download.status_code == 200 and download.headers["content-type"] == "application/gzip"
        assert gzip.decompress(download.content) == files["report.json"]
        record = client.get(f"/api/backtests/{run_id}").json()
        assert record["summary"] == json.loads(files["report.json"])["summary"]
        assert record["report_archive"]["uncompressed_sha256"] == digest(folder / "report.json.gz", compressed=True)[0]
        assert client.get(f"/api/backtests/{run_id}/chart").status_code == 200
    assert client.get(f"/api/optimizations/{job['id']}").json() == job
    assert client.get(f"/api/optimizations/{job['id']}/results").json()["items"] == rows
    assert {p.name: p.read_bytes() for p in (root / standalone["id"]).iterdir()} == standalone_before
    assert client.get(f"/api/backtests/{standalone['id']}").json() == standalone
    repeated = compress_existing(root.parent, tmp_path / "repeat-evidence", progress=lambda message: None)
    assert repeated["compressed_reports"] == 0


def test_interrupted_cleanup_retains_both_verified_copies_and_rerun_finishes(client, monkeypatch, tmp_path):
    _, _, rows = full_optimization(client, monkeypatch)
    root = client.app.state.runs.root
    original_unlink = Path.unlink
    failures = []
    def fail_cleanup(path, *args, **kwargs):
        if path.name == "report.json" and not failures:
            failures.append(path)
            raise OSError("Controlled cleanup interruption")
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(OSError, match="cleanup interruption"):
        compress_existing(root.parent, tmp_path / "interrupted-evidence", progress=lambda message: None)
    path = failures[0]
    assert path.exists() and path.with_suffix(".json.gz").exists()
    assert gzip.decompress(path.with_suffix(".json.gz").read_bytes()) == path.read_bytes()
    assert client.get(f"/api/backtests/{path.parent.name}/exports/report").status_code == 200
    monkeypatch.setattr(Path, "unlink", original_unlink)
    result = compress_existing(root.parent, tmp_path / "recovered-evidence", progress=lambda message: None)
    assert result["compressed_reports"] == 3
    assert all(not (root / row["run_id"] / "report.json").exists() for row in rows)


def test_bad_existing_archive_preserves_original_and_catalogue(client, monkeypatch, tmp_path):
    _, _, rows = full_optimization(client, monkeypatch)
    root = client.app.state.runs.root
    run_id = min(row["run_id"] for row in rows)
    folder = root / run_id
    original = (folder / "report.json").read_bytes()
    with gzip.open(folder / "report.json.gz", "wb") as stream:
        stream.write(b"wrong report")
    with pytest.raises(ValueError, match="does not match"):
        compress_existing(root.parent, tmp_path / "bad-archive-evidence", progress=lambda message: None)
    assert (folder / "report.json").read_bytes() == original
    assert client.get(f"/api/backtests/{run_id}").json()["artifacts"]["report"] == "report.json"


def test_active_optimization_rejects_before_creating_evidence(client, monkeypatch, tmp_path):
    _, job, _ = full_optimization(client, monkeypatch)
    client.app.state.optimizations.update(job["id"], status="running")
    with pytest.raises(ValueError, match="finish"):
        compress_existing(client.app.state.runs.root.parent, tmp_path / "active-evidence")
    assert not (tmp_path / "active-evidence").exists()


def test_archived_legacy_report_still_supports_drawdown_enrichment(client, monkeypatch, tmp_path):
    _, _, rows = full_optimization(client, monkeypatch)
    run_id = rows[0]["run_id"]
    original = client.get(f"/api/backtests/{run_id}").json()
    legacy = json.loads(json.dumps(original))
    for key in ("period_start_utc", "period_end_utc"):
        legacy.pop(key)
    for key in ("max_drawdown_amount", "max_drawdown_pct", "max_drawdown_duration_seconds"):
        legacy["summary"].pop(key)
    with client.app.state.runs.connect() as conn:
        conn.execute("UPDATE runs SET manifest=? WHERE id=?", (json.dumps(legacy), run_id))
    compress_existing(client.app.state.runs.root.parent, tmp_path / "legacy-evidence", progress=lambda message: None)
    restored = client.get(f"/api/backtests/{run_id}").json()
    assert restored["summary"] == original["summary"]
    assert restored["period_start_utc"] == original["period_start_utc"]
    assert restored["period_end_utc"] == original["period_end_utc"]
    assert restored["artifacts"]["report"] == "report.json.gz"

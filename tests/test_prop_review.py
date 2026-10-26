"""Public review outputs exercise actual saved artifacts, not canned success flags."""

import csv
from dataclasses import replace
from hashlib import sha256
import io
import json
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.prop import ResolvedProfile, ResolvedSimulation, get_profile
from alphaquest.prop import review


@pytest.mark.parametrize("platform", ["rithmic", "tradovate", "wealthcharts"])
@pytest.mark.parametrize("quantity,net,marks", [(1, "13", ["-3.5", "1.5", "13"]), (2, "26", ["-7", "3", "26"])])
def test_review_outputs_persist_exact_values_sources_and_isolation(tmp_path, platform, quantity, net, marks):
    app = create_app(tmp_path / "datasets.sqlite3")
    with TestClient(app) as client:
        assert client.get("/api/prop-review/latest").status_code == 404
        before = client.get("/api/backtests").json()
        response = client.post("/api/prop-review", json={"platform": platform, "quantity": quantity})
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["synthetic"] is True and result["all_passed"] is True
        assert len(result["checks"]) == 44 and all(c["passed"] for c in result["checks"])
        assert {c["subtask"] for c in result["checks"]} == {1, 2, 3}
        assert result["adapter"]["trade"]["net_pnl"] == net
        assert result["adapter"]["trade"]["source"]["contracts"] == 2
        assert [s["trade_count"] for s in result["adapter"]["sessions"]] == [0, 1, 0]
        observed = [o["equity_change"] for o in result["adapter"]["observations"] if o["mode"] == "bar_close" and o["trade_number"]]
        assert observed == marks
        assert client.get("/api/backtests").json() == before
        assert client.get("/api/datasets").json() == []
        base = f"/api/prop-review/{result['id']}"
        assert client.get(base).json() == result
        profile = ResolvedProfile.from_json(client.get(base + "/exports/profile.json").text)
        settings = ResolvedSimulation.from_json(client.get(base + "/exports/simulation.json").text)
        assert profile.profile == get_profile("apex_50k_eod_" + platform)
        assert settings.rules == profile and settings.config.quantity == quantity
        saved_spec = client.get(base + "/exports/specification.md").content
        assert sha256(saved_spec).hexdigest() == result["specification"]["sha256"]
        observations = list(csv.DictReader(io.StringIO(client.get(base + "/exports/observations.csv").text)))
        assert len(observations) == 10
        assert [o["equity_change"] for o in observations if o["mode"] == "trade_close"] == [net]
        with ZipFile(io.BytesIO(client.get(base + "/exports/bundle.zip").content)) as bundle:
            names = bundle.namelist()
            assert {"profile.json", "simulation.json", "source.json", "calendar.json", "checks.csv", "observations.csv", "sessions.csv", "specification.md", "review.json"} <= set(names)
            source = json.loads(bundle.read("source.json"))
            metadata = json.loads(source["manifest_json"])["run_metadata"]
            assert sha256(bundle.read("sources/arithmetic/dataset.csv")).hexdigest() == metadata["dataset"]["sha256"]
            assert sha256(bundle.read("sources/arithmetic/strategy.py")).hexdigest() == metadata["strategy"]["source_sha256"]
            for artifact in source["artifacts"]:
                name, = [n for n in names if n.startswith("sources/arithmetic/backtest_runs/") and n.endswith("/" + artifact["name"])]
                assert sha256(bundle.read(name)).hexdigest() == artifact["sha256"]
            raw_report, = [n for n in names if n.startswith("sources/arithmetic/backtest_runs/") and n.endswith("report.json")]
            assert json.loads(bundle.read(raw_report))["trades"][0]["net_pnl"] == "26.00"
        assert client.get(base + "/exports/backtests.sqlite3").status_code == 404
    # A new application/process lifetime reads the original review off disk.
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as restarted:
        assert restarted.get("/api/prop-review/latest").json() == result


@pytest.mark.parametrize("body", [{"quantity": True}, {"quantity": "1"}, {"quantity": 1.5}, {"quantity": 0},
                                  {"quantity": 3}, {"platform": "unknown"}, {"unrecognized": 1}])
def test_invalid_requests_do_not_publish_review(tmp_path, body):
    with TestClient(create_app(tmp_path / "datasets.sqlite3")) as client:
        assert client.post("/api/prop-review", json=body).status_code == 422
        assert client.get("/api/prop-review/latest").status_code == 404
        assert not (tmp_path / "prop_reviews").exists()


def test_failed_generation_preserves_previous_review_and_cleans_staging(tmp_path, monkeypatch):
    first = review.create_review(tmp_path, "rithmic", 2)

    def fail(path, *args):
        (path / "partial.json").write_text("{}")
        raise RuntimeError("Interrupted demonstration")

    monkeypatch.setattr(review, "build_review", fail)
    with pytest.raises(RuntimeError, match="Interrupted"):
        review.create_review(tmp_path, "rithmic", 1)
    assert (tmp_path / "latest").read_text() == first["id"]
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["latest", first["id"]])


def test_demonstration_reports_a_real_regression_instead_of_always_passing(tmp_path, monkeypatch):
    profile = get_profile()
    # A valid alternative template must fail the independent 3000 target oracle.
    changed = replace(profile, evaluation=replace(profile.evaluation, profit_target=review.D("3100"),
                                                 drawdown=replace(profile.evaluation.drawdown, lock_profit=review.D("3100"))))
    monkeypatch.setattr(review, "get_profile", lambda *args: changed)
    result = review.create_review(tmp_path, "rithmic", 2)
    assert result["all_passed"] is False
    assert any(not c["passed"] and c["subtask"] == 2 for c in result["checks"])
    assert json.loads((tmp_path / result["id"] / "review.json").read_text())["all_passed"] is False

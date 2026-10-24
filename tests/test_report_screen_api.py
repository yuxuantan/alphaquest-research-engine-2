"""Exact full-resolution equity previews and disk-streamed CSV exports."""

from decimal import Decimal
import csv
from pathlib import Path

import pytest

from alphaquest.report_chart import equity_records, equity_preview
from test_backtest_api import client, run_fixture
from review_execution import fixtures
from review_reports import _equal_record


@pytest.mark.parametrize("case", fixtures(), ids=lambda case: case["id"])
def test_chart_and_exports_match_every_reviewed_fixture(client, case):
    dataset, record = run_fixture(client, case)
    base = f"/api/backtests/{record['id']}"
    folder = client.app.state.runs.root / record["id"]
    response = client.get(base + "/chart")
    assert response.status_code == 200
    preview = response.json()
    expected = [{"trade_number": 0, "exit_time_utc": None, "net_pnl": "0",
                 "equity": case["execution_settings"]["initial_capital"]}] + [
        {"trade_number": trade["trade_number"], "exit_time_utc": trade["exit_time_utc"],
         "net_pnl": trade["net_pnl"], "equity": case["expected_equity"][trade["exit_bar_number"]]["equity"]}
        for trade in case["expected_trades"]]
    assert len(preview["items"]) == len(expected)
    for actual, wanted in zip(preview["items"], expected, strict=True):
        _equal_record(actual, wanted)
    assert preview["items"] == client.get(base + "/equity").json()["items"]
    assert preview["total"] == len(case["expected_trades"]) + 1
    assert preview["sampled"] is False
    assert preview["currency"] == "CU (account currency unspecified)"
    for kind in ("trades", "equity"):
        response = client.get(base + f"/exports/{kind}")
        assert response.status_code == 200
        assert response.content == (folder / f"{kind}.csv").read_bytes()
        assert f"{record['id']}-{kind}.csv" in response.headers["content-disposition"]
        assert response.headers["content-type"].startswith("text/csv")
    # Reports and their exports outlive the source dataset.
    assert client.delete("/api/datasets/" + dataset["id"]).status_code == 204
    assert client.get(base + "/chart").json() == preview
    assert client.get(base + "/exports/trades").status_code == 200


def test_chart_sampling_is_bounded_preserves_extremes_and_reads_incrementally(tmp_path, monkeypatch):
    path = tmp_path / "equity.csv"
    total = 100_001
    with path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["trade_number", "exit_time_utc", "net_pnl", "equity"])
        for i in range(total):
            # One isolated spike and loss in different buckets must survive.
            value = "100000000000000000000000000001.123456789" if i == 9876 else "-123456789.000000000001" if i == 87654 else "10000"
            writer.writerow([i, "" if not i else "2026-01-05T10:00:00Z", "0", value])
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: pytest.fail("Must stream CSV"))
    original_open = Path.open
    reads = []

    class IncrementalFile:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def __iter__(self): return self
        def __next__(self):
            line = next(self.stream)
            assert len(line) < 200
            reads.append(1)
            return line
        def read(self, *args): pytest.fail("Must read records incrementally")

    monkeypatch.setattr(Path, "open", lambda self, *args, **kwargs: IncrementalFile(original_open(self, *args, **kwargs)))
    stream = equity_records(path)
    assert next(stream)["trade_number"] == 0
    assert len(reads) == 2  # Header and first row, before the rest is read.
    stream.close()
    for limit in (16, 17, 1000, 2000):
        result = equity_preview(path, total, limit)
        items = result["items"]
        assert len(items) <= limit
        assert items[0]["trade_number"] == 0 and items[-1]["trade_number"] == total - 1
        ordinals = [point["trade_number"] for point in items]
        assert ordinals == sorted(set(ordinals))
        assert 9876 in ordinals and 87654 in ordinals
        assert min(Decimal(p["equity"]) for p in items) == Decimal("-123456789.000000000001")
        assert result["sampled"] is True


@pytest.mark.parametrize("suffix", ["chart", "exports/trades", "exports/equity", "exports/report", "exports/../report.json"])
def test_chart_and_export_missing_run_or_kind_is_rejected(client, suffix):
    assert client.get("/api/backtests/" + "a" * 32 + "/" + suffix).status_code == 404


@pytest.mark.parametrize("limit", [0, 15, 2001, "bad"])
def test_chart_limit_validation(client, limit):
    assert client.get("/api/backtests/" + "a" * 32 + f"/chart?max_points={limit}").status_code == 422


def test_truncated_or_inconsistent_chart_is_not_shown_as_complete(client):
    _, record = run_fixture(client)
    path = client.app.state.runs.root / record["id"] / "equity.csv"
    path.write_text("trade_number,exit_time_utc,net_pnl,equity\n0,,0,10000\n")
    assert client.get(f"/api/backtests/{record['id']}/chart").status_code == 500

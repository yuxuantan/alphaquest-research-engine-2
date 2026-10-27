"""Retained benchmark through normal APIs; owned server stops on exit.

.venv/bin/python tests/review_optimization_acceleration.py --output artifacts/optimization-speed-NEW
"""

import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect

from alphaquest.benchmark_optimization import benchmark
from alphaquest.optimization import MAX_WORKERS
from alphaquest.strategies.registry import get_strategy
from review_optimization_portal import serve_review


def review(output, url, bars, repeats):
    stamp = datetime(2026, 1, 5)
    lines = ["Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol"]
    for minute in range(bars):
        # Varying ranges exercise nonzero ADX and strict-pivot calculations.
        # Every close remains inside every opening range, preventing entries.
        high = Decimal(102) + Decimal(minute % 19) / 4
        low = Decimal(98) - Decimal(minute % 13) / 4
        lines.append((stamp + timedelta(minutes=minute)).strftime("%m/%d/%Y,%H:%M") + f",99.75,{high},{low},100,100,60,40")
    source = "\n".join(lines).encode()
    (output / "SYNTHETIC-speed-benchmark.csv").write_bytes(source)
    with httpx.Client(base_url=url, timeout=120) as client:
        saved = client.post("/api/datasets", params={"filename": "synthetic.csv", "name": "SYNTHETIC reusable acceleration benchmark", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10"}, content=source)
        saved.raise_for_status()
        definition = get_strategy("vwap_pullback_risk_sizing")
        request = {"dataset_id": saved.json()["id"], "strategy_id": definition.module.STRATEGY_ID, "method": "exhaustive",
                   "parameter_ranges": {field["name"]: {"start": field["default"], "end": field["default"], "step": "0" if field["type"] == "Decimal" else 0} for field in definition.description()["parameters"]},
                   "execution_settings": {"initial_capital": "10000", "slippage_ticks": 1, "commission_per_contract_per_side": "1"}}
        request["parameter_ranges"]["mm_risk_pct"] = {"start": "1", "end": "8", "step": "1"}
        (output / "request.json").write_text(json.dumps(request, indent=2))
        results = benchmark(url, request, [count for count in (1, 4, 6, 7) if count <= MAX_WORKERS], repeats, output / "benchmark")
        for measurement in results["measurements"]:
            for trial in measurement["fingerprints"]:
                assert trial["metrics"]["trades_taken"] == 0
                assert Decimal(trial["metrics"]["total_net_pnl"]) == 0
                assert Decimal(trial["metrics"]["final_equity"]) == 10000
        # Also save actual all-hit reuse evidence on this same source and grid.
        # Benchmark runs deliberately bypass cache publication; seed once.
        import time
        jobs = []
        for _ in range(2):
            job = client.post("/api/optimizations", json={**request, "workers": 1, "reuse_results": True}).json()
            while job["status"] in ("queued", "running"):
                time.sleep(.1)
                job = client.get(f"/api/optimizations/{job['id']}").json()
            assert job["status"] == "complete", job
            jobs.append(job)
        assert jobs[1]["reused_trials"] == 8 and jobs[1]["worker_pids"] == []
        (output / "reuse.json").write_text(json.dumps(jobs, indent=2))
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.goto(url + "/#optimizations/" + jobs[1]["id"])
            expect(page.locator("#optimization-status")).to_contain_text("8 reused · 0 computed")
            expect(page.get_by_text("Reused saved trial", exact=True)).to_have_count(8)
            page.screenshot(path=str(output / "reused-results.png"), full_page=True)
            page.reload()
            expect(page.locator("#optimization-results tbody tr")).to_have_count(8)
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bars", type=int, default=20000)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    serve_review(args.output, lambda output, url: review(output, url, args.bars, args.repeats))

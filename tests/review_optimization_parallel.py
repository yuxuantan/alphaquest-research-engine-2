"""Retain real portal serial/process timing, exact parity and worker-overlap evidence.

.venv/bin/python tests/review_optimization_parallel.py --output artifacts/optimization-parallel-NEW
Uses labeled synthetic data and an owned temporary server; output must be new.
"""

import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import time

import httpx
from playwright.sync_api import sync_playwright, expect

from alphaquest.optimization import DEFAULT_WORKERS, MAX_WORKERS
from review_optimization_portal import serve_review


def review(output, url, bars, trials, workers):
    stamp = datetime(2026, 1, 5)
    lines = ["Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol"]
    for minute in range(bars):
        # Constant closes stay inside the [99, 102] opening range, so no ORB
        # entry exists. Indicators and the full normal report path still run.
        lines.append((stamp + timedelta(minutes=minute)).strftime("%m/%d/%Y,%H:%M") + ",100,102,99,101,1,1,0")
    source = output / "SYNTHETIC-parallel-benchmark.csv"
    source.write_text("\n".join(lines) + "\n")
    measurements = []
    with httpx.Client(base_url=url, timeout=120) as client, sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        page.locator("#csv-file").set_input_files(source)
        page.locator("#dataset-name").fill("SYNTHETIC parallel optimization benchmark")
        page.locator("#dataset-tick-size").fill("0.25")
        page.locator("#dataset-point-value").fill("10")
        page.locator("#validate-button").click()
        expect(page.locator("#validation-result")).to_contain_text("Validation passed", timeout=120000)
        page.locator("#save-button").click()
        expect(page.locator("#validation-result")).to_contain_text("Dataset saved", timeout=120000)
        dataset = client.get("/api/datasets").json()[0]
        for worker_count in (1, workers):
            page.goto(url + "/#optimizations")
            page.locator("#backtest-dataset").select_option(dataset["id"])
            page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
            expect(page.locator("#optimization-ranges tr")).to_have_count(32)
            page.get_by_label("Mm risk pct start", exact=True).fill("1")
            page.get_by_label("Mm risk pct end", exact=True).fill(str(trials))
            page.get_by_label("Mm risk pct step", exact=True).fill("1")
            page.locator("#optimization-workers").select_option(str(worker_count))
            page.locator("#optimization-reuse").uncheck()
            expect(page.locator("#optimization-count")).to_have_text(f"Total combinations: {trials} = {trials} backtests")
            page.screenshot(path=str(output / f"workers-{worker_count}-configured.png"), full_page=True)
            before = time.monotonic()
            page.locator("#start-backtest").click()
            expect(page).to_have_url(re.compile(r"/#optimizations/[a-f0-9]{32}$"))
            job_id = page.url.rsplit("/", 1)[1]
            snapshots = []
            deadline = time.monotonic() + 600
            while True:
                job = client.get(f"/api/optimizations/{job_id}").json()
                snapshots.append({key: job.get(key) for key in ("status", "stage", "completed_trials", "active_trials", "elapsed_seconds")})
                if job["status"] not in ("queued", "running"):
                    break
                assert time.monotonic() < deadline, "Benchmark timeout"
                page.wait_for_timeout(200)
            request_seconds = time.monotonic() - before
            assert job["status"] == "complete", job
            assert job["completed_trials"] == job["total_trials"] == trials
            expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=10000)
            expect(page.locator("#optimization-results tbody tr")).to_have_count(trials)
            rows = client.get(f"/api/optimizations/{job_id}/results").json()["items"]
            fingerprints = []
            for row in rows:
                assert row["metrics"]["trades_taken"] == 0
                assert Decimal(row["metrics"]["total_net_pnl"]) == 0
                assert Decimal(row["metrics"]["final_equity"]) == 10000
                assert row["metrics"]["win_rate_pct"] is None
                exports = {}
                for kind in ("trades", "equity"):
                    raw = client.get(f"/api/backtests/{row['run_id']}/exports/{kind}").content
                    exports[kind] = hashlib.sha256(raw).hexdigest()
                fingerprints.append({"trial": row["trial"], "parameters": row["parameters"], "metrics": row["metrics"], "csv_sha256": exports})
            with page.expect_download() as downloaded:
                page.locator("#optimization-download").click()
            downloaded.value.save_as(output / f"workers-{worker_count}-results.csv")
            page.screenshot(path=str(output / f"workers-{worker_count}-results.png"), full_page=True)
            page.reload()
            expect(page.locator("#optimization-results tbody tr")).to_have_count(trials)
            measurements.append({"workers": worker_count, "job": job, "rows": rows,
                                 "fingerprints": fingerprints, "request_to_completion_seconds": request_seconds,
                                 "progress_snapshots": snapshots})
        serial, parallel = measurements
        assert serial["fingerprints"] == parallel["fingerprints"]
        intervals = [row["execution"] for row in parallel["rows"]]
        overlapping = any(a["worker_pid"] != b["worker_pid"]
                          and max(a["started_at_utc"], b["started_at_utc"]) < min(a["finished_at_utc"], b["finished_at_utc"])
                          for a in intervals for b in intervals)
        assert len(parallel["job"]["worker_pids"]) > 1 and overlapping
        assert not errors, errors
        browser.close()
    verification = {"synthetic": True, "bars": bars, "trials_per_job": trials,
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "machine": {"platform": platform.platform(), "logical_cpus": os.cpu_count()},
                    "exact_serial_parallel_metrics_parameters_and_csv_match": True,
                    "multiple_child_processes_and_overlapping_trials": overlapping,
                    "expected": {"trades_per_trial": 0, "net_pnl_per_trial": "0", "final_equity": "10000",
                                 "reason": "Constant closes never break the synthetic opening range."},
                    "observed_speedup": serial["job"]["elapsed_seconds"] / parallel["job"]["elapsed_seconds"],
                    "measurements": measurements, "browser_errors": errors,
                    "timing_note": "One local serial/parallel pair, including process startup and report publication. No universal speedup claim."}
    (output / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(f"Serial {serial['job']['elapsed_seconds']:.3f}s; {workers} processes {parallel['job']['elapsed_seconds']:.3f}s; observed {verification['observed_speedup']:.2f}x.")
    print(f"PASS: {trials} trials each; exact metrics/parameter/CSV parity; actual child-process overlap; evidence: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bars", default=12000, type=int)
    parser.add_argument("--trials", default=8, type=int)
    parser.add_argument("--workers", default=DEFAULT_WORKERS, type=int)
    args = parser.parse_args()
    if args.bars < 1000 or not 2 <= args.trials <= 50 or not 2 <= args.workers <= MAX_WORKERS:
        parser.error(f"Use bars >= 1000, 2–50 trials and 2–{MAX_WORKERS} workers.")
    serve_review(args.output, lambda output, url: review(output, url, args.bars, args.trials, args.workers))


if __name__ == "__main__":
    main()

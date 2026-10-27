"""Retain an isolated, synthetic optimization demonstration through the normal UI.

.venv/bin/python tests/review_optimization_portal.py --output artifacts/optimization-review-NEW
The output directory must be new. The owned server is stopped on exit.
"""

import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path
import re
import socket
from threading import Thread
import time

import httpx
from playwright.sync_api import sync_playwright, expect
import uvicorn

from alphaquest.app import create_app


FIXTURE = Path(__file__).parent / "fixtures/backtest_contract/arithmetic_5m.csv"


def review(output, url):
    with sync_playwright() as runtime, httpx.Client(base_url=url) as client:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        page.locator("#csv-file").set_input_files(FIXTURE)
        page.locator("#dataset-name").fill("SYNTHETIC optimization arithmetic review")
        page.locator("#dataset-tick-size").fill("0.25")
        page.locator("#dataset-point-value").fill("10")
        page.locator("#validate-button").click()
        expect(page.locator("#validation-result")).to_contain_text("Validation passed")
        page.locator("#save-button").click()
        expect(page.locator("#validation-result")).to_contain_text("Dataset saved")
        dataset = client.get("/api/datasets").json()[0]
        page.get_by_role("link", name="Optimizations", exact=True).click()
        expect(page.locator("#optimization-ranges tr")).to_have_count(3)
        page.locator("#backtest-dataset").select_option(dataset["id"])
        page.locator("#backtest-slippage-ticks").fill("1")
        page.locator("#backtest-commission").fill("1")
        page.get_by_label("Hold minutes end", exact=True).fill("25")
        page.get_by_label("Hold minutes step", exact=True).fill("5")
        page.get_by_label("Contracts end", exact=True).fill("2")
        page.get_by_label("Contracts step", exact=True).fill("-1")
        page.locator("#start-backtest").click()
        expect(page.locator("#backtest-error")).to_contain_text("greater than")
        assert client.get("/api/optimizations").json()["total"] == 0
        page.screenshot(path=str(output / "invalid-grid.png"), full_page=True)
        page.get_by_label("Contracts end", exact=True).fill("3")
        page.get_by_label("Contracts step", exact=True).fill("1")
        expect(page.locator("#optimization-count")).to_have_text("Total combinations: 2 × 3 = 6 backtests")
        page.screenshot(path=str(output / "configured-grid.png"), full_page=True)
        page.locator("#start-backtest").click()
        expect(page).to_have_url(re.compile(r"/#optimizations/[a-f0-9]{32}$"))
        expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
        job_id = page.url.rsplit("/", 1)[1]
        job = client.get(f"/api/optimizations/{job_id}").json()
        assert job["completed_trials"] == job["total_trials"] == 6
        response = client.get(f"/api/optimizations/{job_id}/results")
        rows = response.json()["items"]
        observations = []
        for row in rows:
            q = row["parameters"]["contracts"]
            expected = {"total_net_pnl": 13*q, "total_gross_pnl": 15*q,
                        "total_commissions": 2*q, "total_slippage_cost": 5*q,
                        "final_equity": 10000+13*q, "trades_taken": 1, "winning_trades": 1,
                        "losing_trades": 0, "breakeven_trades": 0, "win_rate_pct": 100,
                        "max_drawdown_amount": 0, "max_drawdown_pct": 0,
                        "max_drawdown_duration_seconds": 0}
            for key, value in expected.items():
                assert Decimal(str(row["metrics"][key])) == value, (key, row)
            trade = client.get(f"/api/backtests/{row['run_id']}/trades").json()["items"][0]
            assert Decimal(trade["entry_fill_price"]) == Decimal("100.25")
            assert Decimal(trade["exit_fill_price"]) == Decimal("101.75")
            observations.append({"parameters": row["parameters"], "expected": expected, "actual": row["metrics"], "run_id": row["run_id"], "match": True})
        # Every result heading supports both directions through the real page.
        column_count = page.locator("#optimization-results th button").count()
        for column in range(column_count):
            button = page.locator("#optimization-results th button").nth(column)
            header = page.locator("#optimization-results th").nth(column)
            expected = "descending" if header.get_attribute("aria-sort") == "ascending" else "ascending"
            button.click()
            expect(header).to_have_attribute("aria-sort", expected)
            page.locator("#optimization-results th button").nth(column).click()
            expect(header).to_have_attribute("aria-sort", "ascending" if expected == "descending" else "descending")
        page.get_by_role("button", name="Total net pnl", exact=False).click()
        expect(page.locator("#optimization-results th[aria-sort='ascending']")).to_contain_text("Total net pnl")
        page.get_by_role("button", name="Total net pnl", exact=False).click()
        expect(page.locator("#optimization-results tbody tr").first.locator("td").nth(4)).to_have_text("39.00")
        with page.expect_download() as downloaded:
            page.locator("#optimization-download").click()
        downloaded.value.save_as(output / "results-descending.csv")
        with (output / "results-descending.csv").open() as stream:
            assert [Decimal(row["total_net_pnl"]) for row in csv.DictReader(stream)] == [39, 39, 26, 26, 13, 13]
        page.screenshot(path=str(output / "results-desktop.png"), full_page=True)
        detail_url = page.url
        page.locator("#optimization-results tbody tr").first.get_by_role("link").click()
        expect(page.locator("#backtest-completion")).to_be_visible()
        page.screenshot(path=str(output / "trial-backtest-report.png"), full_page=True)
        page.goto(detail_url)
        page.reload()
        expect(page.locator("#optimization-status")).to_contain_text("COMPLETE")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / "results-mobile.png"), full_page=True)
        # Reproduce the requested 2 x 4 x 3 example through the same UI.
        page.set_viewport_size({"width": 1440, "height": 1100})
        page.goto(url + "/#optimizations")
        expect(page.locator("#optimization-ranges tr")).to_have_count(3)
        page.locator("#backtest-dataset").select_option(dataset["id"])
        for name, start_value, end_value, step_value, expected_count in (
            ("Green bar count", 2, 3, 1, 2),
            ("Hold minutes", 10, 25, 5, 4),
            ("Contracts", 1, 5, 2, 3),
        ):
            page.get_by_label(name + " start", exact=True).fill(str(start_value))
            page.get_by_label(name + " end", exact=True).fill(str(end_value))
            page.get_by_label(name + " step", exact=True).fill(str(step_value))
            count_input = page.get_by_label(name + " step count", exact=True)
            expect(count_input).to_have_value(str(expected_count))
            assert count_input.get_attribute("readonly") is not None
        expect(page.locator("#optimization-count")).to_have_text("Total combinations: 2 × 4 × 3 = 24 backtests")
        page.screenshot(path=str(output / "grid-24-configured.png"), full_page=True)
        page.locator("#start-backtest").click()
        expect(page).to_have_url(re.compile(r"/#optimizations/[a-f0-9]{32}$"))
        expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
        product_id = page.url.rsplit("/", 1)[1]
        product_job = client.get(f"/api/optimizations/{product_id}").json()
        product_rows = client.get(f"/api/optimizations/{product_id}/results").json()["items"]
        expected_sets = {(a, b, c) for a in (2, 3) for b in (10, 15, 20, 25) for c in (1, 3, 5)}
        assert {tuple(row["parameters"].values()) for row in product_rows} == expected_sets
        assert product_job["total_trials"] == product_job["completed_trials"] == 24
        expect(page.locator("#optimization-results tbody tr")).to_have_count(24)
        page.screenshot(path=str(output / "grid-24-results.png"), full_page=True)
        (output / "grid-24-verification.json").write_text(json.dumps({
            "synthetic": True, "expected_step_counts": [2, 4, 3], "expected_total": 24,
            "job": product_job, "rows": product_rows, "all_parameter_sets_match": True,
        }, indent=2) + "\n")
        assert not errors, errors
        browser.close()
    (output / "job.json").write_text(json.dumps(job, indent=2) + "\n")
    (output / "verification.json").write_text(json.dumps({
        "synthetic": True, "optimization_id": job_id, "portal_path": f"/#optimizations/{job_id}",
        "independent_arithmetic": "Per contract: (101.75 - 100.25) * 10 - 2 * 1 = 13 CU; each hold uses the final observed bar.",
        "observations": observations, "invalid_step_rejection_saved_no_job": True,
        "sortable_columns_both_directions": column_count, "csv_order_net_descending": [39,39,26,26,13,13],
        "reopened_after_reload": True, "mobile_overflow": False, "browser_errors": errors,
    }, indent=2) + "\n")
    print(f"PASS: 6 combinations, independent net 13/26/39 CU; {column_count} sortable columns; CSV, report links, reload and mobile verified; 2 × 4 × 3 = 24 additional backtests verified.")
    print(f"Evidence: {output}")


def serve_review(output, review_function=review):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    app = create_app(output / "datasets.sqlite3")
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", loop="asyncio"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    worker = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert worker.is_alive() and time.monotonic() < deadline
            time.sleep(.01)
        review_function(output, url)
    finally:
        server.should_exit = True
        worker.join(timeout=15)
        sock.close()
        assert not worker.is_alive(), "Review server did not stop"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    serve_review(parser.parse_args().output)


if __name__ == "__main__":
    main()

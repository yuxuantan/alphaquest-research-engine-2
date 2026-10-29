"""Run the report workflow in Chromium and retain review data/screenshots.

.venv/bin/python tests/review_report_portal.py --output artifacts/report-screen-review
The output directory must be new. No existing workspace datasets are touched.
"""

from test_backtests_browser import set_parameter

import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import socket
from threading import Thread
import time

import httpx
from playwright.sync_api import sync_playwright, expect
import uvicorn

from alphaquest.app import create_app
from review_execution import fixtures, FIXTURES
from review_reports import _equal_record


def configure(page, saved, parameters, settings):
    page.locator("#backtest-dataset").select_option(saved["id"])
    page.locator("#backtest-strategy").select_option("consecutive_green_hold")
    for name, value in parameters.items():
        set_parameter(page, name, str(value))
    ids = {"initial_capital": "initial-capital", "tick_size": "tick-size", "point_value": "point-value",
           "slippage_ticks": "slippage-ticks", "commission_per_contract_per_side": "commission"}
    for name, value in settings.items():
        if name in ("tick_size", "point_value"): continue
        page.locator("#backtest-" + ids[name]).fill(str(value))


def run(page):
    snapshots = []
    page.locator("#start-backtest").click()
    deadline = time.monotonic() + 120
    while not page.locator("#backtest-completion").is_visible():
        assert time.monotonic() < deadline, "Report timeout"
        error = page.locator("#backtest-error")
        assert not error.is_visible(), error.inner_text() if error.is_visible() else ""
        snapshots.append({"stage": page.locator("#backtest-progress-title").text_content(),
                          "bars": page.locator("#backtest-progress-detail").text_content()})
        page.wait_for_timeout(100)
    return page.url.split("/")[-1], snapshots


def screenshot(page, path):
    # Paint the horizontally scrollable table before Chromium's full-page
    # capture; a viewport resize can otherwise leave offscreen layers blank.
    page.locator(".report-table-scroll").scroll_into_view_if_needed()
    page.wait_for_timeout(50)
    page.screenshot(path=str(path), full_page=True)


def review(output, url):
    reviews = []
    with httpx.Client(base_url=url, timeout=120) as client, sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        for case in fixtures():
            saved_response = client.post("/api/datasets", params={"filename": case["csv"], "name": case["id"], "source_timezone": case["source_timezone"], **{k: case["execution_settings"][k] for k in ("tick_size", "point_value")}}, content=(FIXTURES / case["csv"]).read_bytes())
            assert saved_response.status_code == 201, saved_response.text
            saved = saved_response.json()
            page.goto(url + "/#backtests")
            expect(page.locator("#optimization-ranges tr")).to_have_count(3)
            configure(page, saved, case["strategy_parameters"], case["execution_settings"])
            run_id, progress = run(page)
            record = client.get("/api/backtests/" + run_id).json()
            trades = client.get(f"/api/backtests/{run_id}/trades").json()["items"]
            preview = client.get(f"/api/backtests/{run_id}/chart").json()
            _equal_record(record["summary"], case["expected_summary"])
            assert len(trades) == len(case["expected_trades"])
            for observed, expected in zip(trades, case["expected_trades"], strict=True):
                _equal_record(observed, expected)
                row = page.locator(f"tr[data-trade='{observed['trade_number']}']")
                for key in ("entry_fill_price", "exit_fill_price", "contracts", "gross_pnl", "total_commissions", "net_pnl", "actual_holding_minutes", "exit_reason"):
                    expect(row.locator(f"[data-field='{key}']")).to_have_text(str(observed[key]))
            expected_curve = [{"trade_number": 0, "exit_time_utc": None, "net_pnl": "0", "equity": case["execution_settings"]["initial_capital"]}] + [
                {"trade_number": trade["trade_number"], "exit_time_utc": trade["exit_time_utc"], "net_pnl": trade["net_pnl"],
                 "equity": case["expected_equity"][trade["exit_bar_number"]]["equity"]} for trade in case["expected_trades"]]
            assert len(preview["items"]) == len(expected_curve)
            for actual, expected in zip(preview["items"], expected_curve, strict=True):
                _equal_record(actual, expected)
            assert Decimal(page.locator("#report-net").inner_text()) == Decimal(case["expected_summary"]["total_net_pnl"])
            assert Decimal(page.locator("#report-drawdown-amount").inner_text()) == Decimal(case["expected_summary"]["max_drawdown_amount"])
            assert Decimal(page.locator("#report-drawdown-pct").inner_text().removesuffix("%")) == Decimal(case["expected_summary"]["max_drawdown_pct"])
            for kind in ("trades", "equity"):
                with page.expect_download() as downloaded:
                    page.locator(f"#report-{kind}-download").click()
                assert Path(downloaded.value.path()).read_bytes() == (output / "backtest_runs" / run_id / f"{kind}.csv").read_bytes()
            page.reload()
            expect(page.locator("#backtest-completion")).to_be_visible()
            expect(page.locator("#report-run-id")).to_contain_text(run_id)
            page.get_by_role("link", name="Backtests", exact=True).click()
            page.locator(f"#completed-runs-list a[href$='{run_id}']").click()
            expect(page.locator("#backtest-completion")).to_be_visible()
            if case["id"] in ("arithmetic_5m", "no_trades", "gap_deadline", "end_of_data"):
                screenshot(page, output / (case["id"] + "-desktop.png"))
            if case["id"] == "arithmetic_5m":
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                screenshot(page, output / "report-mobile.png")
                page.set_viewport_size({"width": 1440, "height": 1100})
                page.locator("details.report-panel summary").click()
                screenshot(page, output / "report-settings.png")
            reviews.append({"fixture": case["id"], "run_id": run_id, "expected_summary": case["expected_summary"],
                            "actual_summary": record["summary"], "expected_trades": case["expected_trades"], "actual_trades": trades,
                            "chart_matches_every_trade_close_equity_point": True, "downloads_match_saved_bytes": True,
                            "refreshed_and_reopened": True, "progress_snapshots": progress, "match": True})
            s = record["summary"]
            print(f"{case['id']:26} {s['trades_taken']:>2} trades  net {s['total_net_pnl']:>8} / expected {case['expected_summary']['total_net_pnl']:>5}  PASS")
        # Larger, independent arithmetic: every bar is green with the same close;
        # N=1, hold=1, zero costs => 10,001 flat-price breakeven trades.
        bars = 20_002
        start = datetime(2026, 1, 5)
        lines = ["Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol"]
        for minute in range(bars):
            stamp = (start + timedelta(minutes=minute)).strftime("%m/%d/%Y,%H:%M")
            lines.append(stamp + ",100,101,100,101,0,0,0")
        saved = client.post("/api/datasets", params={"filename": "large.csv", "name": "Large synthetic 20002", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10"}, content=("\n".join(lines) + "\n").encode()).json()
        page.goto(url + "/#backtests")
        expect(page.locator("#optimization-ranges tr")).to_have_count(3)
        settings = {"initial_capital": "10000", "tick_size": "0.25", "point_value": "10", "slippage_ticks": 0, "commission_per_contract_per_side": "0"}
        configure(page, saved, {"green_bar_count": 1, "hold_minutes": 1, "contracts": 1}, settings)
        responses = []
        page.on("response", lambda response: responses.append(response) if "/api/" in response.url else None)
        run_id, progress = run(page)
        expect(page.locator("#report-trades")).to_have_text("10,001")
        assert Decimal(page.locator("#report-net").inner_text()) == 0
        chart_count = int(page.locator("#equity-chart").get_attribute("data-points"))
        assert chart_count <= 1000
        expect(page.locator("#report-trades-body tr")).to_have_count(50)
        page.locator("#trades-next").click()
        expect(page.locator("#report-trades-count")).to_have_text("51–100 of 10,001 trades")
        screenshot(page, output / "large-report.png")
        total_trades = 0
        all_net = Decimal(0)
        for offset in range(0, 10001, 1000):
            batch = client.get(f"/api/backtests/{run_id}/trades?offset={offset}&limit=1000").json()["items"]
            assert all(Decimal(t["net_pnl"]) == 0 and t["actual_holding_minutes"] == "1" for t in batch)
            total_trades += len(batch)
            all_net += sum((Decimal(t["net_pnl"]) for t in batch), Decimal(0))
        assert total_trades == 10001 and all_net == 0
        page_counts = [len(response.json()["items"]) for response in responses if "/trades?" in response.url]
        progress_responses = [response for response in responses if "/api/progress/" in response.url and response.status == 200]
        timings = [response.request.timing["responseEnd"] for response in progress_responses]
        assert progress_responses and max(page_counts) <= 50
        large = {"run_id": run_id, "bars": bars, "expected_trades": 10001, "actual_trades": total_trades,
                 "expected_net": "0", "actual_net": str(all_net), "chart_points": chart_count, "chart_total": total_trades + 1,
                 "browser_trade_page_counts": page_counts, "progress_poll_count": len(progress_responses),
                 "max_progress_response_ms": max(timings), "progress_snapshots": progress, "match": True}
        page.get_by_role("link", name="Backtests", exact=True).click()
        expect(page.locator("#completed-runs-list a")).to_have_count(10)
        page.locator("#completed-runs").scroll_into_view_if_needed()
        page.screenshot(path=str(output / "completed-reports.png"), full_page=True)
        assert not errors, errors
        context.close()
        browser.close()
    (output / "verification.json").write_text(json.dumps({"fixtures": reviews, "large_run": large, "browser_errors": errors}, indent=2) + "\n")
    print(f"Large run: {bars} bars, {total_trades} trades, {chart_count} chart points, pages {page_counts}; net 0; PASS")
    print(f"Review artifacts: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
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
        review(output, url)
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        sock.close()
        assert not worker.is_alive()


if __name__ == "__main__":
    main()

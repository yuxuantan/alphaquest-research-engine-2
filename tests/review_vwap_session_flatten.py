"""Retain synthetic normal/early-close demonstrations through the normal UI.

.venv/bin/python tests/review_vwap_session_flatten.py --output artifacts/vwap-session-flatten-review-NEW
Uses an isolated normal library; the temporary server shuts down on exit.
"""

import argparse
from decimal import Decimal
import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect

from review_optimization_portal import serve_review
from test_inferred_session_close import csv_bytes, session_rows


def review(output, url):
    observations = []
    with sync_playwright() as runtime, httpx.Client(base_url=url, timeout=90) as client:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(45000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        for name, close, cutoff, utc in (("normal", (16, 0), "15:55", "21:55"),
                                          ("noon", (12, 0), "11:55", "17:55"),
                                          ("1215", (12, 15), "12:10", "18:10")):
            raw = csv_bytes(session_rows(close=close))
            source = output / f"SYNTHETIC-{name}.csv"
            source.write_bytes(raw)
            page.goto(url)
            page.locator("#csv-file").set_input_files(source)
            page.locator("#dataset-name").fill(f"SYNTHETIC VWAP {name} session close")
            page.locator("#source-timezone").select_option("UTC")
            page.locator("#dataset-tick-size").fill("0.25")
            page.locator("#dataset-point-value").fill("20")
            page.locator("#validate-button").click()
            expect(page.locator("#validation-result")).to_contain_text("Validation passed")
            page.locator("#save-button").click()
            expect(page.locator("#validation-result")).to_contain_text("Dataset saved")
            dataset = next(d for d in client.get("/api/datasets").json() if d["name"] == f"SYNTHETIC VWAP {name} session close")
            page.get_by_role("link", name="Backtests", exact=True).click()
            page.locator("#backtest-dataset").select_option(dataset["id"])
            page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
            page.locator("#strategy-stop_swing_len").fill("1")
            page.locator("#strategy-target_swing_len").fill("1")
            page.locator("#strategy-use_adx_elev").uncheck()
            page.locator("#strategy-use_adx_decay").uncheck()
            page.locator("#strategy-use_eod_flat").check()
            page.locator("#backtest-slippage-ticks").fill("1")
            page.locator("#backtest-commission").fill("1")
            expect(page.locator("#backtest-fill-assumption")).to_contain_text("BACKTEST LOOKAHEAD")
            page.screenshot(path=str(output / f"{name}-configuration.png"), full_page=True)
            with page.expect_response(lambda r: "/api/backtests?" in r.url and r.request.method == "POST", timeout=90000) as completed:
                page.locator("#start-backtest").click()
            record = completed.value.json()
            assert completed.value.status == 201, record
            run_id = record["id"]
            expect(page.locator("#backtest-completion")).to_be_visible()
            trade = client.get(f"/api/backtests/{run_id}/trades").json()["items"][0]
            expected_exit = f"2026-01-05T{utc}:00Z"
            assert trade["exit_time_utc"] == expected_exit and trade["exit_reason"] == "eod_flat"
            assert Decimal(trade["entry_fill_price"]) == Decimal("115.25")
            assert Decimal(trade["exit_fill_price"]) == Decimal("117.75")
            assert Decimal(trade["total_commissions"]) == 2
            assert Decimal(record["summary"]["total_net_pnl"]) == 48
            assert client.get(f"/api/datasets/{dataset['id']}/csv").content == raw
            for kind in ("trades", "equity", "report"):
                response = client.get(f"/api/backtests/{run_id}/exports/{kind}")
                assert response.status_code == 200
                (output / f"{name}-{kind}.{'json' if kind == 'report' else 'csv'}").write_bytes(response.content)
            settings = page.locator("#backtest-completion-content")
            settings.evaluate("el => { const parent=el.closest('details'); if(parent) parent.open=true; }")
            expect(settings.locator("[data-setting='session_flattening']")).to_contain_text("1 inferred sessions")
            page.screenshot(path=str(output / f"{name}-report.png"), full_page=True)
            page.reload()
            expect(page.locator("#backtest-completion-content [data-setting='session_flattening']")).to_contain_text("Backtest lookahead")
            observations.append({"synthetic": True, "case": name, "dataset_id": dataset["id"], "run_id": run_id,
                "portal_path": f"/#backtests/report/{run_id}", "expected_close_ct": "%02d:%02d" % close,
                "expected_cutoff_ct": cutoff, "expected_exit_time_utc": expected_exit,
                "expected_net_pnl": "48", "actual_trade": trade,
                "actual_net_pnl": record["summary"]["total_net_pnl"],
                "session_flattening": record["run_metadata"]["strategy"]["session_flattening"],
                "source_unchanged": True, "reopened_after_reload": True})
            print(f"PASS {name}: inferred close {'%02d:%02d' % close} -> exit {cutoff} CT; net48 CU; run {run_id}")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / "report-mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()
    (output / "verification.json").write_text(json.dumps({"synthetic": True,
        "arithmetic": "(117.75 - 115.25) * 20 - (1 + 1) = 48 CU",
        "observations": observations, "browser_errors": errors}, indent=2) + "\n")
    print(f"Evidence retained: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    serve_review(parser.parse_args().output, review)

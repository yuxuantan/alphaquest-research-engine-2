"""Report workflow in Chromium, using real saved datasets and replay outputs."""

from datetime import datetime, timedelta
from decimal import Decimal
import json
import re
from threading import Event

import httpx
import pytest

from test_backtests_browser import browser, page, portal, prepare, playwright, FIXTURES
from alphaquest.strategies import consecutive_green_hold as sample
from review_execution import fixtures
from review_reports import _equal_record


@pytest.mark.parametrize("case", fixtures(), ids=lambda case: case["id"])
def test_portal_report_matches_hand_checked_fixture_and_reopens(page, portal, case):
    saved = portal["saved"].get(case["id"])
    if saved is None:
        with httpx.Client(base_url=portal["url"]) as client:
            response = client.post("/api/datasets", params={"filename": case["csv"], "name": case["id"], "source_timezone": case["source_timezone"]}, content=(FIXTURES / case["csv"]).read_bytes())
            assert response.status_code == 201, response.text
            saved = response.json()
    prepare(page, portal)
    page.locator("#backtest-dataset").select_option(saved["id"])
    for key, value in case["strategy_parameters"].items():
        page.locator(f"#strategy-{key}").fill(str(value))
    ids = {"initial_capital": "initial-capital", "tick_size": "tick-size", "point_value": "point-value", "slippage_ticks": "slippage-ticks", "commission_per_contract_per_side": "commission"}
    for key, value in case["execution_settings"].items():
        page.locator("#backtest-" + ids[key]).fill(str(value))
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    run_id = page.url.split("/")[-1]
    with httpx.Client(base_url=portal["url"]) as client:
        record = client.get("/api/backtests/" + run_id).json()
        _equal_record(record["summary"], case["expected_summary"])
        trades = client.get(f"/api/backtests/{run_id}/trades").json()["items"]
    assert Decimal(page.locator("#report-net").inner_text()) == Decimal(case["expected_summary"]["total_net_pnl"])
    playwright.expect(page.locator("#report-trades")).to_have_text(str(len(case["expected_trades"])))
    playwright.expect(page.locator("#report-win-rate")).to_have_text("N/A" if not trades else case["expected_summary"]["win_rate_pct"] + "%")
    assert Decimal(page.locator("#report-drawdown-amount").inner_text()) == Decimal(case["expected_summary"]["max_drawdown_amount"])
    assert Decimal(page.locator("#report-drawdown-pct").inner_text().removesuffix("%")) == Decimal(case["expected_summary"]["max_drawdown_pct"])
    expected_duration = {"end_of_data": "4m", "last_bar_entry": "2m"}.get(case["id"], "0s")
    playwright.expect(page.locator("#report-drawdown-duration")).to_have_text(expected_duration)
    for actual, expected in zip(trades, case["expected_trades"], strict=True):
        _equal_record(actual, expected)
        row = page.locator(f"#report-trades-body tr[data-trade='{actual['trade_number']}']")
        for key in ("entry_fill_price", "exit_fill_price", "contracts", "gross_pnl", "total_commissions", "net_pnl", "actual_holding_minutes", "exit_reason"):
            playwright.expect(row.locator(f"[data-field='{key}']")).to_have_text(str(actual[key]))
        for key in ("entry_time_utc", "exit_time_utc"):
            playwright.expect(row.locator(f"[data-field='{key}']")).to_have_text(actual[key].replace("T", " ").replace("Z", ""))
    playwright.expect(page.locator("#equity-chart")).to_have_attribute("data-total", str(len(trades) + 1))
    playwright.expect(page.locator("#equity-chart-title")).to_have_text("Trade-close equity · CU")
    page.locator("#equity-chart").focus()
    page.keyboard.press("Home")
    playwright.expect(page.locator("#chart-readout")).to_contain_text("Initial balance")
    if case["id"] == "arithmetic_5m":
        page.keyboard.press("ArrowRight")
        playwright.expect(page.locator("#chart-readout")).to_contain_text("Trade 1 · Equity 10026.00 CU · Trade net P&L 26.00 CU")
    if case["id"] == "no_pyramiding":
        for equity in ("10020.00", "10040.00"):
            page.keyboard.press("ArrowRight")
            playwright.expect(page.locator("#chart-readout")).to_contain_text(f"Equity {equity} CU")
    with page.expect_download() as downloaded:
        page.locator("#report-trades-download").click()
    folder = portal["app"].state.runs.root / run_id
    assert downloaded.value.suggested_filename == f"{run_id}-trades.csv"
    assert open(downloaded.value.path(), "rb").read() == (folder / "trades.csv").read_bytes()
    with page.expect_download() as downloaded:
        page.locator("#report-equity-download").click()
    assert open(downloaded.value.path(), "rb").read() == (folder / "equity.csv").read_bytes()
    page.reload()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    playwright.expect(page.locator("#report-run-id")).to_contain_text(run_id)
    page.get_by_role("link", name="Backtests", exact=True).click()
    page.locator(f"#completed-runs-list a[href$='{run_id}']").click()
    playwright.expect(page.locator("#report-run-id")).to_contain_text(run_id)
    page.locator("details.report-panel summary").click()
    playwright.expect(page.locator("#backtest-completion-content")).to_contain_text(saved["source_timezone"])
    playwright.expect(page.locator("#backtest-completion-content")).to_contain_text(saved["sha256"])
    playwright.expect(page.locator("#backtest-completion-content")).to_contain_text("Bar close")
    for key, value in {**case["strategy_parameters"], **case["execution_settings"]}.items():
        playwright.expect(page.locator(f"[data-setting='{key}'] dd")).to_have_text(str(value))


def test_large_run_progress_bounded_chart_and_trade_pagination(page, portal, monkeypatch):
    total = 20_002
    start = datetime(2026, 1, 5)
    lines = ["Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol"]
    for i in range(total):
        timestamp = (start + timedelta(minutes=i)).strftime("%m/%d/%Y,%H:%M")
        lines.append(timestamp + ",100,101,100,101,0,0,0")
    with httpx.Client(base_url=portal["url"]) as client:
        saved = client.post("/api/datasets", params={"filename": "large.csv", "name": "Large synthetic", "source_timezone": "UTC"}, content=("\n".join(lines) + "\n").encode()).json()
    paused, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar

    def pause(self, bar, position):
        if bar.bar_number == 1001:
            paused.set()
            assert release.wait(10)
        return original(self, bar, position)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", pause)
    prepare(page, portal)
    page.locator("#backtest-dataset").select_option(saved["id"])
    for field in ("green_bar_count", "hold_minutes", "contracts"):
        page.locator("#strategy-" + field).fill("1")
    page.locator("#backtest-slippage-ticks").fill("0")
    page.locator("#backtest-commission").fill("0")
    responses = []
    page.on("response", lambda response: responses.append(response) if "/api/backtests/" in response.url else None)
    page.locator("#start-backtest").click()
    try:
        assert paused.wait(10)
        playwright.expect(page.locator("#backtest-progress-detail")).to_have_text("1,000 / 20,002 bars processed")
        # The server can still serve requests while the replay worker is paused.
        with httpx.Client(base_url=portal["url"], timeout=2) as client:
            assert client.get("/api/strategies").status_code == 200
        playwright.expect(page.locator("#start-backtest")).to_be_disabled()
    finally:
        release.set()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible(timeout=30000)
    playwright.expect(page.locator("#report-trades")).to_have_text("10,001")
    assert Decimal(page.locator("#report-net").inner_text()) == 0
    assert int(page.locator("#equity-chart").get_attribute("data-points")) <= 1000
    playwright.expect(page.locator("#equity-chart")).to_have_attribute("data-total", "10002")
    playwright.expect(page.locator("#chart-note")).to_contain_text("Min/max")
    playwright.expect(page.locator("#report-trades-body tr")).to_have_count(50)
    playwright.expect(page.locator("#report-trades-count")).to_have_text("1–50 of 10,001 trades")
    page.locator("#trades-next").click()
    playwright.expect(page.locator("#report-trades-count")).to_have_text("51–100 of 10,001 trades")
    playwright.expect(page.locator("#report-trades-body tr").first).to_have_attribute("data-trade", "51")
    page.locator("#trades-previous").click()
    playwright.expect(page.locator("#report-trades-body tr").first).to_have_attribute("data-trade", "1")
    for response in responses:
        if "/chart?" in response.url:
            assert len(response.json()["items"]) <= 1000
        elif "/trades?" in response.url:
            assert len(response.json()["items"]) <= 50
        assert "/equity?" not in response.url
    page.set_viewport_size({"width": 390, "height": 844})
    playwright.expect(page.locator("#equity-chart")).not_to_have_attribute("viewBox", re.compile(r"0 0 [1-9]\d{3,} 300"))
    assert float(page.locator("#equity-chart").get_attribute("viewBox").split()[2]) <= 390
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_report_loading_errors_retry_and_history_pagination(page, portal):
    prepare(page, portal)
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    url = page.url
    with httpx.Client(base_url=portal["url"]) as client:
        record = client.get("/api/backtests/" + url.split("/")[-1]).json()
    # Populate only catalogue entries for the history paging check; none of the
    # test-only rows is opened as a report.
    with portal["app"].state.runs.connect() as connection:
        for i in range(26):
            row = {**record, "id": f"{i:032x}"}
            connection.execute("INSERT INTO runs VALUES (?, ?, ?)", (row["id"], "2020-01-01T00:00:00Z", json.dumps(row)))
    page.get_by_role("link", name="Backtests", exact=True).click()
    playwright.expect(page.locator("#completed-runs-list a")).to_have_count(25)
    page.locator("#runs-next").click()
    playwright.expect(page.locator("#completed-runs-list a")).to_have_count(2)
    page.locator("#runs-previous").click()
    playwright.expect(page.locator("#completed-runs-list a")).to_have_count(25)
    page.route("**/chart?*", lambda route: route.fulfill(status=500, json={"detail": "Saved chart unavailable"}))
    page.goto(url)
    playwright.expect(page.locator("#report-status")).to_contain_text("Saved chart unavailable")
    playwright.expect(page.locator("#backtest-completion")).to_be_hidden()
    page.unroute("**/chart?*")
    page.reload()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    page.goto(portal["url"] + "/#backtests/report/" + "f" * 32)
    playwright.expect(page.locator("#report-status")).to_contain_text("Completed backtest not found")

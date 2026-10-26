"""Optimization through the real shared backtest form and durable portal table."""

import re
from threading import Event

import pytest

from test_backtests_browser import browser, page, portal, playwright
from alphaquest.strategies import consecutive_green_hold as sample


def prepare(page, portal):
    page.goto(portal["url"] + "/#optimizations")
    playwright.expect(page.locator("#optimization-ranges tr")).to_have_count(3)
    page.locator("#optimization-workers").select_option("1")
    page.locator("#backtest-dataset").select_option(portal["saved"]["arithmetic_5m"]["id"])
    page.locator("#backtest-slippage-ticks").fill("1")
    page.locator("#backtest-commission").fill("1")
    page.get_by_label("Contracts end", exact=True).fill("3")
    playwright.expect(page.locator("#optimization-count")).to_have_text("Total combinations: 3 = 3 backtests")


def run(page):
    page.locator("#start-backtest").click()
    playwright.expect(page).to_have_url(re.compile(r"/#optimizations/[a-f0-9]{32}$"))
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(3)


def test_grid_run_sort_export_reopen_and_normal_report(page, portal, tmp_path):
    prepare(page, portal)
    run(page)
    url = page.url
    rows = page.locator("#optimization-results tbody tr")
    playwright.expect(rows.nth(0).locator("td").nth(3)).to_have_text("1")
    playwright.expect(rows.nth(0).locator("td").nth(4)).to_have_text("13.00")
    page.get_by_role("button", name="Total net pnl", exact=False).click()
    playwright.expect(page.locator('#optimization-results th[aria-sort="ascending"]')).to_contain_text("Total net pnl")
    page.get_by_role("button", name="Total net pnl", exact=False).click()
    playwright.expect(rows.nth(0).locator("td").nth(4)).to_have_text("39.00")
    playwright.expect(page.locator('#optimization-results th[aria-sort="descending"]')).to_contain_text("Total net pnl")
    with page.expect_download() as downloaded:
        page.locator("#optimization-download").click()
    text = __import__("pathlib").Path(downloaded.value.path()).read_text()
    assert "39.00" in text and "13.00" in text
    report_link = rows.nth(0).get_by_role("link")
    run_id = report_link.inner_text()
    report_link.click()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    playwright.expect(page.locator("#report-run-id")).to_contain_text(run_id)
    playwright.expect(page.locator("#report-summary")).to_contain_text("39.00")
    page.goto(url)
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE")
    page.reload()
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(3)
    page.get_by_role("link", name="Optimizations", exact=True).click()
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(1)
    page.locator("#optimization-results tbody a").click()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE")
    assert page.locator("#backtest-setup").is_hidden()


def test_invalid_integer_grid_is_rejected_without_jobs_and_drafts_persist(page, portal):
    prepare(page, portal)
    page.get_by_label("Contracts end", exact=True).fill("2")
    page.get_by_label("Contracts step", exact=True).fill("-1")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-error")).to_contain_text("greater than")
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    assert page.request.get(portal["url"] + "/api/optimizations").json()["total"] == 0
    page.get_by_role("link", name="Datasets", exact=True).click()
    page.get_by_role("link", name="Optimizations", exact=True).click()
    playwright.expect(page.get_by_label("Contracts end", exact=True)).to_have_value("2")
    page.get_by_role("link", name="Backtests", exact=True).click()
    playwright.expect(page.locator("#strategy-contracts")).to_be_enabled()
    playwright.expect(page.locator("#optimization-settings")).to_be_hidden()


def test_mobile_grid_and_results_do_not_expand_page(page, portal):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(portal["url"])
    page.get_by_role("link", name="Optimizations", exact=True).click()
    playwright.expect(page.locator("#optimization-settings")).to_be_visible()
    prepare(page, portal)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    run(page)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator("#optimization-results").evaluate("table => table.scrollWidth > table.parentElement.clientWidth")


def test_running_job_remains_visible_after_reload_and_duplicate_submit_is_blocked(page, portal, monkeypatch):
    entered, release = Event(), Event()
    original = sample.ConsecutiveGreenHold.on_bar
    def paused(self, bar, position):
        if self.parameters.contracts == 1 and bar.bar_number == 2:
            entered.set()
            assert release.wait(15)
        return original(self, bar, position)
    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", paused)
    prepare(page, portal)
    requests = []
    page.on("request", lambda request: requests.append(request) if request.method == "POST" and request.url.endswith("/api/optimizations") else None)
    try:
        page.locator("#backtest-form").evaluate("form => {for(let i=0;i<3;i++) form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));}")
        assert entered.wait(5)
        playwright.expect(page.locator("#optimization-status")).to_contain_text("RUNNING")
        assert len(requests) == 1
        page.reload()
        playwright.expect(page.locator("#optimization-status")).to_contain_text("RUNNING")
    finally:
        release.set()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)


def test_vwap_range_controls_include_boolean_and_decimal_endpoints(page, portal):
    prepare(page, portal)
    page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
    playwright.expect(page.locator("#optimization-ranges tr")).to_have_count(32)
    page.get_by_label("Trade shorts start", exact=True).select_option("false")
    page.get_by_label("Trade shorts end", exact=True).select_option("true")
    playwright.expect(page.get_by_label("Trade shorts step count", exact=True)).to_have_value("2")
    page.get_by_label("Mm risk pct start", exact=True).fill("1.1")
    page.get_by_label("Mm risk pct end", exact=True).fill("1.3")
    page.get_by_label("Mm risk pct step", exact=True).fill("0.1")
    playwright.expect(page.locator("#optimization-count")).to_have_text("Total combinations: 3 × 2 = 6 backtests")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
    response = page.request.get(portal["url"] + "/api/optimizations").json()["items"][0]
    assert response["axes"]["trade_shorts"] == [False, True]
    assert response["axes"]["mm_risk_pct"] == ["1.1", "1.2", "1.3"]
    assert response["total_trials"] == 6


def test_adx_boolean_endpoints_auto_count_run_and_reopen(page, portal, tmp_path):
    import json

    prepare(page, portal)
    page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
    start = page.get_by_label("Use adx elev start", exact=True)
    end = page.get_by_label("Use adx elev end", exact=True)
    count = page.get_by_label("Use adx elev step count", exact=True)
    playwright.expect(start).to_have_value("true")
    playwright.expect(end).to_have_value("true")
    playwright.expect(count).to_have_value("1")
    assert count.get_attribute("readonly") is not None
    end.select_option("false")
    playwright.expect(count).to_have_value("2")
    playwright.expect(page.locator("#optimization-count")).to_have_text("Total combinations: 2 = 2 backtests")
    start.select_option("false")
    playwright.expect(count).to_have_value("1")
    start.select_option("true")
    playwright.expect(count).to_have_value("2")
    # Switching strategies retains the categorical range and recomputes count.
    page.locator("#backtest-strategy").select_option("consecutive_green_hold")
    page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
    playwright.expect(start).to_have_value("true")
    playwright.expect(end).to_have_value("false")
    playwright.expect(count).to_have_value("2")
    page.screenshot(path=str(tmp_path / "adx-boolean-configured.png"), full_page=True)
    page.locator("#start-backtest").click()
    playwright.expect(page).to_have_url(re.compile(r"/#optimizations/[a-f0-9]{32}$"))
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
    job_id = page.url.rsplit("/", 1)[-1]
    job = page.request.get(f"{portal['url']}/api/optimizations/{job_id}").json()
    rows = page.request.get(f"{portal['url']}/api/optimizations/{job_id}/results").json()["items"]
    assert job["axes"]["use_adx_elev"] == [True, False]
    assert job["completed_trials"] == job["total_trials"] == 2
    assert [row["parameters"]["use_adx_elev"] for row in rows] == [True, False]
    assert all(type(row["parameters"]["use_adx_elev"]) is bool for row in rows)
    page.reload()
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(2)
    page.screenshot(path=str(tmp_path / "adx-boolean-results.png"), full_page=True)
    (tmp_path / "adx-boolean-verification.json").write_text(json.dumps({
        "synthetic_dataset": True, "expected_boolean_values": [True, False],
        "expected_trials": 2, "job": job, "rows": rows, "reopened_after_reload": True,
    }, indent=2) + "\n")


def test_editable_step_readonly_counts_defaults_and_product_24(page, portal):
    prepare(page, portal)
    playwright.expect(page.locator(".optimization-grid thead th")).to_have_text(["Parameter", "Start value", "End value", "Step", "Step count"])
    for row in page.locator("#optimization-ranges tr").all():
        assert row.locator('[data-range="step_count"]').get_attribute("readonly") is not None
    # Fixed rows start at 0; changing one endpoint supplies default step 1.
    playwright.expect(page.get_by_label("Green bar count step", exact=True)).to_have_value("0")
    page.get_by_label("Green bar count start", exact=True).fill("2")
    playwright.expect(page.get_by_label("Green bar count step", exact=True)).to_have_value("1")
    page.get_by_label("Hold minutes start", exact=True).fill("10")
    page.get_by_label("Hold minutes end", exact=True).fill("25")
    page.get_by_label("Hold minutes step", exact=True).fill("5")
    # Non-landing endpoint: 1, 3, 5 stops before 6; no extra endpoint trial.
    page.get_by_label("Contracts end", exact=True).fill("6")
    page.get_by_label("Contracts step", exact=True).fill("2")
    playwright.expect(page.get_by_label("Contracts step count", exact=True)).to_have_value("3")
    playwright.expect(page.locator("#optimization-count")).to_have_text("Total combinations: 2 × 4 × 3 = 24 backtests")
    # Refresh choices/navigation preserve an edited increment.
    page.locator("#refresh-backtest-choices").click()
    playwright.expect(page.get_by_label("Contracts step", exact=True)).to_have_value("2")
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(24)
    job_id = page.url.rsplit("/", 1)[1]
    job = page.request.get(f"{portal['url']}/api/optimizations/{job_id}").json()
    assert job["axes"]["contracts"] == [1, 3, 5]
    assert job["step_counts"] == {"green_bar_count": 2, "hold_minutes": 4, "contracts": 3}
    assert job["completed_trials"] == 24


def test_decimal_count_uses_exact_arithmetic_in_portal(page, portal):
    prepare(page, portal)
    page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
    page.get_by_label("Mm risk pct start", exact=True).fill("0.10000000000000000000000000001")
    page.get_by_label("Mm risk pct end", exact=True).fill("0.30000000000000000000000000003")
    page.get_by_label("Mm risk pct step", exact=True).fill("0.10000000000000000000000000001")
    playwright.expect(page.get_by_label("Mm risk pct step count", exact=True)).to_have_value("3")
    page.get_by_label("Mm risk pct end", exact=True).fill("0.30000000000000000000000000002")
    playwright.expect(page.get_by_label("Mm risk pct step count", exact=True)).to_have_value("2")
    page.get_by_label("Mm risk pct end", exact=True).fill("0.10000000000000000000000000001")
    playwright.expect(page.get_by_label("Mm risk pct step", exact=True)).to_have_value("0")
    playwright.expect(page.get_by_label("Mm risk pct step count", exact=True)).to_have_value("1")


def test_integer_steps_cannot_be_silently_rounded_to_whole_numbers(page, portal):
    prepare(page, portal)
    page.get_by_label("Contracts step", exact=True).fill("1.00000000000000000000000000001")
    playwright.expect(page.get_by_label("Contracts step count", exact=True)).to_have_value("")
    playwright.expect(page.locator("#optimization-count")).to_contain_text("fix invalid ranges")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-error")).to_be_visible()
    assert page.request.get(portal["url"] + "/api/optimizations").json()["total"] == 0


def test_fixed_integer_endpoints_cannot_be_silently_rounded(page, portal):
    prepare(page, portal)
    for part in ("start", "end"):
        page.get_by_label("Contracts " + part, exact=True).fill("3.00000000000000000000000000001")
    playwright.expect(page.get_by_label("Contracts step", exact=True)).to_have_value("0")
    playwright.expect(page.get_by_label("Contracts step count", exact=True)).to_have_value("")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-error")).to_contain_text("whole numbers")
    assert page.request.get(portal["url"] + "/api/optimizations").json()["total"] == 0


def test_parallel_worker_selection_persists_and_process_results_reopen(page, portal):
    from alphaquest.optimization import MAX_WORKERS
    if MAX_WORKERS < 2:
        pytest.skip("Host allows one worker")
    prepare(page, portal)
    page.locator("#optimization-workers").select_option("2")
    page.locator("#refresh-backtest-choices").click()
    playwright.expect(page.locator("#optimization-workers")).to_have_value("2")
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    run(page)
    playwright.expect(page.locator("#optimization-status")).to_contain_text("2 worker processes")
    page.reload()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE")
    playwright.expect(page.locator("#optimization-status")).to_contain_text("2 worker processes")


@pytest.mark.parametrize("failure", ["network", "missing", "server", "malformed", "invalid"])
def test_worker_loading_failure_has_retry_and_preserves_choices(page, portal, failure):
    endpoint = "**/api/optimizations/settings"
    def fail(route):
        if failure == "network": route.abort()
        elif failure == "missing": route.fulfill(status=422, json={"detail": "Invalid UUID"})
        elif failure == "server": route.fulfill(status=503, json={"detail": "Temporarily unavailable"})
        elif failure == "malformed": route.fulfill(status=200, body="not-json")
        else: route.fulfill(json={"default_workers": 4, "max_workers": 0})
    page.route(endpoint, fail)
    page.goto(portal["url"] + "/#optimizations")
    playwright.expect(page.locator("#optimization-ranges tr")).to_have_count(3)
    playwright.expect(page.locator("#optimization-workers")).to_have_text("Worker options unavailable")
    playwright.expect(page.locator("#optimization-workers-retry")).to_be_visible()
    if failure == "missing":
        playwright.expect(page.locator("#optimization-workers-help")).to_contain_text("Restart the backend")
    page.locator("#backtest-dataset").select_option(portal["saved"]["arithmetic_5m"]["id"])
    page.get_by_label("Contracts end", exact=True).fill("5")
    playwright.expect(page.locator("#start-backtest")).to_be_disabled()
    # Ordinary backtests do not depend on the parallel-worker settings service.
    page.get_by_role("link", name="Backtests", exact=True).click()
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    page.get_by_role("link", name="Optimizations", exact=True).click()
    playwright.expect(page.locator("#optimization-workers-retry")).to_be_visible()
    page.unroute(endpoint)
    page.locator("#optimization-workers-retry").click()
    playwright.expect(page.locator("#optimization-workers")).to_be_enabled()
    playwright.expect(page.locator("#optimization-workers-retry")).to_be_hidden()
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    playwright.expect(page.get_by_label("Contracts end", exact=True)).to_have_value("5")


def test_worker_options_load_even_when_strategy_request_fails(page, portal):
    page.route("**/api/strategies", lambda route: route.fulfill(status=503, json={"detail": "Strategy registry unavailable"}))
    page.goto(portal["url"] + "/#optimizations")
    playwright.expect(page.locator("#backtest-error")).to_contain_text("Strategy registry unavailable")
    playwright.expect(page.locator("#optimization-workers option")).not_to_have_count(0)
    playwright.expect(page.locator("#optimization-workers")).not_to_contain_text("Loading")
    playwright.expect(page.locator("#optimization-workers")).not_to_contain_text("unavailable")
    page.unroute("**/api/strategies")
    page.locator("#refresh-backtest-choices").click()
    playwright.expect(page.locator("#optimization-ranges tr")).to_have_count(3)


def test_worker_request_timeout_stops_loading_and_retries(page, portal):
    import time
    def delayed(route):
        # A stalled worker endpoint must not prevent choices rendering or leave
        # the selector loading indefinitely. Return after the client timeout.
        time.sleep(11)
        route.fulfill(json={"default_workers": 1, "max_workers": 1})
    page.route("**/api/optimizations/settings", delayed)
    page.goto(portal["url"] + "/#optimizations")
    playwright.expect(page.locator("#optimization-workers-help")).to_contain_text("timed out", timeout=15000)
    playwright.expect(page.locator("#optimization-workers-retry")).to_be_visible()
    page.unroute("**/api/optimizations/settings")
    page.locator("#optimization-workers-retry").click()
    playwright.expect(page.locator("#optimization-workers")).to_be_enabled()


def test_worker_retry_retains_inspectable_product_evidence(page, portal, tmp_path):
    import json
    from pathlib import Path
    from decimal import Decimal

    # A separately labeled source, using normal dataset storage; the BOM changes
    # the source identity while preserving the reviewed synthetic arithmetic.
    source = Path(__file__).parent / "fixtures/backtest_contract/arithmetic_5m.csv"
    response = page.request.post(portal["url"] + "/api/datasets", params={
        "filename": "SYNTHETIC-worker-retry.csv", "name": "SYNTHETIC worker retry review",
        "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10",
    }, data=b"\xef\xbb\xbf" + source.read_bytes(), headers={"content-type": "text/csv"})
    assert response.status == 201, response.text()
    dataset = response.json()
    page.route("**/api/optimizations/settings", lambda route: route.fulfill(status=503, json={"detail": "Review: temporary settings outage"}))
    page.goto(portal["url"] + "/#optimizations")
    playwright.expect(page.locator("#optimization-ranges tr")).to_have_count(3)
    playwright.expect(page.locator("#optimization-workers")).to_have_text("Worker options unavailable")
    page.locator("#backtest-dataset").select_option(dataset["id"])
    page.locator("#backtest-slippage-ticks").fill("1")
    page.locator("#backtest-commission").fill("1")
    page.get_by_label("Contracts end", exact=True).fill("3")
    playwright.expect(page.locator("#start-backtest")).to_be_disabled()
    page.screenshot(path=str(tmp_path / "worker-options-unavailable.png"), full_page=True)
    page.unroute("**/api/optimizations/settings")
    page.locator("#optimization-workers-retry").click()
    playwright.expect(page.locator("#optimization-workers")).to_be_enabled()
    page.locator("#optimization-workers").select_option("1")
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    playwright.expect(page.get_by_label("Contracts end", exact=True)).to_have_value("3")
    page.screenshot(path=str(tmp_path / "worker-options-recovered.png"), full_page=True)
    run(page)
    job_id = page.url.rsplit("/", 1)[1]
    rows = page.request.get(f"{portal['url']}/api/optimizations/{job_id}/results").json()["items"]
    assert [Decimal(row["metrics"]["total_net_pnl"]) for row in rows] == [13, 26, 39]
    page.screenshot(path=str(tmp_path / "recovered-optimization-results.png"), full_page=True)
    (tmp_path / "verification.json").write_text(json.dumps({
        "synthetic": True, "simulated_boundary": "503 on worker settings only",
        "unavailable_state_and_disabled_start_verified": True,
        "retry_loaded_real_settings": True, "parameter_edits_preserved": True,
        "job_id": job_id, "expected_net_pnl": [13, 26, 39], "actual_rows": rows,
    }, indent=2) + "\n")

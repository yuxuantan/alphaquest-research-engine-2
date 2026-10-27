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


def test_reuse_toggle_badges_reopen_and_forced_fresh_results(page, portal, tmp_path):
    import json
    prepare(page, portal)
    playwright.expect(page.locator("#optimization-reuse")).to_be_checked()
    run(page)
    first_url = page.url
    before = page.request.get(portal["url"] + "/api/optimizations").json()["items"][0]
    first = page.request.get(f"{portal['url']}/api/optimizations/{before['id']}/results").json()["items"]
    assert before["prepared_data"] and before["reused_trials"] == 0
    prepare(page, portal)
    run(page)
    reused_url = page.url
    playwright.expect(page.locator("#optimization-status")).to_contain_text("3 reused · 0 computed")
    playwright.expect(page.get_by_text("Reused saved trial", exact=True)).to_have_count(3)
    reused = page.request.get(portal["url"] + "/api/optimizations").json()["items"][0]
    actual = page.request.get(f"{portal['url']}/api/optimizations/{reused['id']}/results").json()["items"]
    assert [row["run_id"] for row in actual] == [row["run_id"] for row in first]
    assert page.request.get(portal["url"] + "/api/backtests").json()["total"] == 3
    page.screenshot(path=str(tmp_path / "reused-results.png"), full_page=True)
    page.reload()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("3 reused · 0 computed")
    page.locator("#optimization-results tbody a").first.click()
    playwright.expect(page.locator("#report-summary")).to_contain_text("13.00")
    prepare(page, portal)
    page.locator("#optimization-reuse").uncheck()
    run(page)
    playwright.expect(page.locator("#optimization-status")).to_contain_text("0 reused · 3 computed")
    assert page.request.get(portal["url"] + "/api/backtests").json()["total"] == 6
    (tmp_path / "reuse-verification.json").write_text(json.dumps({
        "baseline": before, "reused": reused, "first_rows": first, "reused_rows": actual,
        "expected_net_pnl": [13, 26, 39], "source_url": first_url, "reused_url": reused_url}, indent=2))


def test_grid_run_sort_export_reopen_and_normal_report(page, portal, tmp_path):
    prepare(page, portal)
    run(page)
    url = page.url
    rows = page.locator("#optimization-results tbody tr")
    playwright.expect(rows.nth(0).locator('td[data-column="param.contracts"]')).to_have_text("1")
    playwright.expect(rows.nth(0).locator('td[data-column="total_net_pnl"]')).to_have_text("13.00")
    page.get_by_role("button", name="Total net pnl", exact=False).click()
    playwright.expect(page.locator('#optimization-results th[aria-sort="ascending"]')).to_contain_text("Total net pnl")
    page.get_by_role("button", name="Total net pnl", exact=False).click()
    playwright.expect(rows.nth(0).locator('td[data-column="total_net_pnl"]')).to_have_text("39.00")
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
    assert page.locator("#optimization-results thead th.optimization-varying-parameter").evaluate_all(
        "items => items.map(item => item.dataset.column)") == ["param.mm_risk_pct", "param.trade_shorts"]


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


@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 650}, {"width": 390, "height": 650}], ids=["desktop", "mobile"])
def test_result_headers_stay_visible_and_varying_columns_remain_highlighted(page, portal, tmp_path, viewport):
    import json
    from pathlib import Path

    page.set_viewport_size(viewport)
    source = Path(__file__).parent / "fixtures/backtest_contract/arithmetic_5m.csv"
    response = page.request.post(portal["url"] + "/api/datasets", params={
        "filename": "SYNTHETIC-table-review.csv", "name": "SYNTHETIC optimization table review",
        "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10",
    }, data=b"\xef\xbb\xbf" + source.read_bytes(), headers={"content-type": "text/csv"})
    assert response.status == 201
    prepare(page, portal)
    page.locator("#backtest-dataset").select_option(response.json()["id"])
    page.get_by_label("Hold minutes end", exact=True).fill("25")
    page.get_by_label("Hold minutes step", exact=True).fill("5")
    page.get_by_label("Contracts end", exact=True).fill("30")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(50)
    job_id = page.url.rsplit("/", 1)[1]
    headers = page.locator("#optimization-results thead th.optimization-varying-parameter")
    assert headers.evaluate_all("items => items.map(item => item.dataset.column)") == ["param.hold_minutes", "param.contracts"]
    assert page.locator("#optimization-results thead th").evaluate_all("items => items.slice(0, 4).map(item => item.dataset.column)") == [
        "param.hold_minutes", "param.contracts", "trial", "param.green_bar_count"]
    playwright.expect(page.locator("#optimization-results tbody td.optimization-frozen-parameter")).to_have_count(100)
    playwright.expect(page.locator("#optimization-results tbody td.optimization-varying-parameter")).to_have_count(100)
    playwright.expect(page.locator("#optimization-parameter-legend")).to_contain_text("Hold minutes, Contracts")
    for key in ("param.green_bar_count", "total_net_pnl"):
        assert "optimization-varying-parameter" not in (page.locator(f'#optimization-results th[data-column="{key}"]').get_attribute("class") or "")
    region = page.locator("#optimization-results-scroll")
    # Both the document and the result body must actually scroll in this probe.
    region.evaluate("element => element.scrollTop = 450")
    page.evaluate("window.scrollTo(0, document.querySelector('#optimization-results-scroll').getBoundingClientRect().top + window.scrollY + 70)")
    page.wait_for_function("""() => {
        const region = document.querySelector('#optimization-results-scroll');
        const header = document.querySelector('#optimization-results thead th');
        return region.getBoundingClientRect().top < -20 && region.scrollTop > 400
            && header.getBoundingClientRect().top >= -1 && header.getBoundingClientRect().top < 3;
    }""")
    before = page.locator("#optimization-results thead th").first.bounding_box()
    columns_before = headers.evaluate_all("items => items.map(item => ({x: item.getBoundingClientRect().x, width: item.getBoundingClientRect().width}))")
    metric = page.locator('#optimization-results th[data-column="total_net_pnl"]')
    metric_x_before = metric.bounding_box()["x"]
    region.evaluate("element => { element.scrollTop = 900; element.scrollLeft = 600; }")
    page.wait_for_function("document.querySelector('#optimization-results-scroll').scrollTop >= 900")
    after = page.locator("#optimization-results thead th").first.bounding_box()
    assert abs(before["y"] - after["y"]) <= 1
    columns_after = headers.evaluate_all("items => items.map(item => ({x: item.getBoundingClientRect().x, width: item.getBoundingClientRect().width}))")
    assert region.evaluate("element => element.scrollLeft") == 600
    assert abs(metric_x_before - metric.bounding_box()["x"] - 600) < 1
    for first, second in zip(columns_before, columns_after):
        assert abs(first["x"] - second["x"]) < 1
    assert abs(columns_after[1]["x"] - columns_after[0]["x"] - columns_after[0]["width"]) < 1
    # Scrolled metrics must paint underneath both frozen headers and body cells.
    assert headers.evaluate_all("""items => items.every(cell => {
        const r = cell.getBoundingClientRect();
        return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2).closest('th') === cell;
    })""")
    assert page.locator("#optimization-results tbody td.optimization-frozen-parameter").evaluate_all("""items => {
        const region = document.querySelector('#optimization-results-scroll').getBoundingClientRect();
        const header = document.querySelector('#optimization-results thead th').getBoundingClientRect();
        const visible = items.filter(cell => {
            const r = cell.getBoundingClientRect();
            return r.y > header.bottom && r.bottom < Math.min(innerHeight, region.bottom) - 2;
        });
        return visible.length > 0 && visible.every(cell => {
            const r = cell.getBoundingClientRect();
            return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2).closest('td') === cell;
        });
    }""")
    th = page.locator('#optimization-results th[data-column="param.contracts"]')
    td = page.locator('#optimization-results tbody td[data-column="param.contracts"]').first
    assert abs(th.bounding_box()["x"] - td.bounding_box()["x"]) < 1
    assert abs(th.bounding_box()["width"] - td.bounding_box()["width"]) < 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(tmp_path / "scrolled-results.png"))
    # The visible sticky header remains the real sortable column header.
    th.get_by_role("button").click()
    playwright.expect(th).to_have_attribute("aria-sort", "ascending")
    playwright.expect(th.locator(".optimization-varying-badge")).to_have_text("Varies")
    page.locator("#optimization-next").click()
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(10)
    playwright.expect(page.locator("#optimization-results tbody td.optimization-varying-parameter")).to_have_count(20)
    playwright.expect(page.locator("#optimization-results tbody td.optimization-frozen-parameter")).to_have_count(20)
    page.reload()
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(50)
    playwright.expect(headers).to_have_count(2)
    records = page.request.get(f"{portal['url']}/api/optimizations/{job_id}/results?limit=100").json()
    assert records["total"] == len(records["items"]) == 60
    (tmp_path / "verification.json").write_text(json.dumps({
        "synthetic": True, "job_id": job_id, "viewport": viewport,
        "expected_varying_parameters": ["hold_minutes", "contracts"], "fixed_parameter": "green_bar_count",
        "inner_scroll_before": 450, "inner_scroll_after": 900,
        "header_viewport_y_before": before["y"], "header_viewport_y_after": after["y"],
        "frozen_columns_before": columns_before, "frozen_columns_after": columns_after,
        "horizontal_scroll": 600, "metrics_scrolled_under_frozen_cells": True,
        "header_and_body_columns_aligned": True, "sorting_pagination_reload_verified": True,
        "total_saved_trials": 60,
    }, indent=2) + "\n")


def test_single_generated_value_is_not_highlighted_even_when_endpoints_differ(page, portal):
    prepare(page, portal)
    page.get_by_label("Contracts end", exact=True).fill("2")
    page.get_by_label("Contracts step", exact=True).fill("5")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(1)
    playwright.expect(page.locator("#optimization-results .optimization-varying-parameter")).to_have_count(0)
    playwright.expect(page.locator("#optimization-results .optimization-frozen-parameter")).to_have_count(0)
    playwright.expect(page.locator("#optimization-results thead th").first).to_have_attribute("data-column", "trial")
    playwright.expect(page.locator("#optimization-parameter-legend")).to_have_text("All strategy parameters are fixed for this run.")


def test_resume_remaining_trials_preserves_twelve_saved_reports(page, portal, tmp_path, monkeypatch):
    from decimal import Decimal
    from hashlib import sha256
    import json
    from pathlib import Path
    import sqlite3
    from alphaquest.optimization import MAX_WORKERS

    if MAX_WORKERS < 4:
        pytest.skip("Review requires four worker processes")
    source = Path(__file__).parent / "fixtures/backtest_contract/arithmetic_5m.csv"
    response = page.request.post(portal["url"] + "/api/datasets", params={
        "filename": "SYNTHETIC-database-recovery.csv", "name": "SYNTHETIC database recovery review",
        "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10",
    }, data=b"\xef\xbb\xbf" + source.read_bytes(), headers={"content-type": "text/csv"})
    assert response.status == 201
    store = portal["app"].state.optimizations
    publish = store.publish
    def unavailable_last_batch(job_id, trial, run_id, context, result):
        if trial >= 13:
            # Real SQLite CANTOPEN at publication, after real backtests. The
            # inaccessible path is confined to this test's owned workspace.
            sqlite3.connect(context.output_root / "unavailable" / "backtests.sqlite3")
        return publish(job_id, trial, run_id, context, result)
    monkeypatch.setattr(store, "publish", unavailable_last_batch)
    prepare(page, portal)
    page.locator("#backtest-dataset").select_option(response.json()["id"])
    page.locator("#optimization-workers").select_option("4")
    page.get_by_label("Hold minutes end", exact=True).fill("35")
    page.get_by_label("Hold minutes step", exact=True).fill("5")
    page.get_by_label("Contracts end", exact=True).fill("4")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("FAILED", timeout=20000)
    playwright.expect(page.locator("#optimization-status")).to_contain_text("12 / 16 trials saved")
    job_id = page.url.rsplit("/", 1)[1]
    before = page.request.get(f"{portal['url']}/api/optimizations/{job_id}/results").json()["items"]
    assert [row["trial"] for row in before] == list(range(1, 13))
    def csv_hashes(rows):
        return {row["run_id"]: {name: sha256((store.runs.root / row["run_id"] / name).read_bytes()).hexdigest()
                for name in ("trades.csv", "equity.csv")} for row in rows}
    saved_hashes = csv_hashes(before)
    resume = page.locator("#optimization-resume")
    playwright.expect(resume).to_have_text("Resume remaining 4 trials")
    resume.scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path / "failed-twelve-of-sixteen.png"), full_page=True)
    monkeypatch.setattr(store, "publish", publish)
    resume.click()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
    playwright.expect(page.locator("#optimization-status")).to_contain_text("16 / 16 trials saved")
    playwright.expect(resume).to_be_hidden()
    after = page.request.get(f"{portal['url']}/api/optimizations/{job_id}/results").json()["items"]
    assert after[:12] == before
    assert csv_hashes(after[:12]) == saved_hashes
    assert [Decimal(row["metrics"]["total_net_pnl"]) for row in after] == [13, 26, 39, 52] * 4
    assert page.request.get(portal["url"] + "/api/backtests").json()["total"] == 16
    page.screenshot(path=str(tmp_path / "resumed-sixteen-of-sixteen.png"), full_page=True)
    page.reload()
    playwright.expect(page.locator("#optimization-status")).to_contain_text("16 / 16 trials saved")
    page.locator("#optimization-results tbody tr").last.get_by_role("link").click()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    playwright.expect(page.locator("#report-summary")).to_contain_text("52.00")
    (tmp_path / "verification.json").write_text(json.dumps({
        "synthetic": True, "simulated_boundary": "Real SQLite CANTOPEN on trials 13-16 publication",
        "workers": 4, "job_id": job_id, "saved_trials_before": 12, "saved_trials_after": 16,
        "preserved_rows": before, "preserved_csv_sha256": saved_hashes,
        "new_trials": after[12:], "all_expected_net_pnl": [13, 26, 39, 52] * 4,
        "existing_reports_unchanged": True, "reload_and_normal_report_verified": True,
    }, indent=2) + "\n")

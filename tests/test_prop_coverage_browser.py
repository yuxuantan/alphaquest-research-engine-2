"""Coverage is demonstrated in the normal saved backtest/setup/result journey."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from test_backtests_browser import FIXTURES, browser, page, portal, playwright
from test_prop_browser import save_setup, check_source
from test_prop_results_browser import run


OUTPUT = Path("artifacts/prop-coverage")


def upload(portal, *, missing=None):
    lines = (FIXTURES / "coverage_rth_5m.csv").read_text().splitlines()
    if missing is not None:
        del lines[missing + 1]
    with httpx.Client(base_url=portal["url"]) as client:
        response = client.post("/api/datasets", params={"filename": "synthetic-rth.csv", "name": "Synthetic NQ cash-hours coverage",
            "source_timezone": "UTC", "tick_size": "0.25", "point_value": "20"}, content="\n".join(lines) + "\n")
        assert response.status_code == 201, response.text
        return response.json()["id"]


def backtest_to_setup(page, portal, dataset, *, zero=False):
    page.goto(portal["url"] + "/#backtests")
    playwright.expect(page.locator("#strategy-parameters input")).to_have_count(3)
    page.locator("#backtest-dataset").select_option(dataset)
    page.locator("#backtest-slippage-ticks").fill("1")
    page.locator("#backtest-commission").fill("1")
    page.locator("#strategy-contracts").fill("2")
    page.locator("#strategy-green_bar_count").fill("100" if zero else "3")
    with page.expect_response(lambda r: "/api/backtests?" in r.url and r.request.method == "POST") as completed:
        page.locator("#start-backtest").click()
    assert completed.value.status == 201
    record = completed.value.json()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    page.get_by_role("link", name="Set up prop simulation").click()
    playwright.expect(page.locator("#prop-workflow")).to_be_visible()
    page.locator("#prop-instrument-profile").select_option("nq")
    return record


@pytest.mark.parametrize("zero,balance", [(False, "50056"), (True, "5E+4")])
def test_remember_schedule_save_run_download_and_reuse(page, portal, zero, balance):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dataset = upload(portal)
    source = backtest_to_setup(page, portal, dataset, zero=zero)
    playwright.expect(page.locator("#prop-coverage-status")).to_contain_text("78 bars")
    playwright.expect(page.locator("#prop-save")).to_be_disabled()
    page.locator("#prop-export-profile").select_option("cme_cash_hours_300")
    page.locator("#prop-remember-session").click()
    playwright.expect(page.locator("#prop-coverage-status")).to_contain_text("Coverage matches")
    playwright.expect(page.locator("#prop-advanced-coverage")).to_be_hidden()
    assert page.locator("#prop-coverage-summary tbody").nth(1).locator("td").all_text_contents() == [
        "2026-01-05", "covered", "78", "78", "0", "0", "0" if zero else "1", "—"]
    page.screenshot(path=str(OUTPUT / ("zero-trade-coverage.png" if zero else "coverage.png")), full_page=True)
    setup = save_setup(page)
    check_source(page)
    run(page)
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text(balance)
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("unresolved_data_end")
    result_url = page.url
    for name in ("report.json", "coverage.json"):
        with page.expect_download() as download:
            page.get_by_role("link", name=name, exact=True).click()
        content = download.value.path().read_bytes()
        captured = json.loads(content)
        (OUTPUT / (("zero-" if zero else "") + name)).write_bytes(content)
        if name == "report.json":
            assert Decimal(captured["summary"]["balance"]) == Decimal(balance)
            assert captured["summary"]["external_costs"] == "49"
        else:
            assert captured["coverage"]["summary"]["zero_trade_sessions"] == int(zero)
            assert captured["coverage"]["summary"]["missing_bars"] == 0
            assert captured["profile"]["id"] == "cme_cash_hours_300"
    page.reload()
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text(balance)
    page.screenshot(path=str(OUTPUT / ("zero-trade-result.png" if zero else "result.png")), full_page=True)
    # A second completed run from the same dataset inherits the expectation;
    # the saved setup retains its own snapshot when the dataset default changes.
    backtest_to_setup(page, portal, dataset, zero=zero)
    playwright.expect(page.locator("#prop-export-profile")).to_have_value("cme_cash_hours_300")
    playwright.expect(page.locator("#prop-save")).to_be_enabled()
    page.locator("#prop-export-profile").select_option("cme_cash_hours_60")
    playwright.expect(page.locator("#prop-save")).to_be_disabled()
    page.locator("#prop-remember-session").click()
    playwright.expect(page.locator("#prop-coverage-status")).to_contain_text("incomplete")
    page.goto(portal["url"] + "/#backtests/prop/" + setup)
    playwright.expect(page.locator("#prop-export-profile")).to_have_value("cme_cash_hours_300")
    playwright.expect(page.locator("#prop-coverage-status")).to_contain_text("Coverage matches")
    playwright.expect(page.locator("#prop-run")).to_be_enabled()
    page.goto(result_url)
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text(balance)
    with httpx.Client(base_url=portal["url"]) as client:
        assert client.get(f"/api/backtests/{source['id']}").json() == source


@pytest.mark.parametrize("missing", [0, 20])
def test_gaps_and_partial_boundaries_block_save_in_product(page, portal, missing):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    backtest_to_setup(page, portal, upload(portal, missing=missing), zero=True)
    page.locator("#prop-export-profile").select_option("cme_cash_hours_300")
    page.locator("#prop-remember-session").click()
    playwright.expect(page.locator("#prop-coverage-status")).to_contain_text("incomplete")
    playwright.expect(page.locator("#prop-save")).to_be_disabled()
    assert page.locator("#prop-coverage-summary tbody").nth(0).locator("td").all_text_contents() == [
        "0", "0", "0", "0", "0", "1", "0", "1" if missing == 0 else "0"]
    assert page.locator("#prop-coverage-summary tbody").nth(1).locator("td").all_text_contents()[:6] == [
        "2026-01-05", "missing", "78", "77", "1", "0"]
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(OUTPUT / ("partial-boundary.png" if missing == 0 else "missing-bar.png")), full_page=True)


def test_coverage_request_failure_is_visible_and_advanced_override_remains_accessible(page, portal):
    page.route("**/api/prop-simulations/sources/*/coverage*", lambda route: route.fulfill(status=503, json={"detail": "Inspection temporarily unavailable"}))
    backtest_to_setup(page, portal, upload(portal))
    playwright.expect(page.locator("#prop-coverage-status")).to_contain_text("Inspection temporarily unavailable")
    playwright.expect(page.locator("#prop-save")).to_be_disabled()
    page.locator("#prop-coverage-mode").select_option("advanced")
    playwright.expect(page.locator("#prop-advanced-coverage")).to_be_visible()
    page.locator("#prop-coverage-mode").select_option("automatic")
    page.unroute("**/api/prop-simulations/sources/*/coverage*")
    page.locator("#prop-refresh-coverage").click()
    playwright.expect(page.locator("#prop-coverage-status")).to_contain_text("78 bars")
    playwright.expect(page.locator("#prop-export-profile option")).to_have_count(6)

"""Prop increments use the final product workflow from actual saved reports."""

import json
import re

import httpx

from test_backtest_api import body
from test_backtests_browser import browser, page, portal, playwright


def open_setup(page, portal, dataset_id=None):
    with httpx.Client(base_url=portal["url"]) as client:
        response = client.post("/api/backtests", json=body(dataset_id or portal["saved"]["arithmetic_5m"]["id"]))
        assert response.status_code == 201, response.text
        record = response.json()
    page.goto(portal["url"] + "/#backtests/report/" + record["id"])
    page.get_by_role("link", name="Set up prop simulation").click()
    playwright.expect(page.locator("#prop-workflow")).to_be_visible()
    playwright.expect(page.locator("#prop-source")).to_contain_text(record["id"])
    return record


def fill_setup(page, fee="0", instrument_profile=None):
    if fee is not None:
        page.locator("#prop-fee-override").check()
        page.locator("#prop-fee").fill(fee)
    page.locator("#prop-instrument-profile").select_option(instrument_profile or "custom")
    if instrument_profile is None:
        page.locator("#prop-symbol").fill("TEST")
        page.locator("#prop-currency").select_option("USD")
        page.locator("#prop-weight").fill("1")
        page.locator("#prop-unit-url").fill("https://example.com/explicit-test-units")
        page.locator("#prop-basis").fill("Explicit synthetic test: USD 10 per point, .25 tick, one rule unit per contract.")
    page.locator("#prop-coverage-mode").select_option("advanced")
    page.locator("#prop-calendar-mode").select_option("weekday_approximation")
    page.locator("#prop-window-start").fill("05:00")
    page.locator("#prop-window-end").fill("05:30")
    page.locator("#prop-cadence").fill("300")
    page.locator("#prop-coverage").fill("Complete synthetic fixture window Monday through Friday.")


def save_setup(page):
    page.locator("#prop-save").click()
    playwright.expect(page.locator("#prop-status")).to_have_text("Saved setup loaded.")
    playwright.expect(page.locator("#prop-saved")).to_be_visible()
    assert re.search(r"#backtests/prop/[0-9a-f]{32}$", page.url)
    return page.url.rsplit("/", 1)[-1]


def check_source(page):
    page.locator("#prop-check").click()
    playwright.expect(page.locator("#prop-check-result")).to_contain_text("Source inputs are compatible")
    playwright.expect(page.locator("#prop-status")).to_contain_text("Source check complete")


def test_report_setup_check_resize_download_and_reload(page, portal):
    record = open_setup(page, portal)
    fill_setup(page)
    original = save_setup(page)
    check_source(page)
    playwright.expect(page.locator("#prop-check-result")).to_contain_text("26")
    playwright.expect(page.locator("#prop-check-result")).to_contain_text("7 of 7 observations")
    page.locator("#prop-preview-mode").select_option("trade_close")
    playwright.expect(page.locator("#prop-check-result")).to_contain_text("1 of 1 observations")
    with page.expect_download() as download:
        page.get_by_role("link", name="check.json", exact=True).click()
    first = json.loads(download.value.path().read_text())
    assert first["summary"]["net_pnl"] == "26"
    page.reload()
    playwright.expect(page.locator("#prop-check-result")).to_contain_text("Source inputs are compatible")
    playwright.expect(page.locator("#prop-saved-id")).to_contain_text(original)
    page.locator("#prop-quantity").fill("1")
    playwright.expect(page.locator("#prop-input-check")).to_be_hidden()
    playwright.expect(page.locator("#prop-check")).to_be_disabled()
    second = save_setup(page)
    assert second != original
    check_source(page)
    with page.expect_download() as download:
        page.get_by_role("link", name="check.json", exact=True).click()
    scaled = json.loads(download.value.path().read_text())
    assert scaled["summary"]["net_pnl"] == "13"
    assert scaled["summary"]["source_contracts"] == 2
    assert scaled["summary"]["slippage_cost"] == "5"
    page.locator("#prop-back").click()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    playwright.expect(page.locator("#report-run-id")).to_contain_text(record["id"])
    page.get_by_role("link", name="Set up prop simulation").click()
    playwright.expect(page.locator("#prop-setups-count")).to_have_text("2 saved setups")


def test_phase_platform_and_invalid_source_are_real_workflow_states(page, portal):
    open_setup(page, portal)
    fill_setup(page)
    page.locator("#prop-profile").select_option("apex_50k_eod_tradovate")
    playwright.expect(page.locator("#prop-rules")).to_contain_text("No lock")
    page.locator("#prop-phase").select_option("funded")
    playwright.expect(page.locator("#prop-fee-override")).not_to_be_checked()
    playwright.expect(page.locator("#prop-fee-field")).to_be_hidden()
    playwright.expect(page.locator("#prop-fee-label")).to_have_text("Funded activation fee override · USD")
    playwright.expect(page.locator("#prop-fee")).to_have_value("")
    playwright.expect(page.locator("#prop-rules")).to_contain_text("Limits by prior-session profit")
    page.locator("#prop-fee-override").check()
    page.locator("#prop-fee").fill("0")
    page.locator("#prop-window-end").fill("05:35")
    save_setup(page)
    page.locator("#prop-check").click()
    playwright.expect(page.locator("#prop-check-result")).to_contain_text("Source inputs rejected")
    playwright.expect(page.locator("#prop-check-result")).to_contain_text("coverage")
    page.reload()
    playwright.expect(page.locator("#prop-check-result")).to_contain_text("Source inputs rejected")
    playwright.expect(page.get_by_role("button", name="Run simulation", exact=True)).to_be_disabled()


def test_product_mobile_layout_and_explicit_calendar(page, portal):
    page.set_viewport_size({"width": 390, "height": 844})
    open_setup(page, portal)
    fill_setup(page)
    page.locator("#prop-calendar-mode").select_option("explicit")
    page.locator("#prop-days").fill(json.dumps([dict(trading_date="2026-01-05", status="covered", windows=[
        dict(first_utc="2026-01-05T10:00:00Z", last_utc="2026-01-05T10:30:00Z", bar_interval_seconds=300)])]))
    save_setup(page)
    check_source(page)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    playwright.expect(page.locator("#prop-preview-mode")).to_be_visible()


def test_source_request_failure_is_visible_and_can_retry(page, portal):
    open_setup(page, portal)
    fill_setup(page)
    save_setup(page)
    page.route("**/api/prop-simulations/setups/*/check", lambda route: route.fulfill(status=503, json={"detail": "Source storage unavailable."}))
    page.locator("#prop-check").click()
    playwright.expect(page.locator("#prop-status")).to_contain_text("Source storage unavailable")
    playwright.expect(page.locator("#prop-input-check")).to_be_hidden()
    playwright.expect(page.locator("#prop-check")).to_be_enabled()
    page.unroute("**/api/prop-simulations/setups/*/check")
    check_source(page)


def test_saved_setup_is_usable_when_template_catalog_is_unavailable(page, portal):
    open_setup(page, portal)
    fill_setup(page)
    save_setup(page)
    check_source(page)
    page.route("**/api/prop-simulations/profiles", lambda route: route.fulfill(status=503, json={"detail": "Template catalog unavailable."}))
    page.reload()
    playwright.expect(page.locator("#prop-check-result")).to_contain_text("Source inputs are compatible")
    playwright.expect(page.locator("#prop-save-note")).to_contain_text("saved rules remain available")
    playwright.expect(page.locator("#prop-check")).to_be_enabled()
    playwright.expect(page.locator("#prop-save")).to_be_disabled()
    check_source(page)

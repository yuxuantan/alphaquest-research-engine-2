"""Reusable instruments are selected in the existing backtest/setup/result workflow."""

import json
from pathlib import Path

import httpx
import pytest

from test_backtests_browser import browser, page, portal, playwright
from test_prop_browser import open_setup, fill_setup, save_setup, check_source


def dataset_for(portal, point_value):
    with httpx.Client(base_url=portal["url"]) as client:
        dataset_id = portal["saved"]["arithmetic_5m"]["id"]
        response = client.patch(f"/api/datasets/{dataset_id}/instrument-settings",
                                json={"tick_size": "0.25", "point_value": point_value})
        assert response.status_code == 200, response.text
        return response.json()["id"]


@pytest.mark.parametrize("instrument,point,weight,balance", [("nq", "20", "1", "50056"), ("mnq", "2", "0.1", "50002")])
def test_select_save_run_reopen_download_and_catalog_failure(page, portal, instrument, point, weight, balance):
    output = Path("artifacts/prop-instrument-profiles")
    output.mkdir(parents=True, exist_ok=True)
    source = open_setup(page, portal, dataset_for(portal, point))
    playwright.expect(page.locator("#prop-instrument-profile")).to_have_value("")
    fill_setup(page, fee=None, instrument_profile=instrument)
    playwright.expect(page.locator("#prop-instrument-custom")).to_be_hidden()
    playwright.expect(page.locator("#prop-instrument-summary")).to_contain_text("USD")
    playwright.expect(page.locator("#prop-instrument-summary")).to_contain_text("0.25")
    cells = page.locator("#prop-instrument-summary tbody td").all_text_contents()
    assert cells == [instrument.upper(), "USD", "0.25", point, weight]
    page.screenshot(path=str(output / f"{instrument}-setup.png"), full_page=True)
    setup_id = save_setup(page)
    with page.expect_download() as download:
        page.get_by_role("link", name="instrument.json", exact=True).click()
    captured = json.loads(download.value.path().read_text())
    (output / f"{instrument}-instrument.json").write_bytes(download.value.path().read_bytes())
    assert captured["profile"]["profile"]["id"] == instrument
    check_source(page)
    page.locator("#prop-run").click()
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text(balance)
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text(f"Instrument: {instrument.upper()} · USD · profile {instrument}")
    with page.expect_download() as download:
        page.get_by_role("link", name="report.json", exact=True).click()
    result = json.loads(download.value.path().read_text())
    (output / f"{instrument}-report.json").write_bytes(download.value.path().read_bytes())
    assert result["instrument"] == captured
    assert result["summary"]["external_costs"] == "49" and result["summary"]["balance"] == balance
    page.screenshot(path=str(output / f"{instrument}-result.png"), full_page=True)
    page.reload()
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text(balance)
    page.locator("#prop-back").click()
    playwright.expect(page.locator("#prop-workflow")).to_be_visible()
    playwright.expect(page.locator("#prop-instrument-profile")).to_have_value(instrument)
    playwright.expect(page.locator("#prop-instrument-summary")).to_contain_text("Saved instrument snapshot")
    page.route("**/api/prop-simulations/instrument-profiles*", lambda route: route.fulfill(status=503, json={"detail": "Catalog unavailable"}))
    page.reload()
    playwright.expect(page.locator("#prop-instrument-summary")).to_contain_text("Saved instrument snapshot")
    playwright.expect(page.locator("#prop-check")).to_be_enabled()
    playwright.expect(page.locator("#prop-run")).to_be_enabled()
    playwright.expect(page.locator("#prop-save")).to_be_disabled()
    check_source(page)
    assert page.url.endswith(setup_id)
    with httpx.Client(base_url=portal["url"]) as client:
        assert client.get(f"/api/backtests/{source['id']}").json() == source


def test_conflicting_contract_selection_blocks_save_without_converting_source(page, portal):
    page.set_viewport_size({"width": 390, "height": 844})
    open_setup(page, portal, dataset_for(portal, "20"))
    fill_setup(page, fee=None, instrument_profile="nq")
    playwright.expect(page.locator("#prop-save")).to_be_enabled()
    page.locator("#prop-instrument-profile").select_option("mnq")
    playwright.expect(page.locator("#prop-instrument-summary")).to_contain_text("Saved point_value 20 does not match MNQ profile 2")
    playwright.expect(page.locator("#prop-save")).to_be_disabled()
    playwright.expect(page.locator("#prop-instrument-custom")).to_be_hidden()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.locator("#prop-instrument-profile").select_option("nq")
    playwright.expect(page.locator("#prop-save")).to_be_enabled()
    save_setup(page)

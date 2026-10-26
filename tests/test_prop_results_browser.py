"""Evaluation is usable through the final report/setup/result workflow."""

import json
import httpx

from test_backtests_browser import FIXTURES, browser, page, portal, playwright
from test_prop_browser import open_setup, fill_setup, save_setup, check_source


def run(page):
    page.locator("#prop-run").click()
    playwright.expect(page.locator("#prop-result-view")).to_be_visible()
    playwright.expect(page.locator("#prop-status")).to_contain_text("Saved historical evaluation result")


def test_run_reopen_download_compare_and_return_to_setup(page, portal):
    source = open_setup(page, portal); fill_setup(page); setup_id = save_setup(page); check_source(page)
    run(page)
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("unresolved_data_end")
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("50026")
    playwright.expect(page.locator("#prop-chart-readout")).to_contain_text("equity 50026")
    result_url = page.url
    with page.expect_download() as download:
        page.get_by_role("link", name="report.json", exact=True).click()
    result = json.loads(download.value.path().read_text())
    assert result["summary"]["balance"] == "50026" and result["setup_id"] == setup_id
    page.reload()
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text(result["id"])
    page.locator("#prop-back").click()
    playwright.expect(page.locator("#prop-results-count")).to_have_text("1 saved results")
    page.locator("#prop-results-list a").click()
    assert page.url == result_url
    page.locator("#prop-back").click()
    page.locator("#prop-quantity").fill("1")
    playwright.expect(page.locator("#prop-run")).to_be_disabled()
    save_setup(page); check_source(page); run(page)
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("50013")
    page.goto(result_url)
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("50026")


def test_result_mobile_layout_and_chart_exact_readout(page, portal):
    page.set_viewport_size({"width": 390, "height": 844})
    open_setup(page, portal); fill_setup(page); save_setup(page); check_source(page); run(page)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.locator("#prop-trace-point").fill("0")
    playwright.expect(page.locator("#prop-chart-readout")).to_contain_text("equity 5E+4")


def test_operation_failure_does_not_show_financial_result(page, portal):
    open_setup(page, portal); fill_setup(page)
    page.locator("#prop-quantity").fill("7")
    save_setup(page); check_source(page)
    page.locator("#prop-run").click()
    playwright.expect(page.locator("#prop-status")).to_contain_text("exceeds the session contract limit")
    playwright.expect(page.locator("#prop-result-view")).to_be_hidden()
    playwright.expect(page.locator("#prop-results-count")).to_have_text("0 saved results")
    playwright.expect(page.locator("#prop-run")).to_be_enabled()


def test_financial_failure_is_a_completed_saved_result(page, portal):
    lines = (FIXTURES / "arithmetic_5m.csv").read_text().splitlines()
    last = lines[-1].split(",")
    last[2:6] = ["-4.3"] * 4
    lines[-1] = ",".join(last)
    with httpx.Client(base_url=portal["url"]) as client:
        response = client.post("/api/datasets", params={"filename": "synthetic-floor.csv", "name": "Synthetic floor breach", "source_timezone": "UTC", "tick_size": "0.25", "point_value": "10"},
                               content="\n".join(lines) + "\n")
        assert response.status_code == 201, response.text
    open_setup(page, portal, dataset_id=response.json()["id"])
    fill_setup(page); save_setup(page); check_source(page); run(page)
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("failed_drawdown")
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("47900")
    page.reload()
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("failed_drawdown")


def test_publication_failure_keeps_setup_and_no_completed_result(page, portal, monkeypatch):
    open_setup(page, portal); fill_setup(page); setup = save_setup(page); check_source(page)
    store = portal["app"].state.prop_runs
    publish = store._publish

    def fail(path, table, *args):
        if table == "prop_results":
            raise OSError("Simulated publication failure")
        return publish(path, table, *args)

    monkeypatch.setattr(store, "_publish", fail)
    page.locator("#prop-run").click()
    playwright.expect(page.locator("#prop-status")).to_contain_text("Simulation operation failed")
    playwright.expect(page.locator("#prop-result-view")).to_be_hidden()
    with httpx.Client(base_url=portal["url"]) as client:
        assert client.get("/api/prop-simulations/results", params={"setup_id": setup}).json()["total"] == 0

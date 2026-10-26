"""Profile pricing is reusable through the actual backtest/setup/result flow."""

import json
from pathlib import Path

from test_backtests_browser import browser, page, portal, playwright
from test_prop_browser import open_setup, fill_setup, save_setup, check_source


def profile_fees(page, attempt, activation):
    playwright.expect(page.locator("#prop-workflow")).to_be_visible()
    if page.locator("#prop-profile-fees").get_attribute("open") is None:
        page.locator("#prop-profile-fees > summary").click()
    page.locator("#prop-profile-attempt-fee").fill(attempt)
    page.locator("#prop-profile-activation-fee").fill(activation)
    page.locator("#prop-save-profile-fees").click()
    playwright.expect(page.locator("#prop-status")).to_contain_text("Profile fees saved")


def test_reusable_fees_inherit_run_download_override_and_keep_prior_results(page, portal):
    output = Path("artifacts/prop-profile-fees")
    output.mkdir(parents=True, exist_ok=True)
    record = open_setup(page, portal)
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("49 USD")
    playwright.expect(page.locator("#prop-fee-field")).to_be_hidden()
    profile_fees(page, "35", "140")
    fill_setup(page, fee=None)
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("35 USD")
    page.screenshot(path=str(output / "profile-fees.png"), full_page=True)
    first = save_setup(page)
    check_source(page)
    page.locator("#prop-run").click()
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("50026")
    result_url = page.url
    with page.expect_download() as download:
        page.get_by_role("link", name="report.json", exact=True).click()
    result = json.loads(download.value.path().read_text())
    assert result["summary"]["external_costs"] == "35"
    assert result["summary"]["modeled_net_cash"] == "-35"
    assert result["resolved"]["config"]["fees"]["origin"] == "profile_default"
    (output / "report.json").write_bytes(download.value.path().read_bytes())
    page.screenshot(path=str(output / "evaluation-result.png"), full_page=True)
    page.locator("#prop-back").click()
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("35 USD from the saved profile")
    profile_fees(page, "49", "150")
    second = save_setup(page)
    assert first != second
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("49 USD")
    page.goto(result_url)
    with page.expect_download() as download:
        page.get_by_role("link", name="report.json", exact=True).click()
    assert json.loads(download.value.path().read_text()) == result
    # A fresh setup inherits the persisted values, without any price input.
    page.goto(portal["url"] + "/#backtests/prop/new/" + record["id"])
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("49 USD")
    page.locator("#prop-phase").select_option("funded")
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("150 USD")
    page.locator("#prop-phase").select_option("evaluation")
    fill_setup(page, fee="0")
    override = save_setup(page)
    with page.expect_download() as download:
        page.get_by_role("link", name="simulation.json", exact=True).click()
    config = json.loads(download.value.path().read_text())["config"]
    assert config["fees"]["attempt_fee"] == "0" and config["fees"]["origin"] == "user_supplied"
    page.reload()
    playwright.expect(page.locator("#prop-fee-override")).to_be_checked()
    playwright.expect(page.locator("#prop-fee")).to_have_value("0")
    assert page.url.endswith(override)


def test_profile_switch_resets_override_and_failed_price_save_is_visible(page, portal):
    open_setup(page, portal)
    profile_fees(page, "35", "140")
    fill_setup(page, "0")
    page.locator("#prop-profile").select_option("apex_50k_eod_tradovate")
    playwright.expect(page.locator("#prop-fee-override")).not_to_be_checked()
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("49 USD")
    if page.locator("#prop-profile-fees").get_attribute("open") is None:
        page.locator("#prop-profile-fees > summary").click()
    page.locator("#prop-profile-attempt-fee").fill("-1")
    page.locator("#prop-save-profile-fees").click()
    playwright.expect(page.locator("#prop-status")).to_contain_text("Profile fees not saved")
    page.locator("#prop-profile").select_option("apex_50k_eod_rithmic")
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("35 USD")
    playwright.expect(page.locator("#prop-profile-attempt-fee")).to_have_value("35")


def test_choose_both_user_pricing_options_run_and_reopen(page, portal):
    output = Path("artifacts/prop-pricing-options")
    output.mkdir(parents=True, exist_ok=True)
    source = open_setup(page, portal)
    urls = []
    for suffix, name, attempt in (("", "standard", 49), ("_no_activation", "no-activation", 109)):
        if urls:
            page.goto(portal["url"] + "/#backtests/prop/new/" + source["id"])
            playwright.expect(page.locator("#prop-workflow")).to_be_visible()
        page.locator("#prop-profile").select_option("apex_50k_eod_rithmic" + suffix)
        playwright.expect(page.locator("#prop-fee-summary")).to_contain_text(f"{attempt} USD")
        playwright.expect(page.locator("#prop-fee-field")).to_be_hidden()
        fill_setup(page, fee=None)
        save_setup(page); check_source(page)
        page.locator("#prop-run").click()
        playwright.expect(page.locator("#prop-result-summary")).to_contain_text("50026")
        playwright.expect(page.locator("#prop-result-summary")).to_contain_text("No activation fee" if suffix else "Standard")
        urls.append(page.url)
        with page.expect_download() as download:
            page.get_by_role("link", name="report.json", exact=True).click()
        result = json.loads(download.value.path().read_text())
        assert result["summary"]["balance"] == "50026"
        assert result["summary"]["external_costs"] == str(attempt)
        assert result["summary"]["modeled_net_cash"] == str(-attempt)
        (output / f"{name}-report.json").write_bytes(download.value.path().read_bytes())
        page.screenshot(path=str(output / f"{name}-result.png"), full_page=True)
    page.goto(urls[0])
    playwright.expect(page.locator("#prop-result-summary")).to_contain_text("Standard")
    with page.expect_download() as download:
        page.get_by_role("link", name="report.json", exact=True).click()
    assert json.loads(download.value.path().read_text())["summary"]["external_costs"] == "49"
    page.goto(portal["url"] + "/#backtests/prop/new/" + source["id"])
    playwright.expect(page.locator("#prop-workflow")).to_be_visible()
    page.locator("#prop-profile").select_option("apex_50k_eod_rithmic_no_activation")
    page.locator("#prop-phase").select_option("funded")
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("0 USD")
    fill_setup(page, fee=None); save_setup(page)
    playwright.expect(page.locator("#prop-run")).to_be_disabled()
    page.reload()
    playwright.expect(page.locator("#prop-fee-summary")).to_contain_text("0 USD")

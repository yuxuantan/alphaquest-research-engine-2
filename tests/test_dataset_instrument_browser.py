"""Dataset defaults populate editable, isolated run settings."""

import httpx

from test_backtests_browser import browser, page, portal, prepare, playwright, FIXTURES, post_requests


def test_upload_edit_reload_and_use_dataset_settings_in_backtest(page, portal):
    page.goto(portal["url"])
    page.locator("#csv-file").set_input_files(FIXTURES / "doji_and_red_reset.csv")
    page.locator("#dataset-tick-size").fill("0.125")
    page.locator("#dataset-point-value").fill("5.000000000000000000000000001")
    page.locator("#validate-button").click()
    playwright.expect(page.locator("#validation-result")).to_contain_text("Validation passed")
    page.locator("#save-button").click()
    playwright.expect(page.locator("#validation-result")).to_contain_text("Dataset saved")
    page.get_by_role("button", name="doji_and_red_reset", exact=True).click()
    playwright.expect(page.locator("#detail-tick_size")).to_have_value("0.125")
    playwright.expect(page.locator("#detail-point_value")).to_have_value("5.000000000000000000000000001")
    page.locator("#close-dialog").click()
    page.get_by_role("button", name="Edit defaults for arithmetic_5m", exact=True).click()
    playwright.expect(page.locator("#detail-tick_size")).to_be_focused()
    page.locator("#detail-tick_size").fill("0.5")
    page.locator("#detail-point_value").fill("20")
    page.get_by_role("button", name="Save instrument settings", exact=True).click()
    playwright.expect(page.locator("#instrument-save-status")).to_contain_text("Instrument settings saved")
    page.reload()
    page.get_by_role("button", name="Edit defaults for arithmetic_5m", exact=True).click()
    playwright.expect(page.locator("#detail-tick_size")).to_have_value("0.5")
    playwright.expect(page.locator("#detail-point_value")).to_have_value("20")
    page.locator("#close-dialog").click()
    prepare(page, portal)
    playwright.expect(page.locator("#backtest-instrument-settings [data-instrument='tick_size'] dd")).to_have_text("0.5")
    playwright.expect(page.locator("#backtest-instrument-settings [data-instrument='point_value'] dd")).to_have_text("20")
    playwright.expect(page.locator("#backtest-tick-size")).to_have_value("0.5")
    requests = post_requests(page)
    with page.expect_response(lambda response: "/api/backtests?" in response.url and response.request.method == "POST") as finished:
        page.locator("#start-backtest").click()
    record = finished.value.json()
    assert finished.value.status == 201
    assert requests[0].post_data_json["execution_settings"]["tick_size"] == "0.5"
    assert requests[0].post_data_json["execution_settings"]["point_value"] == "20"
    assert record["execution_settings"]["tick_size"] == "0.5"
    assert record["execution_settings"]["point_value"] == "20"
    assert record["summary"]["total_net_pnl"] == "36.0"


def test_existing_dataset_requires_configuration_and_save_errors_are_visible(page, portal):
    with httpx.Client(base_url=portal["url"]) as client:
        legacy = client.post("/api/datasets", params={"filename": "end.csv", "name": "Unconfigured", "source_timezone": "UTC"},
                             content=(FIXTURES / "end_of_data.csv").read_bytes()).json()
    prepare(page, portal)
    page.locator("#backtest-dataset").select_option(legacy["id"])
    playwright.expect(page.locator("#start-backtest")).to_be_disabled()
    playwright.expect(page.locator("#backtest-instrument-status")).to_contain_text("Set tick size and monetary point value")
    page.get_by_role("link", name="Edit instrument settings in Datasets →", exact=True).click()
    page.get_by_role("button", name="Unconfigured", exact=True).click()
    patches = []
    page.on("request", lambda request: patches.append(request) if request.method == "PATCH" else None)
    page.locator("#detail-tick_size").fill("0")
    page.locator("#detail-point_value").fill("10")
    page.get_by_role("button", name="Save instrument settings", exact=True).click()
    assert patches == []
    page.locator("#detail-tick_size").fill("0.25")
    page.route("**/instrument-settings", lambda route: route.fulfill(status=422, json={"detail": "Settings rejected for review"}))
    page.get_by_role("button", name="Save instrument settings", exact=True).click()
    playwright.expect(page.locator("#instrument-save-status")).to_have_text("Settings rejected for review")
    playwright.expect(page.get_by_role("button", name="Save instrument settings", exact=True)).to_be_enabled()
    page.unroute("**/instrument-settings")
    page.get_by_role("button", name="Save instrument settings", exact=True).click()
    playwright.expect(page.locator("#instrument-save-status")).to_contain_text("Instrument settings saved")
    page.locator("#close-dialog").click()
    page.get_by_role("link", name="Backtests", exact=True).click()
    playwright.expect(page.locator("#backtest-dataset")).to_have_value(legacy["id"])
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    playwright.expect(page.locator("#backtest-instrument-settings")).to_contain_text("0.25")


def test_dataset_selection_updates_instrument_defaults_and_values(page, portal):
    with httpx.Client(base_url=portal["url"]) as client:
        result = client.patch(f"/api/datasets/{portal['saved']['gap_deadline']['id']}/instrument-settings",
                              json={"tick_size": "0.01", "point_value": "2"})
        assert result.status_code == 200
    prepare(page, portal)
    playwright.expect(page.locator("#backtest-instrument-settings [data-instrument='point_value'] dd")).to_have_text("10")
    page.locator("#backtest-dataset").select_option(portal["saved"]["gap_deadline"]["id"])
    playwright.expect(page.locator("#backtest-instrument-settings [data-instrument='tick_size'] dd")).to_have_text("0.01")
    playwright.expect(page.locator("#backtest-instrument-settings [data-instrument='point_value'] dd")).to_have_text("2")


def test_run_overrides_reset_switch_dataset_preserve_drafts_and_reopen_report(page, portal):
    with httpx.Client(base_url=portal["url"]) as client:
        response = client.patch(f"/api/datasets/{portal['saved']['gap_deadline']['id']}/instrument-settings",
                                json={"tick_size": "0.01", "point_value": "2"})
        assert response.status_code == 200
    prepare(page, portal)
    playwright.expect(page.locator("#backtest-tick-size")).to_have_value("0.25")
    playwright.expect(page.locator("#backtest-point-value")).to_have_value("10")
    page.locator("#backtest-tick-size").fill("0.5")
    page.locator("#backtest-point-value").fill("20")
    playwright.expect(page.locator("#backtest-instrument-status")).to_contain_text("edited for this run")
    page.get_by_role("link", name="Datasets", exact=True).click()
    page.get_by_role("link", name="Backtests", exact=True).click()
    playwright.expect(page.locator("#backtest-tick-size")).to_have_value("0.5")
    playwright.expect(page.locator("#backtest-point-value")).to_have_value("20")
    with page.expect_response(lambda response: response.url.endswith('/api/datasets')):
        page.locator("#refresh-backtest-choices").click()
    playwright.expect(page.locator("#reset-instrument-defaults")).to_be_enabled()
    playwright.expect(page.locator("#backtest-point-value")).to_have_value("20")
    page.locator("#reset-instrument-defaults").click()
    playwright.expect(page.locator("#backtest-tick-size")).to_have_value("0.25")
    playwright.expect(page.locator("#backtest-point-value")).to_have_value("10")
    page.locator("#backtest-point-value").fill("99")
    page.locator("#backtest-dataset").select_option(portal["saved"]["gap_deadline"]["id"])
    playwright.expect(page.locator("#backtest-tick-size")).to_have_value("0.01")
    playwright.expect(page.locator("#backtest-point-value")).to_have_value("2")
    page.locator("#backtest-dataset").select_option(portal["saved"]["arithmetic_5m"]["id"])
    playwright.expect(page.locator("#backtest-point-value")).to_have_value("10")
    page.locator("#backtest-tick-size").fill("0.5")
    page.locator("#backtest-point-value").fill("20")
    requests = post_requests(page)
    with page.expect_response(lambda response: "/api/backtests?" in response.url and response.request.method == "POST") as finished:
        page.locator("#start-backtest").click()
    record = finished.value.json()
    assert finished.value.status == 201
    assert requests[0].post_data_json["execution_settings"]["tick_size"] == "0.5"
    assert requests[0].post_data_json["execution_settings"]["point_value"] == "20"
    assert record["run_metadata"]["instrument_overrides"] == {"tick_size": "0.5", "point_value": "20"}
    assert record["summary"]["total_net_pnl"] == "36.0"
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    page.get_by_text("Dataset, strategy & settings used", exact=True).click()
    overrides = page.locator("[data-instrument-overrides] dd")
    playwright.expect(overrides).to_have_text("Tick size: 0.5 · Monetary point value: 20")
    playwright.expect(page.locator("[data-setting='tick_size'] dd")).to_have_text("0.5")
    page.reload()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    page.get_by_text("Dataset, strategy & settings used", exact=True).click()
    playwright.expect(overrides).to_have_text("Tick size: 0.5 · Monetary point value: 20")
    with httpx.Client(base_url=portal["url"]) as client:
        dataset = client.get(f"/api/datasets/{portal['saved']['arithmetic_5m']['id']}").json()
    assert dataset == portal["saved"]["arithmetic_5m"]
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_invalid_run_instrument_value_is_blocked_before_submission(page, portal):
    prepare(page, portal)
    requests = post_requests(page)
    page.locator("#backtest-tick-size").fill("0")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-error")).to_contain_text("greater than zero")
    assert requests == []
    page.locator("#reset-instrument-defaults").click()
    playwright.expect(page.locator("#backtest-tick-size")).to_have_value("0.25")
    assert page.locator("#backtest-tick-size").evaluate("input => input.checkValidity()")

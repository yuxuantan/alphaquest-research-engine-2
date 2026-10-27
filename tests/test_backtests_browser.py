"""Real Chromium checks against the local FastAPI app; optional browser extra."""

from pathlib import Path
import re
import socket
from threading import Event, Thread
import time

import httpx
import pytest
import uvicorn

playwright = pytest.importorskip("playwright.sync_api")

from alphaquest.app import create_app
from alphaquest.backtest_runs import RunStore
from alphaquest.strategies import consecutive_green_hold as sample


FIXTURES = Path(__file__).parent / "fixtures/backtest_contract"


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as runtime:
        instance = runtime.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def portal(tmp_path):
    app = create_app(tmp_path / "datasets.sqlite3")
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", loop="asyncio"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "Browser test server did not start"
            time.sleep(.01)
        saved = {}
        with httpx.Client(base_url=url) as client:
            for name, zone in (("arithmetic_5m", "UTC"), ("gap_deadline", "America/New_York")):
                response = client.post("/api/datasets", params={"filename": name + ".csv", "name": name, "source_timezone": zone, "tick_size": "0.25", "point_value": "10"},
                                       content=(FIXTURES / (name + ".csv")).read_bytes())
                assert response.status_code == 201, response.text
                saved[name] = response.json()
        yield {"url": url, "saved": saved, "app": app}
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive(), "Browser test server failed to stop"


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    context.close()
    assert errors == [], errors


def prepare(page, portal):
    page.goto(portal["url"] + "/#backtests")
    playwright.expect(page.locator("#strategy-parameters input")).to_have_count(3)
    page.locator("#backtest-dataset").select_option(portal["saved"]["arithmetic_5m"]["id"])
    page.locator("#backtest-slippage-ticks").fill("1")
    page.locator("#backtest-commission").fill("1")
    page.locator("#strategy-contracts").fill("2")


def post_requests(page):
    requests = []
    page.on("request", lambda request: requests.append(request) if request.method == "POST" and "/api/backtests?" in request.url else None)
    return requests


def test_dataset_strategy_selection_description_parameters_and_navigation(page, portal):
    prepare(page, portal)
    playwright.expect(page.locator("#strategy-description")).to_have_text(sample.DESCRIPTION)
    playwright.expect(page.locator("#strategy-green_bar_count")).to_have_value("3")
    playwright.expect(page.locator("#strategy-hold_minutes")).to_have_value("20")
    playwright.expect(page.get_by_label("Number of contracts", exact=True)).to_have_value("2")
    page.locator("#backtest-dataset").select_option(portal["saved"]["gap_deadline"]["id"])
    playwright.expect(page.locator("#backtest-timezone")).to_have_text("America/New_York")
    playwright.expect(page.locator("#backtest-dataset-info")).to_contain_text("19:00:00 UTC")
    playwright.expect(page.locator("#backtest-assumptions-heading")).to_contain_text("bar closes")
    playwright.expect(page.locator("#point-value-help")).to_contain_text("per contract")
    page.locator("#strategy-green_bar_count").fill("2")
    page.locator("#strategy-hold_minutes").fill("7")
    page.get_by_role("link", name="Datasets", exact=True).click()
    playwright.expect(page.locator("#datasets-screen")).to_be_visible()
    page.get_by_role("link", name="Strategies", exact=True).click()
    page.get_by_role("link", name="New backtest →", exact=True).click()
    playwright.expect(page.locator("#strategy-green_bar_count")).to_have_value("2")
    playwright.expect(page.locator("#strategy-hold_minutes")).to_have_value("7")
    playwright.expect(page.locator("#backtest-dataset")).to_have_value(portal["saved"]["gap_deadline"]["id"])


def test_strategy_fields_follow_backend_definitions_when_selection_changes(page, portal):
    with httpx.Client(base_url=portal["url"]) as client:
        definitions = client.get("/api/strategies").json()
    alternate = {"id": "alternate_definition", "description": "A browser-only alternate parameter definition.",
                 "parameters": [{"name": "trigger_length", "type": "int", "default": 5, "minimum": 1, "description": "Alternate trigger length."}]}
    page.route("**/api/strategies", lambda route: route.fulfill(json=definitions + [alternate]))
    page.goto(portal["url"] + "/#backtests")
    page.locator("#backtest-strategy").select_option("consecutive_green_hold")
    page.locator("#strategy-green_bar_count").fill("4")
    page.locator("#backtest-strategy").select_option("alternate_definition")
    playwright.expect(page.locator("#strategy-description")).to_have_text(alternate["description"])
    playwright.expect(page.locator("#strategy-parameters input")).to_have_count(1)
    playwright.expect(page.get_by_label("Trigger length", exact=True)).to_have_value("5")
    page.locator("#backtest-strategy").select_option("consecutive_green_hold")
    playwright.expect(page.locator("#strategy-parameters input")).to_have_count(3)
    playwright.expect(page.locator("#strategy-green_bar_count")).to_have_value("4")


def test_exact_submitted_configuration_and_saved_completion_summary(page, portal):
    with httpx.Client(base_url=portal["url"]) as client:
        response = client.patch(f"/api/datasets/{portal['saved']['arithmetic_5m']['id']}/instrument-settings",
                                json={"tick_size": "0.25", "point_value": "10.000000000000000000000000001"})
        assert response.status_code == 200
    prepare(page, portal)
    page.locator("#strategy-green_bar_count").fill("2")
    page.locator("#strategy-hold_minutes").fill("7")
    page.locator("#backtest-initial-capital").fill("10000.123456789123456789123456789")
    requests = post_requests(page)
    with page.expect_response(lambda response: "/api/backtests?" in response.url and response.request.method == "POST") as completed:
        page.locator("#start-backtest").click()
    record = completed.value.json()
    assert completed.value.status == 201
    assert len(requests) == 1
    submitted = requests[0].post_data_json
    assert submitted == {
        "dataset_id": portal["saved"]["arithmetic_5m"]["id"], "strategy_id": "consecutive_green_hold",
        "strategy_parameters": {"green_bar_count": 2, "hold_minutes": 7, "contracts": 2},
        "execution_settings": {"initial_capital": "10000.123456789123456789123456789", "slippage_ticks": 1,
                               "commission_per_contract_per_side": "1", "tick_size": "0.25", "point_value": "10.000000000000000000000000001"},
    }
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    playwright.expect(page.locator("#backtest-completion-content")).to_contain_text(record["id"])
    playwright.expect(page.locator("#backtest-completion-content [data-setting='point_value'] dd")).to_have_text("10.000000000000000000000000001")
    playwright.expect(page.locator("#backtest-completion-content [data-setting='contracts'] dd")).to_have_text("2")
    playwright.expect(page.locator("#backtest-completion-content [data-setting='green_bar_count'] dd")).to_have_text("2")
    playwright.expect(page.locator("#backtest-completion-content [data-setting='hold_minutes'] dd")).to_have_text("7")
    assert record["execution_settings"] == {**submitted["execution_settings"], "tick_size": "0.25", "point_value": "10.000000000000000000000000001"}
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()


def test_live_progress_elapsed_saving_and_duplicate_submission_protection(page, portal, monkeypatch):
    entered, release, saving, release_save = Event(), Event(), Event(), Event()
    original_bar = sample.ConsecutiveGreenHold.on_bar
    original_complete = RunStore.complete

    def paused_bar(self, bar, position):
        if bar.bar_number == 3:
            entered.set()
            assert release.wait(15)
        return original_bar(self, bar, position)

    def paused_save(self, *args):
        saving.set()
        assert release_save.wait(15)
        return original_complete(self, *args)

    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", paused_bar)
    monkeypatch.setattr(RunStore, "complete", paused_save)
    prepare(page, portal)
    requests = post_requests(page)
    polls = []

    def temporary_poll_failure(route):
        polls.append(1)
        if len(polls) == 1:
            route.fulfill(status=503, json={"detail": "Temporary progress interruption"})
        else:
            route.continue_()

    page.route("**/api/progress/*", temporary_poll_failure)
    try:
        page.locator("#start-backtest").click()
        assert entered.wait(5)
        playwright.expect(page.locator("#backtest-progress-detail")).to_have_text("2 / 7 bars processed")
        playwright.expect(page.locator("#backtest-elapsed")).to_have_text(re.compile(r"[1-9]\d*s elapsed"))
        playwright.expect(page.locator("#start-backtest")).to_be_disabled()
        playwright.expect(page.locator("#refresh-backtest-choices")).to_be_disabled()
        playwright.expect(page.locator("#strategy-contracts")).to_be_disabled()
        playwright.expect(page.locator("#reset-instrument-defaults")).to_be_disabled()
        playwright.expect(page.locator("#backtest-tick-size")).to_be_disabled()
        playwright.expect(page.locator("#backtest-point-value")).to_be_disabled()
        box = page.locator("#start-backtest").bounding_box()
        page.mouse.click(box["x"] + 5, box["y"] + 5, click_count=2)
        page.locator("#backtest-form").evaluate("form => { for (let i=0;i<3;i++) form.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true})); }")
        assert len(requests) == 1
        release.set()
        assert saving.wait(5)
        playwright.expect(page.locator("#backtest-progress-title")).to_have_text("Saving run results")
        playwright.expect(page.locator("#backtest-progress-detail")).to_have_text("7 / 7 bars processed")
        playwright.expect(page.locator("#start-backtest")).to_be_disabled()
        playwright.expect(page.locator("#backtest-completion")).to_be_hidden()
    finally:
        release.set()
        release_save.set()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    assert len(requests) == 1 and len(polls) > 1


def test_client_validation_and_server_validation_errors_are_visible(page, portal):
    prepare(page, portal)
    requests = post_requests(page)
    page.locator("#backtest-initial-capital").fill("0")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-error")).to_contain_text("greater than zero")
    assert requests == []
    page.locator("#backtest-initial-capital").fill("10000")
    page.locator("#strategy-green_bar_count").fill("2.5")
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-error")).to_be_visible()
    assert requests == []
    page.locator("#strategy-green_bar_count").fill("3")
    page.route("**/api/backtests?*", lambda route: route.fulfill(status=422, json={"detail": [
        {"loc": ["body", "execution_settings", "initial_capital"], "msg": "Initial capital rejected by server"},
    ]}))
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-error")).to_contain_text("Initial capital rejected by server")
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    playwright.expect(page.locator("#backtest-completion")).to_be_hidden()
    assert len(requests) == 1


def test_execution_failure_and_lost_connection_never_show_success(page, portal, monkeypatch):
    def broken(*args):
        raise RuntimeError("Browser review execution failure")

    monkeypatch.setattr(sample.ConsecutiveGreenHold, "on_bar", broken)
    prepare(page, portal)
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-error")).to_contain_text("no completed run was saved")
    playwright.expect(page.locator("#backtest-completion")).to_be_hidden()
    playwright.expect(page.locator("#start-backtest")).to_be_enabled()
    requests = post_requests(page)
    page.route("**/api/backtests?*", lambda route: route.abort())
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-error")).to_contain_text("Completion is unconfirmed")
    playwright.expect(page.locator("#backtest-completion")).to_be_hidden()
    assert len(requests) == 1


def test_loading_error_can_be_retried_and_empty_library_is_clear(page, portal):
    page.route("**/api/strategies", lambda route: route.fulfill(status=500, json={"detail": "Strategy registry unavailable"}))
    page.goto(portal["url"] + "/#backtests")
    playwright.expect(page.locator("#backtest-error")).to_contain_text("Strategy registry unavailable")
    playwright.expect(page.locator("#start-backtest")).to_be_disabled()
    page.unroute("**/api/strategies")
    page.locator("#refresh-backtest-choices").click()
    playwright.expect(page.locator("#strategy-parameters input")).to_have_count(3)
    page.route("**/api/datasets", lambda route: route.fulfill(json=[]))
    page.locator("#refresh-backtest-choices").click()
    playwright.expect(page.locator("#backtest-options-status")).to_contain_text("No supported saved datasets")
    playwright.expect(page.locator("#start-backtest")).to_be_disabled()


def test_dataset_upload_preview_download_and_delete_still_work(page, portal):
    page.goto(portal["url"])
    source = FIXTURES / "doji_and_red_reset.csv"
    page.locator("#csv-file").set_input_files(source)
    page.locator("#validate-button").click()
    playwright.expect(page.locator("#validation-result")).to_contain_text("Validation passed")
    page.locator("#save-button").click()
    playwright.expect(page.locator("#validation-result")).to_contain_text("Dataset saved")
    page.get_by_role("button", name="doji_and_red_reset", exact=True).click()
    playwright.expect(page.locator("#dataset-dialog")).to_be_visible()
    playwright.expect(page.locator("#detail-content")).to_contain_text("UTC")
    page.locator("#close-dialog").click()
    with page.expect_download() as downloaded:
        page.get_by_role("link", name="Download doji_and_red_reset", exact=True).click()
    assert Path(downloaded.value.path()).read_bytes() == source.read_bytes()
    page.get_by_role("link", name="Strategies", exact=True).click()
    page.get_by_role("link", name="New backtest →", exact=True).click()
    playwright.expect(page.locator("#backtest-dataset option")).to_have_count(4)
    page.get_by_role("link", name="Datasets", exact=True).click()
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete doji_and_red_reset", exact=True).click()
    playwright.expect(page.get_by_role("button", name="doji_and_red_reset", exact=True)).to_have_count(0)
    page.get_by_role("link", name="Strategies", exact=True).click()
    page.get_by_role("link", name="New backtest →", exact=True).click()
    playwright.expect(page.locator("#backtest-dataset option")).to_have_count(3)


def test_mobile_navigation_and_layout(page, portal):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(portal["url"])
    page.get_by_role("link", name="Strategies", exact=True).click()
    page.get_by_role("link", name="New backtest →", exact=True).click()
    playwright.expect(page.locator("#strategy-parameters input")).to_have_count(3)
    playwright.expect(page.locator("#backtests-screen")).to_be_visible()
    playwright.expect(page.locator("#backtest-assumptions-heading")).to_have_text("Timestamps label bar closes.")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("link", name="Datasets", exact=True).click()
    playwright.expect(page.locator("#datasets-screen")).to_be_visible()


def test_vwap_controls_preserve_boolean_decimal_types_and_execution_settings(page, portal):
    prepare(page, portal)
    page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
    playwright.expect(page.locator("#strategy-parameters input")).to_have_count(32)
    playwright.expect(page.locator("#strategy-trade_longs")).to_be_checked()
    playwright.expect(page.locator("#strategy-trade_shorts")).not_to_be_checked()
    playwright.expect(page.locator("#backtest-fill-assumption")).to_contain_text("next observed bar Open")
    page.locator("#strategy-trade_shorts").check()
    page.locator("#strategy-mm_risk_pct").fill("1.25")
    page.locator("#strategy-position_size").fill("2")
    page.locator("#backtest-strategy").select_option("consecutive_green_hold")
    page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
    playwright.expect(page.locator("#strategy-trade_shorts")).to_be_checked()
    playwright.expect(page.locator("#strategy-mm_risk_pct")).to_have_value("1.25")
    requests = post_requests(page)
    page.locator("#start-backtest").click()
    playwright.expect(page.locator("#backtest-completion")).to_be_visible()
    assert len(requests) == 1
    submitted = requests[0].post_data_json
    values = submitted["strategy_parameters"]
    assert values["trade_shorts"] is True and values["use_vol_sizing"] is False
    assert values["mm_risk_pct"] == "1.25" and values["position_size"] == 2
    assert set(submitted["execution_settings"]) == {"initial_capital", "tick_size", "point_value", "slippage_ticks", "commission_per_contract_per_side"}
    playwright.expect(page.locator("#backtest-completion-content [data-setting='mm_risk_pct'] dd")).to_have_text("1.25")
    playwright.expect(page.locator("#backtest-completion-content")).to_contain_text("next_open_market_next_bar_bracket_stop_first")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_inferred_early_close_is_usable_from_normal_backtest_screen(page, portal):
    from test_inferred_session_close import session_rows, csv_bytes
    prepare(page, portal)
    with httpx.Client(base_url=portal["url"]) as client:
        saved = client.post("/api/datasets", params={"filename": "synthetic-early-close.csv", "name": "SYNTHETIC early close",
            "source_timezone": "UTC", "tick_size": "0.25", "point_value": "20"}, content=csv_bytes(session_rows()))
        assert saved.status_code == 201, saved.text
        dataset_id = saved.json()["id"]
    page.reload()
    page.locator("#backtest-dataset").select_option(dataset_id)
    page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
    page.locator("#strategy-stop_swing_len").fill("1")
    page.locator("#strategy-target_swing_len").fill("1")
    page.locator("#strategy-use_adx_elev").uncheck()
    page.locator("#strategy-use_adx_decay").uncheck()
    page.locator("#strategy-use_eod_flat").check()
    page.locator("#backtest-slippage-ticks").fill("1")
    page.locator("#backtest-commission").fill("1")
    playwright.expect(page.locator("#backtest-fill-assumption")).to_contain_text("BACKTEST LOOKAHEAD")
    with page.expect_response(lambda response: "/api/backtests?" in response.url and response.request.method == "POST") as completed:
        page.locator("#start-backtest").click()
    record = completed.value.json()
    assert completed.value.status == 201, record
    assert record["summary"]["total_net_pnl"] == "48.00"
    playwright.expect(page.locator("#backtest-completion-content [data-setting='session_flattening']")).to_contain_text("1 inferred sessions")
    with httpx.Client(base_url=portal["url"]) as client:
        trade = client.get(f"/api/backtests/{record['id']}/trades").json()["items"][0]
        assert trade["exit_time_utc"] == "2026-01-05T17:55:00Z" and trade["exit_reason"] == "eod_flat"
    page.reload()
    playwright.expect(page.locator("#backtest-completion-content [data-setting='session_flattening']")).to_contain_text("Backtest lookahead")

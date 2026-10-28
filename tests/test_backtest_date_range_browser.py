"""Chromium selection, submitted dates, progress count and report reopening."""

from research_fixtures import ResearchHTTPClient,declare_in_form,declaration

from pathlib import Path

import httpx
from test_backtests_browser import browser, page, portal, prepare, post_requests, playwright
from test_backtest_date_range import raw_days

expect = playwright.expect


def save_days(portal):
    with ResearchHTTPClient(base_url=portal["url"]) as client:
        response = client.post("/api/datasets", params={"filename": "range.csv", "name": "Three day range", "source_timezone": "Asia/Singapore", "tick_size": "0.25", "point_value": "10"}, content=raw_days())
        assert response.status_code == 201, response.text
        return response.json()


def test_select_run_and_reopen_one_day_in_source_timezone(page, portal):
    saved = save_days(portal)
    prepare(page, portal)
    page.locator("#backtest-dataset").select_option(saved["id"])
    expect(page.locator("#backtest-date-range-help")).to_contain_text("inclusive in Asia/Singapore")
    # The dates remain while switching strategies and portal screens.
    page.locator("#backtest-strategy").select_option("vwap_pullback_risk_sizing")
    page.locator("#backtest-strategy").select_option("consecutive_green_hold")
    declare_in_form(page,dict(mode="dates",is_start="2026-01-05",is_end="2026-01-05",oos_start="2026-01-06",oos_end="2026-01-06"))
    expect(page.locator("#start-backtest")).to_be_enabled()
    page.get_by_role("link", name="Datasets", exact=True).click()
    page.get_by_role("link", name="Strategies", exact=True).click()
    page.get_by_role("link", name="New backtest →", exact=True).click()
    expect(page.locator("#backtest-from-date")).to_have_value("2026-01-05")
    requests = post_requests(page)
    with page.expect_response(lambda r: "/api/backtests?" in r.url and r.request.method == "POST") as completed:
        page.locator("#start-backtest").click()
    assert completed.value.status == 201
    record = completed.value.json()
    assert len(requests) == 1
    assert requests[0].post_data_json["sample_split"]["is_start"] == requests[0].post_data_json["sample_split"]["is_end"] == "2026-01-05"
    assert record["run_metadata"]["selection"]["row_count"] == 5
    expect(page.locator("#backtest-completion")).to_be_visible()
    expect(page.locator("#report-net")).to_have_text("26.00")
    expect(page.locator("#report-trades")).to_have_text("1")
    expect(page.locator("#backtest-progress-detail")).to_have_text("5 / 5 bars processed")
    page.locator("details.report-panel summary").click()
    content = page.locator("#backtest-completion-content")
    expect(content).to_contain_text("From date (inclusive)")
    expect(content).to_contain_text("2026-01-05")
    expect(content).to_contain_text("Bars used")
    expect(content).to_contain_text("Source dataset bars")
    expect(content).to_contain_text("2026-01-04T16:00:00Z")
    page.reload()
    expect(page.locator("#backtest-completion")).to_be_visible()
    expect(page.locator("#backtest-completion-content")).to_contain_text("2026-01-05")
    for kind in ("trades", "equity"):
        with page.expect_download() as downloaded:
            page.locator(f"#report-{kind}-download").click()
        source = portal["app"].state.runs.root / record["id"] / f"{kind}.csv"
        assert Path(downloaded.value.path()).read_bytes() == source.read_bytes()


def test_invalid_missing_and_locked_research_range(page, portal):
    saved = save_days(portal)
    prepare(page, portal)
    page.locator("#backtest-dataset").select_option(saved["id"])
    requests = post_requests(page)
    split=dict(mode="dates",is_start="2026-01-06",is_end="2026-01-04",oos_start="2026-01-07",oos_end="2026-01-07")
    declare_in_form(page,split)
    expect(page.locator("#sample-status")).to_contain_text("on or before")
    expect(page.locator("#start-backtest")).to_be_disabled()
    assert requests == []
    page.locator("#backtest-from-date").fill("2026-01-05")
    page.locator("#backtest-to-date").fill("")
    page.locator("#sample-review").click()
    expect(page.locator("#sample-status")).to_contain_text("requires IS start/end")
    expect(page.locator("#start-backtest")).to_be_disabled()
    page.locator("#backtest-to-date").fill("2026-01-06")
    page.locator("#sample-review").click()
    expect(page.locator("#start-backtest")).to_be_enabled()
    page.locator("#start-backtest").click()
    expect(page.locator("#backtest-completion")).to_be_visible()
    expect(page.locator("#report-trades")).to_have_text("2")
    assert requests[-1].post_data_json["sample_split"]["is_end"] == "2026-01-06"
    page.goto(portal['url']+'/#backtests/new')
    expect(page.locator("#sample-split-mode")).to_be_enabled()
    expect(page.locator("#sample-status")).to_contain_text("editable")
    expect(page.locator("#backtest-from-date")).to_be_enabled()

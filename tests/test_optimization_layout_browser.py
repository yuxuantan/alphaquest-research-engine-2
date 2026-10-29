"""Column visibility and ordering through the saved optimization workflow."""

import json

from test_backtests_browser import browser, page, portal, playwright
from test_optimization_browser import prepare, run
from test_optimization_columns_browser import frozen_keys, fits


def visible_keys(page):
    return page.locator("#optimization-results thead th:not([hidden])").evaluate_all("cells => cells.map(cell => cell.dataset.column)")


def show_only(page, keys):
    for row in page.locator(".optimization-column-choice").all():
        field = row.locator('[data-control="show"]')
        field.set_checked(row.get_attribute("data-column") in keys)


def test_select_columns_reorder_both_groups_sort_and_persist(page, portal, tmp_path):
    prepare(page, portal)
    run(page)
    job_id = page.url.rsplit("/", 1)[1]
    endpoint = f"{portal['url']}/api/backtests/batches/{job_id}/results"
    before = page.request.get(endpoint).json()
    mutations = []
    page.on("request", lambda request: mutations.append(request.url) if request.method in ("POST", "PUT", "PATCH", "DELETE") else None)
    page.locator("#optimization-freeze summary").click()
    show_only(page, ["trial", "param.contracts", "total_net_pnl", "run_id"])
    playwright.expect(page.locator("#optimization-results thead th:not([hidden])")).to_have_count(4)
    assert visible_keys(page) == ["trial", "param.contracts", "total_net_pnl", "run_id"]
    # A keyboard user can reorder a scrolling metric without losing focus.
    move = page.get_by_role("button", name="Move Total net pnl earlier", exact=True)
    move.focus()
    page.keyboard.press("Space")
    playwright.expect(move).to_be_focused()
    playwright.expect(page.locator('#optimization-results thead th:not([hidden])').nth(1)).to_have_attribute("data-column", "total_net_pnl")
    assert visible_keys(page) == ["trial", "total_net_pnl", "param.contracts", "run_id"]
    page.get_by_label("Freeze Total net pnl", exact=True).check()
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("2 frozen")
    page.get_by_role("button", name="Move Total net pnl earlier", exact=True).click()
    playwright.expect(page.locator("#optimization-results thead th").first).to_have_attribute("data-column", "total_net_pnl")
    assert frozen_keys(page) == ["total_net_pnl", "trial"]
    assert fits(page)
    playwright.expect(page.get_by_role("button", name="Move Contracts earlier", exact=True)).to_be_disabled()
    page.get_by_role("button", name="Move Backtest report earlier", exact=True).click()
    playwright.expect(page.locator("#optimization-results thead th:not([hidden])").nth(2)).to_have_attribute("data-column", "run_id")
    expected = ["total_net_pnl", "trial", "run_id", "param.contracts"]
    assert visible_keys(page) == expected
    page.screenshot(path=str(tmp_path / "selected-and-reordered.png"), full_page=True)
    page.locator("#optimization-freeze summary").click()
    page.locator('#optimization-results th[data-column="total_net_pnl"] button').click()
    page.locator('#optimization-results th[data-column="total_net_pnl"] button').click()
    playwright.expect(page.locator('#optimization-results tbody tr').first.locator('[data-column="total_net_pnl"]')).to_have_text("39.00")
    page.reload()
    playwright.expect(page.locator("#optimization-results thead th:not([hidden])")).to_have_count(4)
    assert visible_keys(page) == expected
    assert frozen_keys(page) == ["total_net_pnl", "trial"]
    assert page.request.get(endpoint).json() == before
    assert not mutations
    (tmp_path / "verification.json").write_text(json.dumps(dict(
        synthetic=True, job_id=job_id, visible_order=expected, frozen=frozen_keys(page),
        hidden_columns_not_displayed=True, keyboard_and_focus=True,
        separate_group_ordering=True, reload_persists=True, expected_net=[13, 26, 39],
        original_results_unchanged=True, mutating_requests=mutations), indent=2))


def test_hiding_frozen_and_sorted_columns_empty_view_show_all_and_reset(page, portal, tmp_path):
    prepare(page, portal)
    run(page)
    page.locator("#optimization-freeze summary").click()
    initial = visible_keys(page)
    page.get_by_label("Freeze Contracts", exact=True).check()
    playwright.expect(page.get_by_label("Freeze Contracts", exact=True)).to_be_checked()
    page.get_by_label("Show Contracts", exact=True).uncheck()
    playwright.expect(page.get_by_label("Freeze Contracts", exact=True)).not_to_be_checked()
    playwright.expect(page.get_by_label("Freeze Contracts", exact=True)).to_be_disabled()
    playwright.expect(page.locator('#optimization-results th[data-column="param.contracts"]')).to_be_hidden()
    page.get_by_label("Show Contracts", exact=True).check()
    playwright.expect(page.get_by_label("Freeze Contracts", exact=True)).not_to_be_checked()
    show_only(page, ["trial", "total_net_pnl"])
    playwright.expect(page.locator("#optimization-results thead th:not([hidden])")).to_have_count(2)
    page.locator("#optimization-freeze summary").click()
    page.locator('#optimization-results th[data-column="total_net_pnl"] button').click()
    page.locator('#optimization-results th[data-column="total_net_pnl"] button').click()
    playwright.expect(page.locator("#optimization-sort-note")).to_have_text("Sorted by Total net pnl · descending.")
    page.locator("#optimization-freeze summary").click()
    page.get_by_label("Show Total net pnl", exact=True).uncheck()
    playwright.expect(page.locator('#optimization-results th[data-column="total_net_pnl"]')).to_be_hidden()
    playwright.expect(page.locator("#optimization-sort-note")).to_have_text("Sorted by Total net pnl · descending.")
    page.get_by_label("Show Trial", exact=True).uncheck()
    playwright.expect(page.locator("#optimization-visible-empty")).to_be_visible()
    assert visible_keys(page) == [] and frozen_keys(page) == []
    page.reload()
    playwright.expect(page.locator("#optimization-visible-empty")).to_be_visible()
    page.locator("#optimization-freeze summary").click()
    page.locator("#optimization-freeze-search").fill("contracts")
    page.get_by_role("button", name="Show all", exact=True).click()
    playwright.expect(page.locator("#optimization-results thead th:not([hidden])")).to_have_count(len(initial))
    playwright.expect(page.locator("#optimization-visible-empty")).to_be_hidden()
    page.get_by_role("button", name="Reset layout", exact=True).click()
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("1 frozen")
    assert visible_keys(page) == initial
    assert frozen_keys(page) == ["trial"]
    page.get_by_role("button", name="Hide all", exact=True).click()
    playwright.expect(page.locator("#optimization-visible-empty")).to_be_visible()
    page.get_by_role("button", name="Reset layout", exact=True).click()
    playwright.expect(page.locator("#optimization-visible-empty")).to_be_hidden()
    page.locator("#optimization-freeze-search").fill("")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(tmp_path / "layout-mobile.png"), full_page=True)
    with page.expect_download() as downloaded:
        page.locator("#optimization-download").click()
    downloaded.value.save_as(tmp_path / "full-results.csv")
    exported = (tmp_path / "full-results.csv").read_text()
    assert all(value in exported for value in ("total_net_pnl", "13.00", "26.00", "39.00"))


def test_migrates_previous_freeze_preferences_without_hiding_results(page, portal):
    page.add_init_script("localStorage.setItem('alphaquest.optimization.frozen-columns.v1:consecutive_green_hold', JSON.stringify(['total_net_pnl']));")
    prepare(page, portal)
    run(page)
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("1 frozen")
    assert frozen_keys(page) == ["total_net_pnl"]
    assert len(visible_keys(page)) > 10
    page.locator("#optimization-freeze summary").click()
    page.get_by_label("Show Contracts", exact=True).uncheck()
    page.reload()
    playwright.expect(page.locator('#optimization-results th[data-column="param.contracts"]')).to_be_hidden()
    assert frozen_keys(page) == ["total_net_pnl"]
    assert page.evaluate("JSON.parse(localStorage.getItem('alphaquest.optimization.column-layout.v2:consecutive_green_hold')).visible.includes('param.contracts')") is False

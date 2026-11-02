"""User-controlled freezing on real durable optimization results."""

import json

import pytest

from test_backtests_browser import browser, page, portal, playwright
from test_optimization_browser import prepare, run
from test_optimization import optimization_body


def frozen_keys(page):
    return page.locator("#optimization-results thead .optimization-frozen-column").evaluate_all(
        "cells => cells.map(cell => cell.dataset.column)")


def frozen_aligned(page):
    return page.evaluate("""() => {
        const table = document.querySelector('#optimization-results');
        const headers = [...table.querySelectorAll('thead .optimization-frozen-column')];
        const cells = new Map([...table.tBodies[0].rows[0].cells].map(cell => [cell.dataset.column, cell]));
        return headers.every((header, index) => {
            const rect = header.getBoundingClientRect(), body = cells.get(header.dataset.column).getBoundingClientRect();
            const previous = index ? headers[index - 1].getBoundingClientRect() : null;
            return Math.abs(rect.x - body.x) < 1 && Math.abs(rect.width - body.width) < 1
                && (!previous || Math.abs(rect.x - previous.right) < 1);
        });
    }""")


def test_choose_parameter_and_metric_columns_sort_export_and_reopen(page, portal, tmp_path):
    prepare(page, portal)
    run(page)
    url = page.url
    job_id = url.rsplit("/", 1)[1]
    endpoint = f"{portal['url']}/api/backtests/batches/{job_id}/results"
    before = page.request.get(endpoint).json()
    posts = []
    page.on("request", lambda request: posts.append(request.url) if request.method in ("POST", "DELETE", "PATCH", "PUT") else None)
    playwright.expect(page.locator("#optimization-freeze")).not_to_have_attribute("open", "")
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("1 frozen")
    assert frozen_keys(page) == ["trial"]
    # Highlighting identifies varied parameters independently of freezing.
    assert page.locator('#optimization-results th[data-column="param.contracts"]').get_attribute("class") == "optimization-varying-parameter"
    page.locator("#optimization-freeze summary").click()
    net = page.get_by_label("Freeze Total net pnl", exact=True)
    net.focus()
    page.keyboard.press("Space")
    playwright.expect(net).to_be_checked()
    playwright.expect(net).to_be_focused()
    page.get_by_label("Freeze Contracts", exact=True).check()
    page.wait_for_function("() => document.querySelectorAll('#optimization-results thead .optimization-frozen-column').length === 3")
    assert frozen_keys(page) == ["trial", "total_net_pnl", "param.contracts"]
    assert frozen_aligned(page)
    page.locator("#optimization-freeze-search").fill("contracts")
    playwright.expect(page.locator(".optimization-column-choice:visible")).to_have_count(1)
    page.locator("#optimization-freeze-search").fill("no such column")
    playwright.expect(page.locator(".optimization-column-empty")).to_be_visible()
    page.locator("#optimization-freeze-search").fill("")
    page.screenshot(path=str(tmp_path / "selected-columns.png"), full_page=True)
    page.locator("#optimization-freeze summary").click()
    page.locator('#optimization-results th[data-column="total_net_pnl"] button').click()
    playwright.expect(page.locator('#optimization-results th[data-column="total_net_pnl"]')).to_have_attribute("aria-sort", "ascending")
    page.locator('#optimization-results th[data-column="total_net_pnl"] button').click()
    playwright.expect(page.locator('#optimization-results tbody tr').first.locator('[data-column="total_net_pnl"]')).to_have_text("39.00")
    with page.expect_download() as downloaded:
        page.locator("#optimization-download").click()
    downloaded.value.save_as(tmp_path / "results.csv")
    assert "39.00" in (tmp_path / "results.csv").read_text()
    page.reload()
    playwright.expect(page.locator("#optimization-results tbody tr")).to_have_count(3)
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("3 frozen")
    assert frozen_keys(page) == ["trial", "total_net_pnl", "param.contracts"]
    assert page.request.get(endpoint).json() == before
    assert not posts
    (tmp_path / "verification.json").write_text(json.dumps(dict(
        synthetic=True, job_id=job_id, frozen=frozen_keys(page), expected_net=[13, 26, 39],
        frozen_cells_aligned=frozen_aligned(page), sorting_download_reload=True, original_results_unchanged=True,
        no_calculations_or_mutations=True), indent=2))


def test_unlimited_freezing_pan_resize_unfreeze_and_reset(page, portal, tmp_path):
    prepare(page, portal)
    run(page)
    page.locator("#optimization-freeze summary").click()
    shown = page.locator('#optimization-results thead th:not([hidden])').evaluate_all('cells => cells.map(cell => cell.dataset.column)')
    # A frozen group beyond the old 40% budget still pins while other metrics
    # scroll underneath it. Larger-than-viewport groups are tested below.
    pinned = ['trial','param.contracts','total_net_pnl','total_gross_pnl','total_commissions']
    for key in pinned:
        page.locator(f'.optimization-column-choice[data-column="{key}"] input[data-control=freeze]').check()
    playwright.expect(page.locator('#optimization-results thead .optimization-frozen-column')).to_have_count(len(pinned))
    width = page.locator('#optimization-results thead .optimization-frozen-column').evaluate_all('cells => cells.reduce((sum, cell) => sum + cell.getBoundingClientRect().width, 0)')
    region_width = page.locator('#optimization-results-scroll').evaluate('el => el.clientWidth')
    assert region_width * .4 < width < region_width
    before = page.locator('#optimization-results thead .optimization-frozen-column').evaluate_all('cells => cells.map(cell => cell.getBoundingClientRect().x)')
    page.locator('#optimization-results-scroll').evaluate('el => el.scrollLeft = 400')
    page.wait_for_timeout(50)
    after = page.locator('#optimization-results thead .optimization-frozen-column').evaluate_all('cells => cells.map(cell => cell.getBoundingClientRect().x)')
    assert all(abs(a-b) < 1 for a,b in zip(before,after))
    assert frozen_aligned(page)
    page.screenshot(path=str(tmp_path / 'frozen-beyond-former-width-budget.png'),full_page=True)
    page.locator('#optimization-results-scroll').evaluate('el => el.scrollLeft = 0')
    for key in shown:
        page.locator(f'.optimization-column-choice[data-column="{key}"] input[data-control=freeze]').check()
    playwright.expect(page.locator('#optimization-results thead .optimization-frozen-column')).to_have_count(len(shown))
    desired = frozen_keys(page)
    assert set(desired) == set(shown)
    assert page.evaluate("""() => [...document.querySelectorAll('#optimization-results thead .optimization-frozen-column')]
        .reduce((sum, cell) => sum + cell.getBoundingClientRect().width, 0) > document.querySelector('#optimization-results-scroll').clientWidth""")
    playwright.expect(page.locator('#optimization-freeze [role=status]')).to_contain_text('pan the frozen group')
    assert page.locator('.optimization-column-choice:has(input[data-control=show]:checked) input[data-control=freeze]:disabled').count() == 0
    assert frozen_aligned(page)
    region = page.locator('#optimization-results-scroll')
    region.evaluate('el => {el.scrollLeft = el.scrollWidth - el.clientWidth;}')
    last = page.locator(f'#optimization-results thead th[data-column="{desired[-1]}"]')
    page.wait_for_function("""key => {
        const region = document.querySelector('#optimization-results-scroll').getBoundingClientRect();
        const last = [...document.querySelectorAll('#optimization-results thead th')].find(cell => cell.dataset.column === key).getBoundingClientRect();
        return last.left >= region.left - 1 && last.right <= region.right + 1;
    }""", arg=desired[-1])
    assert frozen_aligned(page)
    page.screenshot(path=str(tmp_path / 'all-visible-columns-frozen.png'), full_page=True)
    page.set_viewport_size(dict(width=390,height=844))
    playwright.expect(page.locator('#optimization-results thead .optimization-frozen-column')).to_have_count(len(desired))
    assert frozen_keys(page) == desired
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path / 'all-frozen-mobile.png'),full_page=True)
    page.reload()
    playwright.expect(page.locator('#optimization-results thead .optimization-frozen-column')).to_have_count(len(desired))
    assert frozen_keys(page) == desired
    page.set_viewport_size(dict(width=1440,height=1100))
    page.locator('#optimization-freeze summary').click()
    page.get_by_role('button',name='Unfreeze all',exact=True).click()
    playwright.expect(page.locator('#optimization-freeze .optimization-freeze-count')).to_have_text('0 frozen')
    page.reload()
    playwright.expect(page.locator('#optimization-freeze .optimization-freeze-count')).to_have_text('0 frozen')
    page.locator('#optimization-freeze summary').click()
    page.get_by_role('button',name='Reset layout',exact=True).click()
    playwright.expect(page.get_by_label('Freeze Trial',exact=True)).to_be_checked()
    assert frozen_keys(page) == ['trial']
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,
        frozen_columns=desired, no_column_or_width_cap=True, wide_group_reachable=True,
        resize_preserves_all_selections=True, reload_persists=True),indent=2))


def test_preferences_are_separate_for_each_strategy(page, portal):
    prepare(page, portal)
    run(page)
    first_url = page.url
    page.locator("#optimization-freeze summary").click()
    page.get_by_role("button", name="Unfreeze all", exact=True).click()
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("0 frozen")
    page.get_by_label("Show Contracts", exact=True).uncheck()
    definition = next(item for item in page.request.get(portal["url"] + "/api/strategies").json() if item["id"] == "vwap_pullback_risk_sizing")
    request = optimization_body(portal["saved"]["arithmetic_5m"]["id"])
    request["strategy_id"] = definition["id"]
    request["parameter_ranges"] = {parameter["name"]: dict(start=parameter["default"], end=parameter["default"], step="0" if parameter["type"] == "Decimal" else 0) for parameter in definition["parameters"]}
    request["parameter_ranges"]["trade_shorts"]["end"] = True
    request["parameter_ranges"]["trade_shorts"]["step"] = 1
    response = page.request.post(portal["url"] + "/api/backtests", data=request)
    assert response.status == 202, response.text()
    second_url = portal["url"] + "/#backtests/batches/" + response.json()["id"]
    page.goto(second_url)
    playwright.expect(page.locator("#optimization-status")).to_contain_text("COMPLETE", timeout=20000)
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("1 frozen")
    assert frozen_keys(page) == ["trial"]
    # The same controls include all 32 backend-defined VWAP parameters.
    playwright.expect(page.locator('.optimization-column-choice[data-column^="param."]')).to_have_count(32)
    if page.locator("#optimization-freeze").get_attribute("open") is None:
        page.locator("#optimization-freeze summary").click()
    page.get_by_label("Show Min rr", exact=True).check()
    page.get_by_label("Freeze Min rr", exact=True).check()
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("2 frozen")
    page.goto(first_url)
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("0 frozen")
    playwright.expect(page.get_by_label("Show Contracts", exact=True)).not_to_be_checked()
    page.goto(second_url)
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("2 frozen")
    assert frozen_keys(page) == ["trial", "param.min_rr"]


@pytest.mark.parametrize("storage", ["malformed", "blocked"])
def test_browser_storage_errors_do_not_break_freezing(page, portal, storage):
    if storage == "malformed":
        page.add_init_script("localStorage.setItem('alphaquest.optimization.frozen-columns.v1:consecutive_green_hold', '{bad json')")
    else:
        page.add_init_script("Object.defineProperty(Storage.prototype, 'getItem', {value() { throw new Error('storage blocked'); }}); Object.defineProperty(Storage.prototype, 'setItem', {value() { throw new Error('storage blocked'); }});")
    prepare(page, portal)
    run(page)
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("1 frozen")
    page.locator("#optimization-freeze summary").click()
    page.get_by_role("button", name="Unfreeze all", exact=True).click()
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("0 frozen")
    saved_url = page.url
    page.goto(portal["url"] + "/#backtests/batches")
    playwright.expect(page.locator("#optimization-freeze")).to_be_hidden()
    page.goto(saved_url)
    playwright.expect(page.locator("#optimization-freeze .optimization-freeze-count")).to_have_text("0 frozen")

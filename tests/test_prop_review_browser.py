"""User-visible review checks, saved reloads, downloads, and failure recovery."""

import json
from dataclasses import replace

from alphaquest.prop import review

from test_backtests_browser import browser, page, portal, playwright


def generate(page, portal, quantity="2", platform="rithmic"):
    page.goto(portal["url"] + "/#prop-review")
    playwright.expect(page.locator("#prop-generate")).to_be_enabled()
    playwright.expect(page.locator("#prop-review-status")).to_contain_text("No review saved")
    page.locator("#prop-platform").select_option(platform)
    page.locator("#prop-quantity").select_option(quantity)
    page.locator("#prop-generate").click()
    playwright.expect(page.locator("#prop-review-status")).to_contain_text("Review passed")


def test_web_deliverables_expected_values_download_and_reload(page, portal):
    generate(page, portal)
    playwright.expect(page.locator("#prop-review-result")).to_contain_text("44/44 checks passed")
    for number in (1, 2, 3):
        section = page.locator(f"#prop-subtask-{number}")
        playwright.expect(section).to_contain_text("Deliverable:")
        playwright.expect(section).to_contain_text("Validation: expected versus actual")
    playwright.expect(page.locator("#prop-subtask-3")).to_contain_text("Net P&L 26 USD")
    page.get_by_text("Read the saved specification", exact=True).click()
    playwright.expect(page.locator("#prop-subtask-1 pre")).to_contain_text("Single-strategy prop simulation specification")
    with page.expect_download() as download:
        page.get_by_role("link", name="review.json", exact=True).click()
    first = json.loads(download.value.path().read_text())
    assert first["all_passed"] is True and first["quantity"] == 2
    page.reload()
    playwright.expect(page.locator("#prop-review-result")).to_contain_text(first["id"])
    page.locator("#prop-platform").select_option("tradovate")
    page.locator("#prop-quantity").select_option("1")
    playwright.expect(page.locator("#prop-review-status")).to_contain_text("Options changed")
    page.locator("#prop-generate").click()
    playwright.expect(page.locator("#prop-subtask-3")).to_contain_text("Net P&L 13 USD")
    playwright.expect(page.locator("#prop-subtask-2")).to_contain_text("No lock")
    playwright.expect(page.locator("#prop-review-result")).to_contain_text("44/44 checks passed")
    page.get_by_role("link", name="Datasets", exact=True).first.click()
    playwright.expect(page.locator("#datasets-screen")).to_be_visible()
    playwright.expect(page.locator("#prop-review-screen")).to_be_hidden()
    page.get_by_role("link", name="Backtests", exact=True).first.click()
    playwright.expect(page.locator("#backtests-screen")).to_be_visible()


def test_review_mobile_layout_has_no_page_overflow(page, portal):
    page.set_viewport_size({"width": 390, "height": 844})
    generate(page, portal, "1", "wealthcharts")
    playwright.expect(page.locator("#prop-subtask-3")).to_contain_text("Net P&L 13 USD")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    playwright.expect(page.get_by_role("navigation", name="Mobile navigation").get_by_text("Prop review")).to_be_visible()


def test_review_request_failure_is_visible_and_retry_works(page, portal):
    page.goto(portal["url"] + "/#prop-review")
    playwright.expect(page.locator("#prop-review-status")).to_contain_text("No review saved")
    page.route("**/api/prop-review", lambda route: route.fulfill(status=503, json={"detail": "Review storage is unavailable."}))
    page.locator("#prop-generate").click()
    playwright.expect(page.locator("#prop-review-status")).to_contain_text("Review storage is unavailable")
    playwright.expect(page.locator("#prop-review-result")).to_be_hidden()
    playwright.expect(page.locator("#prop-generate")).to_be_enabled()
    page.unroute("**/api/prop-review")
    page.locator("#prop-generate").click()
    playwright.expect(page.locator("#prop-review-result")).to_contain_text("44/44 checks passed")


def test_real_rule_mismatch_is_visible_as_failed_review(page, portal, monkeypatch):
    original = review.get_profile

    def wrong_daily_limit(*args):
        profile = original(*args)
        return replace(profile, evaluation=replace(profile.evaluation, limits=replace(
            profile.evaluation.limits, daily_loss_limit=review.D("1100"))))

    monkeypatch.setattr(review, "get_profile", wrong_daily_limit)
    page.goto(portal["url"] + "/#prop-review")
    playwright.expect(page.locator("#prop-review-status")).to_contain_text("No review saved")
    page.locator("#prop-generate").click()
    playwright.expect(page.locator("#prop-review-status")).to_contain_text("Review has failed checks")
    playwright.expect(page.locator(".prop-fail")).to_have_text("43/44 checks passed")
    playwright.expect(page.locator("#prop-subtask-2")).to_contain_text("FAIL")

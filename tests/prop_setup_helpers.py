"""Use the product's explicit expert view for existing detailed form regressions."""
from playwright.sync_api import expect


def open_prop_task(page,goal='legacy',close_outer=False):
    expect(page.locator('#setup-goal-picker')).to_be_visible(timeout=30000)
    active=page.locator('#setup-goal-'+goal)
    # Preserve a manually selected legacy method when its expert form is already open.
    same=active.get_attribute('aria-pressed')=='true' or (goal in ('legacy','budget') and page.locator('#prop-form').is_visible())
    if not same:
        if not page.locator('#setup-goal-picker').evaluate('(node)=>node.open'):
            page.locator('#setup-goal-picker > summary').click()
        if goal in ('legacy','budget','pair') and not page.locator('#setup-other-tools').evaluate('(node)=>node.open'):
            page.locator('#setup-other-tools > summary').click()
        active.click()
    form={'research':'#robust-form','compare':'#campaign-form','inspect':'#native-form','legacy':'#prop-form','budget':'#prop-form','pair':'#pair-form'}[goal]
    expect(page.locator(form)).to_be_attached(timeout=30000)
    page.locator('#setup-show-all').check()
    if close_outer:
        selector={'research':'#robust-configure','compare':'#campaign-configure','inspect':'#native-configure','pair':'#pair-configure'}.get(goal)
        if selector and page.locator(selector).evaluate('(node)=>node.open'):
            page.locator(selector+' > summary').click()

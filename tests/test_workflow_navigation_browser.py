"""Main workflow navigation, example selection, and presentation-only boundaries."""
import json

from test_backtests_browser import browser, page, portal, playwright


def test_main_navigation_and_campaign_details(page, portal, tmp_path):
    mutations, requests = [], []
    page.on('request', lambda r: mutations.append(r.url) if r.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else requests.append(r.url))
    page.goto(portal['url'])
    nav = page.get_by_role('navigation', name='Main navigation', exact=True)
    playwright.expect(nav.locator('a')).to_have_count(4)
    assert nav.locator('a').evaluate_all('(items) => items.map(item => item.getAttribute("aria-label"))') == ['Dataset', 'Research', 'Campaigns', 'Prop Sim']
    playwright.expect(page.locator('#dataset-count')).to_have_text('2')
    playwright.expect(page.locator('#datasets-screen')).to_be_visible()
    before = page.request.get(portal['url']+'/api/datasets').json()
    nav.get_by_role('link', name='Research', exact=True).click()
    playwright.expect(page.locator('#research-screen')).to_contain_text('No research theses yet')
    playwright.expect(page.locator('#research-screen button')).to_have_count(0)
    assert not any('/api/research-workspace' in url for url in requests)
    page.screenshot(path=str(tmp_path/'research.png'), full_page=True)
    nav.get_by_role('link', name='Campaigns', exact=True).click()
    playwright.expect(page.locator('#workflow-campaign-detail')).to_contain_text('A breakout of the day’s opening range')
    page.get_by_role('link', name='Twin continuation twin_continuation', exact=True).click()
    detail = page.locator('#workflow-campaign-detail')
    playwright.expect(detail).to_contain_text('Confirmed swing breakouts and morning momentum')
    playwright.expect(detail.locator('.workflow-dataset')).to_have_count(2)
    playwright.expect(detail).to_contain_text('Latest phase: IS broad · 1 pass')
    detail.get_by_text('Source code', exact=True).click()
    playwright.expect(detail.locator('code')).to_have_text('alphaquest/strategies/twin_continuation.py')
    page.screenshot(path=str(tmp_path/'campaigns.png'), full_page=True)
    page.reload()
    playwright.expect(detail.locator('h2')).to_have_text('Twin continuation')
    page.go_back()
    playwright.expect(detail.locator('h2')).to_have_text('ORB + VWAP pullback')
    page.goto(portal['url']+'/#campaigns/missing')
    playwright.expect(detail).to_contain_text('Campaign not found')
    page.goto(portal['url']+'/#research')
    playwright.expect(page.locator('#research-screen')).to_be_visible()
    assert mutations == []
    assert page.request.get(portal['url']+'/api/datasets').json() == before
    (tmp_path/'navigation.json').write_text(json.dumps({'destinations':['Dataset','Research','Campaigns','Prop Sim'], 'campaigns':2, 'datasets_unchanged':True, 'mutation_requests':mutations}, indent=2))


def test_prop_preview_selection_empty_boundary_and_mobile(page, portal, tmp_path):
    mutations = []
    page.on('request', lambda r: mutations.append(r.url) if r.method != 'GET' else None)
    page.goto(portal['url']+'/#prop-sim')
    screen = page.locator('#prop-sim-screen')
    playwright.expect(screen).to_contain_text('Placeholder values only')
    playwright.expect(page.locator('#prop-preview-account')).to_have_value('APEX › 50K EOD')
    playwright.expect(page.locator('#prop-preview-selected .workflow-input-card')).to_have_count(4)
    page.locator('#prop-preview-evaluation input[value="twin-1"]').check()
    playwright.expect(page.locator('#prop-preview-profile')).to_contain_text('$300 risk per trade')
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path=str(tmp_path/'prop-sim.png'), full_page=True)
    page.locator('#prop-preview-add').click()
    for item in page.locator('#prop-preview-options input').all():
        item.uncheck()
    playwright.expect(page.locator('#prop-preview-evaluation')).to_contain_text('No example inputs selected')
    playwright.expect(page.locator('#prop-preview-profile')).to_have_text('Select an example evaluation profile above.')
    playwright.expect(page.locator('#prop-preview-evaluation input:checked')).to_have_count(0)
    page.locator('#prop-preview-options input[value="orb-2"]').check()
    playwright.expect(page.locator('#prop-preview-selected .workflow-input-card')).to_have_count(1)
    playwright.expect(page.locator('#prop-preview-funded .workflow-sizing-row')).to_have_count(1)
    assert page.locator('.workflow-profits tbody td:not(:first-child)').all_text_contents() == ['—'] * 9
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(tmp_path/'prop-sim-mobile.png'), full_page=True)
    nav = page.get_by_role('navigation', name='Mobile navigation', exact=True)
    playwright.expect(nav.locator('a')).to_have_count(4)
    for name, selector in [('Research','#research-screen'),('Campaigns','#campaigns-screen'),('Prop Sim','#prop-sim-screen'),('Dataset','#datasets-screen')]:
        nav.get_by_role('link',name=name,exact=True).click()
        playwright.expect(page.locator(selector)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        playwright.expect(nav.locator('[aria-current="page"]')).to_have_text(name)
        if name == 'Campaigns':
            page.screenshot(path=str(tmp_path/'campaigns-mobile.png'), full_page=True)
    assert mutations == []


def test_existing_run_routes_remain_reachable_under_campaigns(page, portal):
    page.goto(portal['url']+'/#campaigns')
    page.get_by_role('link',name='Saved runs',exact=True).click()
    playwright.expect(page.locator('#strategies-screen')).to_be_visible()
    playwright.expect(page.locator('.sidebar [aria-current="page"]')).to_have_attribute('data-screen','campaigns')
    page.get_by_role('link',name='New backtest →',exact=True).click()
    playwright.expect(page.locator('#backtests-screen')).to_be_visible()
    playwright.expect(page.locator('#optimization-ranges tr')).to_have_count(3)

"""Main workflow navigation, example selection, and presentation-only boundaries."""
import json

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, portal, playwright
from test_campaign_mechanics import create_workflow, run_validation, checks
from test_campaign_narrow import narrow_workflow, narrow_start
from alphaquest.worker_limits import DEFAULT_WORKERS


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
    playwright.expect(detail.locator('.workflow-dataset')).to_have_count(0)
    playwright.expect(detail).to_contain_text('No saved datasets for this campaign')
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
    (tmp_path/'navigation.json').write_text(json.dumps({'destinations':['Dataset','Research','Campaigns','Prop Sim'], 'campaigns':3, 'datasets_unchanged':True, 'mutation_requests':mutations}, indent=2))


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


def test_campaign_dataset_opens_latest_selectable_phase(page, portal):
    with ResearchHTTPClient(base_url=portal['url'], timeout=120) as client:
        _, _, workflow = create_workflow(client)
        campaign = portal['url'] + '/#campaigns/consecutive_green_hold'
        page.goto(campaign)
        dataset = page.locator('.workflow-dataset').filter(has_text='SYNTHETIC mechanics')
        link = dataset.get_by_role('link', name='SYNTHETIC mechanics', exact=True)
        playwright.expect(link).to_have_attribute('href', f'#campaigns/workflows/{workflow["id"]}/mechanic_validation')
        link.click()
        playwright.expect(page).to_have_url(portal['url'] + f'/#campaigns/workflows/{workflow["id"]}/mechanic_validation')

        result = run_validation(client, workflow)
        prefix = '/api/campaign-workflows/' + workflow['id']
        reviewed = client.patch(prefix + '/review', json=checks(result)).json()
        confirmed = client.post(prefix + '/confirm', json={'revision': reviewed['review']['revision']})
        assert confirmed.status_code == 200, confirmed.text
        page.goto(campaign)
        playwright.expect(link).to_have_attribute('href', f'#campaigns/workflows/{workflow["id"]}/is_broad')
        link.click()
        playwright.expect(page).to_have_url(portal['url'] + f'/#campaigns/workflows/{workflow["id"]}/is_broad')
        playwright.expect(page.locator('#broad-workers')).to_have_value(str(DEFAULT_WORKERS))
        playwright.expect(page.locator('#broad-workers option:checked')).to_contain_text('default')
        assert client.get(prefix + '/broad').json()['default_workers'] == DEFAULT_WORKERS

        _, narrow, _ = narrow_workflow(client)
        page.goto(campaign)
        narrow_link = page.locator('.workflow-dataset').filter(
            has_text='SYNTHETIC 120-day narrow oracle').get_by_role(
                'link', name='SYNTHETIC 120-day narrow oracle', exact=True)
        expected = f'#campaigns/workflows/{narrow["id"]}/is_narrow?broad_trial=1'
        playwright.expect(narrow_link).to_have_attribute('href', expected)
        narrow_link.click()
        playwright.expect(page).to_have_url(portal['url'] + '/' + expected)
        playwright.expect(page.locator('#narrow-broad-trial')).to_have_value('1')
        playwright.expect(page.locator('#narrow-workers')).to_have_value(str(DEFAULT_WORKERS))
        playwright.expect(page.locator('#narrow-workers option:checked')).to_contain_text('default')
        assert client.get('/api/campaign-workflows/' + narrow['id'] + '/narrow',
                          params={'broad_trial': 1}).json()['default_workers'] == DEFAULT_WORKERS

        narrow_prefix = '/api/campaign-workflows/' + narrow['id']
        jobs = {trial: narrow_start(client, narrow_prefix, trial) for trial in (1, 2)}
        for trial in (1, 2):
            row = next(row for row in client.get(narrow_prefix + '/narrow/results',
                params={'broad_trial': trial}).json()['items'] if row['qualifies'])
            state = client.get(narrow_prefix + '/narrow', params={'broad_trial': trial}).json()['state']
            selected = client.patch(narrow_prefix + '/narrow/selection', json={
                'broad_trial': trial, 'job_id': jobs[trial]['id'],
                'revision': state['revision'], 'trials': [row['trial']]})
            assert selected.status_code == 200, selected.text
            confirmed = client.post(narrow_prefix + '/narrow/confirm', json={
                'broad_trial': trial, 'job_id': jobs[trial]['id'],
                'revision': selected.json()['revision']})
            assert confirmed.status_code == 200, confirmed.text
            page.goto(campaign)
            page.reload()  # The API changed state while this tab remained on Campaigns.
            remaining = (f'#campaigns/workflows/{narrow["id"]}/is_narrow?broad_trial=2'
                         if trial == 1 else f'#campaigns/workflows/{narrow["id"]}/oos')
            playwright.expect(narrow_link).to_have_attribute('href', remaining)
        narrow_link.click()
        playwright.expect(page).to_have_url(portal['url'] + '/' + remaining)
        playwright.expect(page.locator('#mechanic-content')).to_contain_text('OOS')
        page.goto(portal['url'] + '/#backtests')
        playwright.expect(page.locator('#optimization-workers')).to_have_value(str(DEFAULT_WORKERS))

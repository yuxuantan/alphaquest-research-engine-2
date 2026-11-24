"""Prop Desk admits real campaign-qualified configurations only."""

from hashlib import sha256
import json

import httpx

from test_backtests_browser import browser, page, playwright, portal
from test_prop_sim import qualified_source


def test_prop_desk_qualification_controls_picker_and_launch(page, portal, tmp_path):
    root = portal['url']
    desk = page.locator('#prop-desk-screen')
    picker = desk.get_by_role('combobox', name='Saved strategy')
    page.goto(root + '/#prop-desk')
    playwright.expect(desk.get_by_text('No qualified strategies.', exact=False)).to_be_visible()
    playwright.expect(desk.get_by_role('button', name='Run simulation')).to_be_disabled()
    evidence = tmp_path / 'prop-desk-qualification-evidence'
    evidence.mkdir()
    page.screenshot(path=evidence/'empty.png', full_page=True)

    with httpx.Client(base_url=root, timeout=90) as client:
        workflow, candidate = qualified_source(client)
        qualified = {item['source_backtest_id']: item['oos_report_id']
                     for item in client.get('/api/prop-sim/candidates').json()['items']}
        selected, oos = candidate['source_backtest_id'], candidate['oos_report_id']
        with portal['app'].state.runs.connect() as db:
            excluded = next(id for id, in db.execute(
                "SELECT id FROM runs WHERE json_extract(manifest,'$.run_metadata.research.workflow_id')=? "
                "AND json_extract(manifest,'$.run_metadata.research.workflow_phase')='is_narrow'", (workflow['id'],))
                if id not in qualified)
        catalogue = client.get('/api/prop-desk/sources')
        assert catalogue.is_success, catalogue.text
        assert {item['id']: item['oos']['id'] for item in catalogue.json()['items']} == qualified
        assert catalogue.json()['total'] == len(qualified)
        assert excluded not in qualified and oos not in qualified
        (evidence/'qualified-catalogue.json').write_bytes(catalogue.content)
        paginator = [client.get('/api/prop-desk/sources', params=dict(offset=i, limit=1)).json()['items'][0]['id']
                     for i in range(len(qualified))]
        assert set(paginator) == set(qualified)

        rejected = {}
        fixed = dict(source_backtest_id=excluded, phase='evaluation', profile_id='apex-50k-eod', micros=1)
        basket = dict(members=[dict(source_backtest_id=excluded, weight=1)], phase='evaluation',
                      profile_id='apex-50k-eod', minimum_micros=1, maximum_micros=1)
        for suffix, payload in (('', fixed), ('/check', fixed), ('/basket', basket), ('/basket/check', basket),
                                ('/optimizer', dict(basket, minimum_members=1, maximum_members=1)),
                                ('/optimizer/subsets', basket)):
            response = client.post('/api/prop-desk' + suffix, json=payload)
            assert response.status_code == 422 and 'has not passed current campaign qualification' in response.text
            rejected[suffix] = response.json()
        mismatch = dict(basket, members=[dict(source_backtest_id=selected, oos_backtest_id=excluded, weight=1)])
        response = client.post('/api/prop-desk/basket', json=mismatch)
        assert response.status_code == 422 and 'current campaign qualification' in response.text
        rejected['incorrect_oos_link'] = response.json()
        assert client.get('/api/prop-desk').json()['items'] == []

        page.reload()
        playwright.expect(picker).to_be_enabled(timeout=60000)
        playwright.expect(picker.locator(f'option[value="{excluded}"]')).to_have_count(0)
        picker.select_option(selected)
        desk.get_by_role('button', name='Add to portfolio').click()
        playwright.expect(desk.get_by_role('link', name='OOS report', exact=False)).to_be_visible()
        page.screenshot(path=evidence/'qualified-desktop.png', full_page=True)
        with page.expect_response('**/api/prop-desk/basket') as launched:
            desk.get_by_role('button', name='Run simulation').click()
        assert launched.value.status == 202, launched.value.text()
        id = launched.value.json()['id']
        assert launched.value.request.post_data_json['members'] == [
            dict(source_backtest_id=selected, oos_backtest_id=oos, weight=1)]
        playwright.expect(desk.get_by_text('Out of sample account paths', exact=False)).to_be_visible(timeout=60000)
        saved = client.get(f'/api/prop-analyses/{id}/downloads/report.json')
        assert saved.is_success, saved.text
        assert saved.json()['configuration']['members'] == launched.value.request.post_data_json['members']
        (evidence/'report.json').write_bytes(saved.content)

        # A later integrity failure removes current eligibility and leaves the
        # already-sealed Desk report readable under its saved identity.
        mc = candidate['selection']['monte_carlo_id'].replace('-', '')
        artifact = portal['app'].state.prop_analyses.root / mc / 'report.json'
        original = artifact.read_bytes()
        try:
            artifact.write_bytes(original + b' ')
            assert client.get('/api/prop-desk/sources').json()['items'] == []
            response = client.post('/api/prop-desk/basket', json=launched.value.request.post_data_json)
            assert response.status_code == 422 and 'has not passed current campaign qualification' in response.text
            rejected['changed_qualification'] = response.json()
        finally:
            artifact.write_bytes(original)
        page.set_viewport_size({'width':390, 'height':844})
        page.reload()
        playwright.expect(desk.get_by_text('Out of sample account paths', exact=False)).to_be_visible(timeout=60000)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert client.get(f'/api/prop-analyses/{id}/downloads/report.json').content == saved.content
        page.screenshot(path=evidence/'reopened-mobile.png', full_page=True)
        (evidence/'rejections.json').write_text(json.dumps(rejected, indent=2))
        (evidence/'journey.json').write_text(json.dumps(dict(
            evidence_type='Synthetic normal-product campaign qualification',
            workflow=workflow['id'], analysis=id, qualified=qualified, excluded=excluded,
            sha256={file.name:sha256(file.read_bytes()).hexdigest() for file in sorted(evidence.iterdir())}), indent=2))

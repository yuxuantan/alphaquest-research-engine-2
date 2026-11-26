"""Recommendation, deferred evidence and consolidation in the product portal."""

import csv
from hashlib import sha256
from io import StringIO
import json
from time import monotonic, sleep

import httpx
import pytest
from prop_desk_fixtures import desk_calculator_sources

from test_backtests_browser import browser, page, playwright, portal
from test_prop_desk_oos_browser import normal_sources
from test_prop_phases import phase_history


API = '/api/prop-desk'


def saved(client, id):
    started = monotonic()
    while monotonic() - started < 90:
        response = client.get(f'{API}/{id}')
        assert response.is_success, response.text
        job = response.json()
        if job['status'] == 'complete':
            return job
        assert job['status'] in ('queued', 'running'), job
        sleep(.05)
    pytest.fail('A Prop Desk job did not finish within 90 seconds.')


def test_recommendation_product_journey(page, portal, tmp_path, monkeypatch, desk_calculator_sources):
    root = portal['url']
    evidence = tmp_path / 'recommendation-evidence'
    evidence.mkdir()
    desk = page.locator('#prop-desk-screen')
    timing = {}
    with httpx.Client(base_url=root, timeout=90) as client:
        raw, members = normal_sources(client)
        flat_raw, alternate = normal_sources(client, empty_oos=True)
        (evidence / 'SYNTHETIC-strategies.csv').write_bytes(raw)
        (evidence / 'SYNTHETIC-flat-oos.csv').write_bytes(flat_raw)

        def no_bar_parse(*args, **kwargs):
            pytest.fail('Warm strategy recommendations must use the session inventory.')

        monkeypatch.setattr('alphaquest.research_folds.read_bars', no_bar_parse)
        for phase in ('evaluation', 'funded'):
            if phase == 'funded':
                page.set_viewport_size({'width':390, 'height':844})
            page.goto(root + '/#prop-desk?view=optimise')
            page.reload()
            for member in members:
                desk.locator(f'[data-source="{member["source_backtest_id"]}"]').get_by_role('button', name='Add').click()
            desk.get_by_label('Overlapping trades').select_option('sequential_mae')
            desk.get_by_label('At least this many strategies per combination').fill('2')
            desk.get_by_label('Minimum total MNQ').fill('3')
            desk.get_by_label('Maximum total MNQ').fill('4')
            if phase == 'funded':
                desk.get_by_role('button', name='Funded', exact=True).click()
            playwright.expect(desk.locator('#prop-desk-workload')).to_have_text('5 feasible allocations · exhaustive search')
            started = monotonic()
            with page.expect_response('**/api/prop-desk/recommendations') as launched:
                desk.get_by_role('button', name='Run Optimise', exact=True).click()
            assert launched.value.status == 202, launched.value.text()
            id = launched.value.json()['id']
            declaration = launched.value.request.post_data_json
            playwright.expect(desk.get_by_role('heading', name='Recommended allocation')).to_be_visible(timeout=45000)
            timing[phase] = {'click_to_rank_seconds':monotonic() - started}
            job = saved(client, id)
            ranking = job['report']['recommendation']
            rows = ranking['groups'][0]['candidates']
            assert [r['targets'] for r in rows] == [[1,2],[1,3],[2,1],[2,2],[3,1]]
            assert ranking['workload']['exhaustive'] and ranking['workload']['tested'] == 5
            assert job['report']['configuration']['overlap_policy'] == 'sequential_mae'
            parent = client.get(f'/api/prop-analyses/{id}/downloads/report.json').content
            (evidence / f'{phase}-ranking.json').write_bytes(parent)
            page.screenshot(path=evidence / f'{phase}-ranking.png', full_page=True)
            desk.get_by_text('Open frozen Simulation', exact=True).click()
            playwright.expect(desk.get_by_role('heading', name='Equity', exact=True)).to_be_visible(timeout=45000)
            timing[phase]['click_to_winning_evidence_seconds'] = monotonic() - started
            child_id = page.url.split('analysis=')[1].split('&')[0]
            child = saved(client, child_id)['report']
            assert child['configuration']['parent_id'] == id
            assert child['configuration']['candidate_id'] == ranking['ranking'][0]['candidate']
            frozen = child['basket']['sizes'][0]
            assert frozen['account_comparison']['oos_days'] == ['2026-01-15']
            prefix = f'/api/prop-analyses/{child_id}/files/'
            chart = client.get(prefix + f'equity_{frozen["micros"]}.json').json()
            with page.expect_download() as download:
                desk.get_by_role('link', name='Admitted trades for this size ↓').click()
            download.value.save_as(evidence / f'{phase}-admitted-trades.csv')
            trades = list(csv.DictReader(StringIO((evidence / f'{phase}-admitted-trades.csv').read_text())))
            targets = frozen['allocation']['micros']
            assert chart['final_equity_change'] == sum(float(r['net_pnl']) for r in trades) == 9 * (399 * targets[0] + 299 * targets[1])
            assert len(trades) == 18 and all(r['overlap'] == 'True' for r in trades)
            report = client.get(f'/api/prop-analyses/{child_id}/downloads/report.json')
            (evidence / f'{phase}-frozen.json').write_bytes(report.content)
            assert sha256(client.get(f'/api/prop-analyses/{id}/downloads/report.json').content).digest() == sha256(parent).digest()
            repeat = client.post(f'{API}/recommendations', json=declaration)
            assert repeat.status_code == 202 and repeat.json()['id'] == id
            started = monotonic()
            desk.get_by_role('link', name='← Saved recommendation').click()
            playwright.expect(desk.get_by_role('heading', name='Recommended allocation')).to_be_visible()
            timing[phase]['reopen_seconds'] = monotonic() - started
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            timing[phase].update(ranking['timing'])
            if phase == 'evaluation':
                desk.get_by_text('Tested allocations', exact=True).click()
                desk.get_by_label('Tested allocation').select_option('1-3-1')
                desk.get_by_role('button', name='Inspect tested allocation').click()
                playwright.expect(desk.get_by_role('heading', name='Equity', exact=True)).to_be_visible(timeout=45000)
                alt = saved(client, page.url.split('analysis=')[1].split('&')[0])['report']
                assert alt['basket']['sizes'][0]['allocation']['micros'] == [3,1]
            else:
                changed = client.post(f'{API}/recommendations', json=dict(declaration, members=alternate))
                assert changed.status_code == 202, changed.text
                changed_parent = saved(client, changed.json()['id'])
                assert changed_parent['report']['recommendation']['ranking_sha256'] == ranking['ranking_sha256']
                inspected = client.post(f'{API}/recommendations/evidence', json=dict(
                    parent_id=changed_parent['id'], candidate_id=ranking['ranking'][0]['candidate']))
                assert inspected.status_code == 202, inspected.text
                changed_child = saved(client, inspected.json()['id'])
                changed_pair = changed_child['report']['basket']['sizes'][0]['account_comparison']
                assert frozen['account_comparison']['oos_metrics']['probability_any_payout'] == 1
                assert changed_pair['oos_metrics']['probability_any_payout'] == 0
                changed_bytes = client.get(f'/api/prop-analyses/{changed_child["id"]}/downloads/report.json').content
                (evidence / 'funded-flat-oos-frozen.json').write_bytes(changed_bytes)
        header = page.locator('#prop-desk-header')
        workspaces = header.get_by_role('navigation', name='Prop Desk workspaces')
        playwright.expect(workspaces.get_by_role('link')).to_have_text(['Strategy & sizing', 'Portfolio & cash flow'])

        # The recommendation is sealed from real synthetic backtests. This
        # fixture exercises the Portfolio setup mapping only, with no replay.
        eligible = [dict(source_backtest_id=m['source_backtest_id'], oos_report_id=m['oos_backtest_id'],
            dataset={'id':'synthetic-common', 'name':'SYNTHETIC handoff setup'},
            strategy_id='consecutive_green_hold', broad_trial=1, narrow_trial=i+1) for i,m in enumerate(members)]
        endpoint = '**/api/prop-sim/portfolio/candidates'
        page.route(endpoint, lambda route: route.fulfill(json={'items':list(reversed(eligible))}))
        desk.get_by_role('link', name='Use in Portfolio setup').click()
        portfolio = page.locator('#portfolio-form')
        playwright.expect(portfolio.locator('.portfolio-source:checked')).to_have_count(2)
        assert portfolio.locator('.portfolio-pick strong + small').first.inner_text().find(members[0]['source_backtest_id'][:8]) >= 0
        playwright.expect(portfolio.get_by_label('Trade sizing')).to_have_value('fixed_contracts')
        playwright.expect(portfolio.locator('#portfolio-funded_minimum')).to_have_value(str(min(targets)))
        playwright.expect(portfolio.locator('#portfolio-funded_maximum')).to_have_value(str(max(targets)))
        playwright.expect(portfolio.locator('#portfolio-evaluation_maximum')).to_have_value('5')
        playwright.expect(workspaces.get_by_role('link', name='Portfolio & cash flow')).to_have_attribute('aria-current', 'page')
        page.screenshot(path=evidence/'portfolio-handoff-mobile.png',full_page=True)

        page.unroute(endpoint)
        incompatible = [eligible[0], dict(eligible[1], oos_report_id='0'*32)]
        page.route(endpoint, lambda route: route.fulfill(json={'items':incompatible}))
        page.reload()
        playwright.expect(portfolio).to_contain_text('The exact IS and OOS sources are unavailable')
        playwright.expect(portfolio.locator('.portfolio-source:checked')).to_have_count(0)
        page.unroute(endpoint)

        header.get_by_role('link', name='Saved runs', exact=True).click()
        playwright.expect(page.locator('#jobs-filter-kind')).to_have_value('prop_analysis')
        page.locator(f'[data-job-id="{id}"]').get_by_role('link', name='View results').click()
        page.locator('#jobs-detail-content').get_by_role('link', name='Open Prop Desk').click()
        playwright.expect(desk.get_by_role('heading', name='Recommended allocation')).to_be_visible()

        workspaces.get_by_role('link', name='Strategy & sizing', exact=True).click()
        desk.get_by_role('link', name='Advanced single-strategy analysis', exact=True).click()
        playwright.expect(page.locator('#prop-sim-screen')).to_be_visible()
        playwright.expect(page.get_by_role('heading', name='Advanced single-strategy analysis')).to_be_visible()
        playwright.expect(workspaces.get_by_role('link', name='Strategy & sizing')).to_have_attribute('aria-current','page')
        playwright.expect(page.locator('.mobile-nav [aria-current="page"]')).to_have_text('Prop Desk')
    (evidence / 'timing.json').write_text(json.dumps(timing, indent=2))


def test_warm_four_strategy_search_timing_and_exact_comparator(portal, tmp_path, monkeypatch, desk_calculator_sources):
    from alphaquest.prop import desk_recommendation

    # Extend the days so all four configurations have an intraday exit.
    lines = phase_history(days=9).decode().splitlines()
    raw = []
    for line in lines:
        raw.append(line)
        if ',18:03,' in line:
            raw.extend(line.replace('18:03,', f'18:0{minute},') for minute in (4, 5))
    root = portal['url']
    bench = {}
    with httpx.Client(base_url=root, timeout=90) as client:
        _, members = normal_sources(client, raw=('\n'.join(raw) + '\n').encode(), max_hold=4)
        config = dict(members=members, minimum_members=1, minimum_micros=4, maximum_micros=6,
                      profile_id='apex-50k-eod', overlap_policy='sequential_mae')

        def timed(terms, endpoint='/recommendations'):
            started = monotonic()
            response = client.post(API + endpoint, json=terms)
            assert response.status_code == 202, response.text
            job = saved(client, response.json()['id'])
            return job, monotonic() - started

        for phase in ('evaluation', 'funded'):
            small = dict(config, phase=phase, members=members[:3])
            timed(small)
            large = dict(config, phase=phase)
            job, seconds = timed(large)
            model = job['report']['recommendation']
            assert model['workload']['feasible'] == 175
            assert all(4 <= sum(row['targets']) <= 6 for group in model['groups'] for row in group['candidates'])
            assert 0 < model['workload']['score_cache_hits'] and model['workload']['tested'] < 175
            _, reopen_seconds = timed(large)
            # The raised limit and the same IS sources produce the exhaustive oracle.
            with monkeypatch.context() as patched:
                patched.setattr(desk_recommendation, 'EXACT_LIMIT', 200)
                exact_terms = dict(large, members=[dict(m, oos_backtest_id=None) for m in members])
                exact, exact_seconds = timed(exact_terms)
            exact_model = exact['report']['recommendation']
            assert exact_model['workload']['tested'] == exact_model['workload']['feasible'] == 175
            assert model['ranking'][0]['score'] == exact_model['ranking'][0]['score'] == 1
            assert model['ranking'][0]['size_score'] == exact_model['ranking'][0]['size_score']
            bench[phase] = dict(click_to_rank_seconds=seconds, repeat_to_report_seconds=reopen_seconds,
                               exhaustive_comparator_seconds=exact_seconds, workload=model['workload'],
                               timings=model['timing'], winner=model['ranking'][0])
            legacy = dict(large, maximum_micros=4, compare_accounts=True)
            compact = dict(large, maximum_micros=4, allocation_search='weighted')
            old, old_seconds = timed(legacy, '/optimizer/subsets')
            quick, quick_seconds = timed(compact)
            bench[phase].update(weighted_full_seconds=old_seconds, weighted_quick_seconds=quick_seconds)
            for group in quick['report']['recommendation']['groups']:
                selected = group['candidates'][0]
                earlier = old['report']['optimizer']['combinations'][group['id'] - 1]['sizes'][0]
                assert selected['targets'] == earlier['allocation']['micros']
                assert selected['tested_total'] == earlier['micros']
                if phase == 'evaluation':
                    assert selected['metrics']['outcome_counts'] == earlier['metrics']['outcome_counts']
                else:
                    assert selected['metrics']['first_year_mean_receipts'] == earlier['metrics']['first_year_mean_receipts']
    (tmp_path / 'four-strategy-timing.json').write_text(json.dumps(bench, indent=2))

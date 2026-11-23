"""Strategy diagnostics through the real saved backtest and Prop Desk journeys."""

import csv
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import json
from uuid import uuid4

import httpx
import pytest
from prop_desk_fixtures import desk_calculator_sources

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_optimization import wait_job
from test_prop_desk_basket import run

IS_NET = [5, -3, 4, -4, 1, -3]
OOS_NET = [8, -2, -1, 2, -5, 2, -2, 1, -1, -1]
SCALE = 100


def diagnostics_members(client):
    lines = ['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    days = [date(2026, 1, 5) + timedelta(days=i) for i in range(22)
            if (date(2026, 1, 5) + timedelta(days=i)).weekday() < 5]
    for day, net in zip(days, IS_NET + OOS_NET, strict=True):
        # Entry 15000. One NQ at $20/pt, $10 round-trip. Exit one earns
        # the requested per-MNQ net. Exit two adds $400 per MNQ.
        close = Decimal(15000) + Decimal(SCALE * net + 1) / 2
        for offset, prices in enumerate(([14999, 15000, 14999, 15000], [close] * 4,
                                          [close + 200] * 4, [close + 200] * 4)):
            lines.append(f'{day:%m/%d/%Y},18:0{offset},' + ','.join(map(str, prices)) + ',100,60,40')
    raw = ('\n'.join(lines)+'\n').encode()
    dataset = client.post('/api/datasets', params=dict(filename='SYNTHETIC-diagnostics.csv',
        name='SYNTHETIC Prop Desk diagnostics', source_timezone='UTC', tick_size='.25', point_value='20', symbol='NQ'),
        content=raw)
    assert dataset.status_code == 201, dataset.text
    saved = client.post('/api/optimizations', json=dict(dataset_id=dataset.json()['id'], strategy_id='consecutive_green_hold',
        method='exhaustive', workers=1, automatic_prop=False,
        parameter_ranges=dict(green_bar_count=dict(start=1, end=1, step=0), hold_minutes=dict(start=1, end=2, step=1),
                              contracts=dict(start=1, end=1, step=0)),
        execution_settings=dict(initial_capital='10000', tick_size='.25', point_value='20',
                                slippage_ticks=0, commission_per_contract_per_side='5'),
        sample_split=dict(mode='dates', is_start=str(days[0]), is_end=str(days[5]),
                          oos_start=str(days[6]), oos_end=str(days[-1]))))
    assert saved.status_code == 202, saved.text
    job = wait_job(client, saved.json()['id'])
    assert job['status'] == 'complete', job
    selected = client.get(f"/api/optimizations/{job['id']}/results").json()['items']
    members = []
    for row in sorted(selected, key=lambda item: item['parameters']['hold_minutes']):
        source = row['run_id']
        progress = str(uuid4())
        oos = client.post(f'/api/backtests/{source}/oos', params={'progress_id':progress}, json={'request_id':str(uuid4())})
        assert oos.status_code == 201, (oos.text, client.get(f'/api/progress/{progress}').json())
        members.append(dict(source_backtest_id=source, oos_backtest_id=oos.json()['id'], weight=1))
    return raw, members


def test_strategy_diagnostics_product(page, portal, tmp_path, monkeypatch, desk_calculator_sources):
    evidence = tmp_path / 'prop-desk-diagnostics-evidence'
    evidence.mkdir()
    root = portal['url']
    with httpx.Client(base_url=root, timeout=90) as client:
        raw, members = diagnostics_members(client)
    (evidence / 'SYNTHETIC-diagnostics.csv').write_bytes(raw)
    first, second = [member['source_backtest_id'] for member in members]

    def unexpected_parse(*args, **kwargs):
        pytest.fail('Warm diagnostic sources must require zero full bar parses.')

    with monkeypatch.context() as warm:
        warm.setattr('alphaquest.research_folds.read_bars', unexpected_parse)
        page.goto(root + '/#backtests/report/' + first)
        playwright.expect(page.locator('#report-summary')).to_be_visible()
        page.locator('.sidebar').get_by_role('link', name='Prop Desk', exact=True).click()
        desk = page.locator('#prop-desk-screen')
        picker = desk.get_by_role('combobox', name='Saved strategy')
        for source in (first, second):
            picker.select_option(source)
            desk.get_by_role('button', name='Add to portfolio').click()
        desk.get_by_label('Minimum total MNQ').fill('2')
        desk.get_by_label('Maximum total MNQ').fill('4')
        with page.expect_response('**/api/prop-desk/basket') as launch:
            desk.get_by_role('button', name='Run simulation').click()
        assert launch.value.status == 202, launch.value.text()
        basket_id = launch.value.json()['id']
        playwright.expect(desk.get_by_role('heading', name='Evaluation basket results')).to_be_visible(timeout=45000)
        launch_requests = {}
        results = {}

        def save(label, source, expected_size, expected_target, expected_net):
            picker = desk.get_by_label('Strategy to diagnose')
            picker.select_option(source)
            with page.expect_response('**/api/prop-desk/diagnostics') as started:
                desk.get_by_role('button', name='Run strategy diagnostics').click()
            assert started.value.status == 202, started.value.text()
            job_id = started.value.json()['id']
            terms = started.value.request.post_data_json
            assert terms['micros'] == expected_size and terms['source_backtest_id'] == source
            launch_requests[label] = dict(request=terms, response=started.value.json())
            chart = desk.get_by_role('img', name='Strategy equity and Monte Carlo percentile bands')
            playwright.expect(chart).to_be_visible(timeout=45000)
            playwright.expect(desk.get_by_text(f'{expected_target} MNQ allocated', exact=False)).to_be_visible()
            playwright.expect(desk.get_by_role('img', name='Trade-close drawdown in US dollars')).to_be_visible()
            base = root + '/api/prop-analyses/' + job_id
            for name in ('report.json', 'strategy_diagnostics.json', 'strategy_trades.csv'):
                response = page.request.get(base + ('/downloads/' if name == 'report.json' else '/files/') + name)
                assert response.ok, response.text()
                (evidence / f'{label}-{name}').write_bytes(response.body())
            with page.expect_download() as archive:
                desk.get_by_role('link', name='All evidence ZIP ↓').click()
            archive.value.save_as(evidence / f'{label}-analysis.zip')
            data = json.loads((evidence / f'{label}-strategy_diagnostics.json').read_text())
            with (evidence / f'{label}-strategy_trades.csv').open() as file:
                ledger = list(csv.DictReader(file))
            assert (data['is_trades'], data['oos_trades'], data['net']) == (6, 10, expected_net)
            bonus = 0 if source == first else 400
            assert [Decimal(row['net_pnl']) for row in ledger] == [
                (expected * SCALE + bonus) * expected_target for expected in IS_NET + OOS_NET]
            assert all(Decimal(row['commission']) == expected_target and Decimal(row['slippage']) == 0 for row in ledger)
            assert sum(Decimal(row['net_pnl']) for row in ledger) == expected_net
            diagnostics = page.request.get(root + '/api/prop-desk/' + job_id).json()['report']
            assert diagnostics['configuration']['allocated_mnq'] == expected_target
            assert diagnostics['configuration']['parent_id'] == terms['parent_id']
            assert diagnostics['configuration']['combination'] == terms['combination']
            results[label] = data
            return job_id

        desktop = save('simulation-2-desktop', first, 2, 1, 100)
        assert results['simulation-2-desktop']['episodes'][-1]['recovered_at'] is None
        assert results['simulation-2-desktop']['maximum_drawdown'] == 700
        assert results['simulation-2-desktop']['episodes'][1]['recovered_at'] == 7
        desk.get_by_role('button', name='Since OOS started').click()
        playwright.expect(desk.get_by_role('button', name='Since OOS started')).to_have_attribute('aria-pressed', 'true')
        desk.get_by_role('button', name='Sum', exact=True).click()
        playwright.expect(desk.get_by_text('$100.00', exact=True)).not_to_have_count(0)
        page.screenshot(path=evidence / 'simulation-2-desktop.png', full_page=True)
        desk.get_by_role('link', name='← Simulation result').click()
        desk.get_by_label('Inspect tested size').select_option('4')
        save('simulation-4-desktop', second, 4, 2, 13000)
        parent_trades = page.request.get(root + f'/api/prop-analyses/{basket_id}/files/admitted_trades_4.csv')
        assert parent_trades.ok
        rows = list(csv.DictReader(StringIO(parent_trades.text())))
        assert {row['source_backtest_id'] for row in rows} == {first, members[0]['oos_backtest_id']}
        assert sum(Decimal(row['net_pnl']) for row in rows) == 200

        page.set_viewport_size({'width':390, 'height':844})
        page.locator('.mobile-nav').get_by_role('link', name='Prop Desk', exact=True).click()
        desk.get_by_role('button', name='Optimise', exact=True).click()
        desk.get_by_label('At least this many strategies per combination').fill('2')
        desk.get_by_label('Minimum total MNQ').fill('2')
        desk.get_by_label('Maximum total MNQ').fill('4')
        with page.expect_response('**/api/prop-desk/optimizer/subsets') as launch:
            desk.get_by_role('button', name='Run simulation').click()
        assert launch.value.status == 202, launch.value.text()
        optimizer_id = launch.value.json()['id']
        playwright.expect(desk.get_by_role('heading', name='Evaluation combination rankings')).to_be_visible(timeout=45000)
        desk.get_by_role('button', name='Inspect combination 1 at').click()
        size = desk.get_by_label('Inspect tested size')
        size.select_option('2')
        size.select_option('4')
        mobile = save('optimise-mobile', first, 4, 2, 200)
        assert results['optimise-mobile']['maximum_drawdown'] == 1400
        assert results['optimise-mobile']['episodes'][1]['recovered_at'] == 7
        page.reload()
        playwright.expect(desk.get_by_role('img', name='Strategy equity and Monte Carlo percentile bands')).to_be_visible()
        playwright.expect(desk.get_by_text('2 MNQ allocated', exact=False)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=evidence / 'optimise-mobile-reopened.png', full_page=True)
        desk.get_by_role('link', name='← Optimise result').click()
        playwright.expect(desk.get_by_label('Inspect tested size')).to_have_value('4')

        with ResearchHTTPClient(base_url=root, timeout=90) as client:
            request = launch_requests['optimise-mobile']['request']
            replay = client.post('/api/prop-desk/diagnostics', json=request)
            assert replay.status_code == 202 and replay.json()['id'] == mobile
            rejected = client.post('/api/prop-desk/diagnostics', json=dict(request, micros=5))
            assert rejected.status_code == 422 and 'tested total MNQ' in rejected.json()['detail']
            (evidence / 'rejected.json').write_text(rejected.text)
            original = client.get('/api/prop-desk/' + optimizer_id).json()['report']['optimizer']
            comparison = run(client, '/api/prop-desk/optimizer/subsets', dict(
                members=[dict(member, oos_backtest_id=None) for member in members],
                minimum_members=2, minimum_micros=2, maximum_micros=4, phase='evaluation', profile_id='apex-50k-eod'))
            assert comparison['report']['optimizer']['ranking_sha256'] == original['ranking_sha256']
            is_only = run(client, '/api/prop-desk/diagnostics', dict(request, parent_id=comparison['id']))
            is_file = client.get(f"/api/prop-analyses/{is_only['id']}/files/strategy_diagnostics.json").json()
            assert is_file['matrix'] == [] and is_file['oos_trades'] == 0
            assert is_file['cone']['horizon_trades'] == 6 and is_file['observed_oos_net'] is None
            (evidence / 'is-only.json').write_text(json.dumps(is_file, indent=2))
            (evidence / 'saved-rankings.json').write_text(json.dumps(dict(
                with_oos=original['ranking_sha256'], without_oos=comparison['report']['optimizer']['ranking_sha256'],
                ranking=original['ranking']), indent=2))
            fixed = run(client, '/api/prop-desk', dict(source_backtest_id=first, phase='evaluation',
                profile_id='apex-50k-eod', micros=2))
            check = run(client, '/api/prop-desk/diagnostics', dict(request, parent_id=fixed['id'], combination=None, micros=2))
            assert check['report']['calculations']['is_trades'] == 6

            # The selected saved input remains protected even for canonical reuse.
            artifact = portal['app'].state.runs.root / first / 'trades.csv'
            raw_trades = artifact.read_bytes()
            try:
                artifact.write_bytes(raw_trades + b'\n')
                changed = client.post('/api/prop-desk/diagnostics', json=request)
                assert changed.status_code == 422 and 'changed during phase simulation' in changed.json()['detail']
            finally:
                artifact.write_bytes(raw_trades)
            detail_artifact = portal['app'].state.prop_analyses.root / mobile / 'strategy_diagnostics.json'
            original_bytes = detail_artifact.read_bytes()
            try:
                detail_artifact.write_bytes(original_bytes + b'\n')
                changed = client.get('/api/prop-desk/' + mobile)
                assert changed.status_code == 409 and 'integrity' in changed.json()['detail']
            finally:
                detail_artifact.write_bytes(original_bytes)
        page.goto(root + '/#prop-desk?analysis=' + desktop)
        playwright.expect(desk.get_by_role('img', name='Strategy equity and Monte Carlo percentile bands')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.set_viewport_size({'width':1440,'height':1100})
        page.goto(root + '/#prop-desk?analysis=' + mobile)
        playwright.expect(desk.get_by_role('link', name='← Optimise result')).to_be_visible()
        playwright.expect(desk.get_by_role('img', name='Strategy equity and Monte Carlo percentile bands')).to_be_visible()
    (evidence / 'journey.json').write_text(json.dumps(dict(members=members, launches=launch_requests,
        arithmetic=dict(is_net=[value * SCALE for value in IS_NET], oos_net=[value * SCALE for value in OOS_NET],
                        second_strategy_per_trade_bonus=400, commission_per_trade_per_mnq=1,
                        net_at_tested_inspections=[100, 13000, 200],
                        first_strategy_recovered=[3, 7], first_strategy_open_through=16,
                        four_two_trade_paths=[10, 2, 2, -6], fixed_cone_end_bands=[-4.8, 0, 2, 4, 8.8]),
        sha256={file.name:sha256(file.read_bytes()).hexdigest() for file in sorted(evidence.iterdir())}), indent=2))

"""Existing dataset/report workflow freezes a procedure, not a last-fold winner."""
from prop_setup_helpers import open_prop_task
from decimal import Decimal
from hashlib import sha256
import io
import json
import re
import socket
from threading import Thread
import time
import zipfile

import httpx
import pytest
import uvicorn

from alphaquest.app import create_app
from test_backtests_browser import browser, page, playwright
from test_optimization import wait_job
from test_prop_phases import phase_history


@pytest.fixture
def portal(tmp_path):
    # A new library has an explicit complete access-history scope. Do not seed
    # unrelated previously inspected datasets into this holdout demonstration.
    app = create_app(tmp_path / 'datasets.sqlite3')
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', loop='asyncio'))
    sock = socket.socket(); sock.bind(('127.0.0.1', 0))
    url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    thread = Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.01)
        yield {'url': url, 'app': app}
    finally:
        server.should_exit = True; thread.join(timeout=10); sock.close()
        assert not thread.is_alive(), 'Owned browser server did not stop.'


def upload_and_reserve(page, portal, tmp_path):
    path = tmp_path / 'SYNTHETIC-procedure-history.csv'; path.write_bytes(phase_history(20))
    page.goto(portal['url'])
    page.locator('#csv-file').set_input_files(path)
    page.locator('#dataset-name').fill('SYNTHETIC procedure and reserved final sessions')
    page.locator('#symbol').fill('MNQ')
    page.locator('#source-timezone').select_option('UTC')
    page.locator('#dataset-tick-size').fill('.25')
    page.locator('#dataset-point-value').fill('2')
    page.get_by_text('Protect a possible final research holdout', exact=True).click()
    page.locator('#dataset-metadata-only').check()
    page.locator('#validate-button').click()
    playwright.expect(page.locator('#validation-result')).to_contain_text('Validation passed')
    page.locator('#save-button').click()
    playwright.expect(page.locator('#validation-result')).to_contain_text('Dataset saved')
    dataset, = page.request.get(portal['url'] + '/api/datasets').json()
    assert dataset['preview'] == [] and dataset['disclosure'] == 'metadata_only'
    page.get_by_role('button', name='View dataset →').click()
    page.locator('#dataset-research-reservations > summary').click()
    page.locator('#dataset-reservation-first').fill('2026-01-23')
    page.locator('#dataset-reservation-last').fill('2026-01-26')
    page.locator('#dataset-reservation-preview').click()
    playwright.expect(page.locator('#dataset-reservation-evidence')).to_contain_text('INSUFFICIENT_ACCESS_HISTORY')
    page.locator('#dataset-reservation-evidence').screenshot(path=str(tmp_path / 'unknown-external-access-rejection.png'))
    page.locator('#dataset-reservation-external').select_option('declared_not_inspected')
    page.locator('#dataset-reservation-preview').click()
    playwright.expect(page.locator('#dataset-reservation-evidence')).to_contain_text('ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE')
    playwright.expect(page.locator('#dataset-reservation-evidence')).to_contain_text('Untouched-data certificate: no')
    page.locator('#dataset-reservation-evidence').screenshot(path=str(tmp_path / 'holdout-access-preview.png'))
    page.locator('#dataset-reservation-save').click()
    playwright.expect(page.locator('#dataset-reservation-status')).to_contain_text('RESERVED')
    reserved, = page.request.get(portal['url'] + f"/api/datasets/{dataset['id']}/research-reservations").json()['items']
    assert reserved['sessions'] == ['2026-01-23', '2026-01-26']
    assert page.request.get(portal['url'] + f"/api/datasets/{dataset['id']}/csv").status == 409
    page.locator('#close-dialog').click()
    return dataset, reserved


def source_grid(client, dataset):
    response = client.post('/api/optimizations', json=dict(
        dataset_id=dataset['id'], strategy_id='consecutive_green_hold', method='exhaustive',
        workers=1, automatic_prop=False,
        parameter_ranges=dict(green_bar_count=dict(start=1, end=2, step=1),
                              hold_minutes=dict(start=1, end=1, step=0),
                              contracts=dict(start=1, end=1, step=0)),
        execution_settings=dict(initial_capital='10000', tick_size='.25', point_value='2',
                                slippage_ticks=0, commission_per_contract_per_side='0'),
        sample_split=dict(mode='dates', is_start='2026-01-05', is_end='2026-01-22',
                          oos_start='2026-01-23', oos_end='2026-01-30')))
    assert response.status_code == 202, response.text
    job = wait_job(client, response.json()['id']); assert job['status'] == 'complete', job
    rows = client.get('/api/optimizations/' + job['id'] + '/results').json()['items']
    records = [client.get('/api/backtests/' + row['run_id']).json() for row in rows]
    assert {Decimal(record['summary']['total_net_pnl']) for record in records} == {Decimal(4200), Decimal(1400)}
    return job, records


def configure_research(page, portal, records):
    page.goto(portal['url'] + '/#backtests/report/' + records[0]['id'])
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'research', close_outer=True)
    page.locator('#robust-configure > summary').click()
    page.locator('#robust-name').fill('SYNTHETIC complete procedure with protected final evidence')
    page.locator('#robust-source-search').fill(records[1]['id'][:8])
    page.get_by_role('checkbox', name=re.compile(records[1]['id'][:8])).check()
    for key, value in dict(outer_train_sessions=8, outer_test_sessions=2,
            inner_train_sessions=2, inner_validation_sessions=2, purge_sessions=1,
            embargo_sessions=1, minimum_inner_folds=2, minimum_outer_folds=2).items():
        page.locator('#robust-' + key).fill(str(value))
    page.locator('#robust-qualification-configure > summary').click()
    for key, value in dict(minimum_folds=2, minimum_sessions=4, minimum_trades=4,
            minimum_trades_per_fold=2, minimum_positive_fold_fraction=1,
            maximum_profit_concentration=.6, additional_round_trip_cost=10,
            minimum_neighbors=1, bootstrap_replicates=400, bootstrap_block_sessions=1,
            confidence_level=.95, minimum_bootstrap_tail_samples=5).items():
        page.locator('#robust-qualification-' + key).fill(str(value))
    page.locator('#robust-economic-configure > summary').click()
    page.locator('#robust-economic-funded').check()
    page.locator('#robust-economic-funded-quantities').fill('10,20')
    page.locator('#robust-economic-funded-fields').get_by_text('Forecast sampling, seeds and model guards', exact=True).click()
    page.locator('#robust-economic-funded-simulations').fill('8')
    page.locator('#robust-economic-funded-block_weekdays').fill('1')
    page.locator('#robust-final-requirements > summary').click()
    page.locator('#robust-require-final-holdout').check()
    page.locator('#robust-final-enable-cash-floor').check()
    page.locator('#robust-final-cash-floor').fill('1')


def test_complete_procedure_final_holdout_and_current_development(page, portal, tmp_path):
    dataset, reservation = upload_and_reserve(page, portal, tmp_path)
    with httpx.Client(base_url=portal['url'], timeout=300) as client:
        job, records = source_grid(client, dataset)
    configure_research(page, portal, records)
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-run')).to_be_enabled(timeout=60000)
    page.locator('#robust-run').click()
    playwright.expect(page.locator('#procedure-preview')).to_be_visible(timeout=180000)
    saved, = page.request.get(portal['url'] + '/api/research-campaigns/robust?source_id=' + records[0]['id']).json()['items']
    campaign_id = saved['campaign_id']; base = portal['url'] + '/api/research-campaigns/robust/' + campaign_id
    original = page.request.get(base + '/exports/report.json').body()
    record = page.request.get(base).json()
    assert record['declaration']['final_evidence']['minimum_funded_trader_receipts'] == '1'
    assert record['declaration']['final_evidence']['require_final_holdout']
    page.locator('#procedure-reservation').select_option(reservation['id'])
    page.locator('#procedure-preview').click()
    playwright.expect(page.locator('#procedure-freeze')).to_be_enabled(timeout=30000)
    page.locator('#procedure-preview-evidence').screenshot(path=str(tmp_path / 'complete-procedure-preview.png'))
    page.locator('#procedure-freeze').click()
    playwright.expect(page.locator('#procedure-final-check')).to_be_visible(timeout=30000)
    package = page.request.get(base).json()['procedure']
    assert len(package['algorithm']['configurations']) == 2
    assert package['terminal_plan']['train']['sessions'] == record['plan']['session_inventory']['sessions'][-10:-2]
    page.locator('#procedure-final-check').click()
    playwright.expect(page.locator('#procedure-final-run')).to_be_enabled(timeout=30000)
    page.locator('#procedure-final-checks').screenshot(path=str(tmp_path / 'frozen-final-access-check.png'))
    page.locator('#procedure-final-run').click()
    playwright.expect(page.locator('#procedure-applications')).to_contain_text('final verification · complete', timeout=180000)
    record = page.request.get(base).json()
    final, = [item for item in record['applications'] if item['purpose'] == 'final_verification']
    final_result = final['result']
    assert final_result['terminal_plan']['application_role'] == 'final_fit'
    assert final_result['final_verification']['status'] == 'FAILED_VERIFICATION_CRITERIA'
    assert final_result['final_verification']['selection_repeated_on_final'] is False
    assert len(final_result['economic_selection']['phases'][0]['frozen_packages']) == 4
    assert sorted(Decimal(row['metrics']['mean_session_net']) for row in final_result['qualification']['candidates']) == [Decimal(100), Decimal(300)]
    assert all(Decimal(item['result']['cash_received']) == 0 for item in final_result['final_verification']['replay']['items'])
    assert final_result['recommendation'][0]['status'] == 'NO_QUALIFIED_DEPLOYMENT_CANDIDATE'
    assert page.request.get(base + '/exports/report.json').body() == original
    page.locator('#procedure-current-run').click()
    playwright.expect(page.locator('#procedure-applications')).to_contain_text('current development · complete', timeout=180000)
    record = page.request.get(base).json()
    current, = [item for item in record['applications'] if item['purpose'] == 'current_development']
    assert current['result']['qualification'] == final_result['qualification']
    assert current['result']['terminal_plan']['application_role'] == 'current_development'
    assert current['result']['final_verification']['replay'] is None
    assert set(current['result']['terminal_plan']['train']['sessions']).isdisjoint(reservation['sessions'])
    downloads = {}; reopens = {}
    for role, application in [('final', final), ('current', current)]:
        page.goto(portal['url'] + '/#backtests/prop/job/' + application['analysis_id'])
        playwright.expect(page.locator('#procedure-application-result')).to_contain_text('Production qualified: no', timeout=30000)
        playwright.expect(page.locator('#procedure-terminal-qualification tbody tr')).to_have_count(2)
        playwright.expect(page.locator('#procedure-application-result .procedure-recommendation')).to_contain_text('NO QUALIFIED DEPLOYMENT CANDIDATE')
        page.locator('#procedure-application-result #procedure-terminal-window').screenshot(path=str(tmp_path / (role + '-terminal-window.png')))
        page.locator('#procedure-application-result .procedure-recommendation').screenshot(path=str(tmp_path / (role + '-readiness.png')))
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.locator('#procedure-terminal-qualification').screenshot(path=str(tmp_path / (role + '-qualification-narrow.png')))
        page.set_viewport_size({'width': 1440, 'height': 1100})
        paths = {'report.json': '/exports/report.json', 'analysis.zip': '/exports/analysis.zip'}
        for filename, suffix in paths.items():
            response = page.request.get(base + '/applications/' + application['application_id'] + suffix)
            assert response.ok, response.text()
            name = role + '-' + filename; (tmp_path / name).write_bytes(response.body()); downloads[name] = sha256(response.body()).hexdigest()
        report = json.loads((tmp_path / (role + '-report.json')).read_bytes())
        with zipfile.ZipFile(io.BytesIO((tmp_path / (role + '-analysis.zip')).read_bytes())) as bundle:
            for name, entry in report['files'].items():
                assert sha256(bundle.read(name)).hexdigest() == (entry['sha256'] if isinstance(entry, dict) else entry)
        posts = []
        listener = lambda request: posts.append(request.url) if request.method == 'POST' else None
        page.on('request', listener); page.reload()
        playwright.expect(page.locator('#procedure-terminal-qualification tbody tr')).to_have_count(2)
        page.remove_listener('request', listener); assert posts == []; reopens[role] = posts
    raw = page.request.get(portal['url'] + '/api/datasets/' + dataset['id'] + '/csv')
    assert raw.ok and sha256(raw.body()).hexdigest() == dataset['sha256']
    assert raw.body() == (tmp_path / 'SYNTHETIC-procedure-history.csv').read_bytes()
    (tmp_path / 'campaign.json').write_text(json.dumps(record, indent=2))
    (tmp_path / 'evidence.json').write_text(json.dumps(dict(campaign_id=campaign_id,
        procedure_sha256=package['procedure_sha256'], dataset_id=dataset['id'], dataset_sha256=dataset['sha256'],
        reservation=reservation, source_ids=[row['id'] for row in records], source_research=records[0]['run_metadata']['research'],
        applications={role: {'application_id': item['application_id'], 'analysis_id': item['analysis_id']} for role, item in [('final', final), ('current', current)]},
        expected={'terminal_configuration_means': [100, 300], 'complete_funded_policy_family': 4, 'received_cash_per_final_policy': 0,
            'predeclared_required_receipts': 1, 'recommendation': 'NO_QUALIFIED_DEPLOYMENT_CANDIDATE', 'outer_report_unchanged': True},
        downloads=downloads, report_reopen_posts=reopens, synthetic=True,
        server='Owned temporary server stops in fixture teardown.'), indent=2))

"""Automatic calendar bounds: date arithmetic, strict admission and durability."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
import json
import zipfile

from fastapi.testclient import TestClient
import pytest

from alphaquest.app import create_app
from alphaquest.research_campaigns import campaign_search_settings
from test_optimization import wait_job
from test_prop_phases import phase_history
from test_research_campaigns import declaration, create, run


def saved_grid_source(client):
    response = client.post('/api/datasets', params=dict(filename='SYNTHETIC-auto-calendar.csv',
        name='SYNTHETIC automatic calendar coverage', source_timezone='UTC', symbol='NQ',
        tick_size='.25', point_value='20'), content=phase_history(24))
    assert response.status_code == 201, response.text
    response = client.post('/api/optimizations', json=dict(dataset_id=response.json()['id'],
        strategy_id='consecutive_green_hold', method='exhaustive', workers=1, automatic_prop=False,
        parameter_ranges={name:dict(start=value, end=value, step=0) for name,value in
            [('green_bar_count',1),('hold_minutes',1),('contracts',1)]},
        execution_settings=dict(initial_capital='10000', slippage_ticks=0, commission_per_contract_per_side='0'),
        sample_split=dict(mode='dates', is_start='2026-01-05', is_end='2026-01-14',
            oos_start='2026-01-15', oos_end='2026-02-05')))
    assert response.status_code == 202, response.text
    id = response.json()['id']
    assert wait_job(client, id)['status'] == 'complete'
    rows = client.get(f'/api/optimizations/{id}/results').json()['items']
    return client.get('/api/backtests/'+rows[0]['run_id']).json(), id


def settings(phase='evaluation', starts=('2026-01-05',), retry=None, **extra):
    return SimpleNamespace(phase=phase, retry=retry,
        search_settings=dict(calendar=dict(start_dates=list(starts)), **extra))


@pytest.mark.parametrize('body,expected', [
    (settings(), '2036-01-03'),
    (settings(starts=('2040-01-02',)), '2049-12-30'),
    (settings(starts=('2028-02-28',), retry=dict(max_calendar_days=3)), '2028-03-02'),
    (settings(starts=('2028-02-28','2028-02-29'), retry=dict(max_calendar_days=1)), '2028-03-01'),
    (settings('funded', ('2028-02-28',), horizon_calendar_days=2), '2028-03-01'),
    (settings('funded', ('2026-12-31',), horizon_calendar_days=1), '2027-01-01'),
    (settings('funded', ('2040-01-02',), horizon_calendar_days=14, receipt_delay_calendar_days=365), '2040-01-16'),
])
def test_derived_bounds_and_no_mutation(body, expected):
    before = deepcopy(body.search_settings)
    assert campaign_search_settings(body)['calendar']['coverage_end'] == expected
    assert body.search_settings == before


def test_declared_closures_preserved_and_explicit_calendars_unchanged():
    body = settings()
    body.search_settings['calendar']['closures'] = ['2026-01-12']
    assert campaign_search_settings(body)['calendar']['closures'] == ['2026-01-12']
    body.search_settings['calendar'].update(coverage_end='2026-01-06', version='explicit-calendar-v7')
    assert campaign_search_settings(body) == body.search_settings  # Existing phase validation still rejects inadequate coverage.


@pytest.mark.parametrize('body,match', [
    (settings(starts=()), 'start_dates'),
    (settings(starts=('not-a-date',)), 'YYYY-MM-DD'),
    (settings(starts=('9999-12-31',)), 'supported calendar dates'),
    (settings('funded', horizon_calendar_days=0), 'horizon_calendar_days'),
    (settings('funded', horizon_calendar_days=True), 'horizon_calendar_days'),
])
def test_invalid_automatic_bounds_reject(body, match):
    with pytest.raises(ValueError, match=match):
        campaign_search_settings(body)


@pytest.fixture(scope='module')
def library(tmp_path_factory):
    root = tmp_path_factory.mktemp('auto-calendar-library')
    with TestClient(create_app(root/'datasets.sqlite3')) as client:
        source, job = saved_grid_source(client)
        yield client, source, root


@pytest.mark.parametrize('phase,end', [('evaluation','2049-12-30'),('funded','2040-01-16')])
def test_normal_api_derivation_explicit_reuse_and_saved_report(library, phase, end):
    client, source, root = library
    body = declaration(source, phase=phase)
    body['sources'][0]['sizes'] = [10 if phase=='evaluation' else 3]
    body['search_settings']['calendar'] = dict(start_dates=['2040-01-02'])
    original = deepcopy(body)
    created = create(client, body)
    assert body == original
    assert 'coverage_end' not in created['declaration']['search_settings']['calendar']
    assert created['manifest']['request']['calendar']['coverage_end'] == end
    campaign = run(client, created['campaign_id'])
    id = campaign['analysis_id']
    report_bytes = client.get(f'/api/prop-analyses/{id}/downloads/report.json').content
    report = json.loads(report_bytes)
    assert report['request']['calendar']['coverage_end'] == end
    row = report['calculations']['candidates'][0]
    if phase == 'evaluation':
        assert row['metrics']['cost_per_funded'] == 70
        assert row['metrics']['expected_calendar_days_to_funded'] == 2
        assert row['manifest']['configuration']['retry']['max_calendar_days'] == 3650
    else:
        assert row['metrics']['expected_payouts'] == row['metrics']['expected_pending_cash'] == 1500
    explicit = deepcopy(body)
    explicit['campaign_id'] = uuid4().hex
    explicit['search_settings']['calendar']['coverage_end'] = end
    same = create(client, explicit)
    assert same['manifest']['calculation_key'] == campaign['manifest']['calculation_key']
    assert run(client, same['campaign_id'])['analysis_id'] == id
    assert client.post('/api/research-campaigns', json=body).json()['campaign_id'] == campaign['campaign_id']
    assert client.get(f'/api/prop-analyses/{id}/downloads/report.json').content == report_bytes
    with zipfile.ZipFile(root/'prop_analyses'/id/'analysis.zip') as archive:
        assert json.loads(archive.read('request.json'))['calendar']['coverage_end'] == end


def test_explicit_short_coverage_and_unverified_version_still_reject(library):
    client, source, root = library
    body = declaration(source)
    body['search_settings']['calendar']['coverage_end'] = '2026-01-06'
    response = client.post('/api/research-campaigns', json=body)
    assert response.status_code == 422 and 'every chain guard date' in response.text
    body['search_settings']['calendar'] = dict(start_dates=['2026-01-05'], version='external-calendar-v1')
    response = client.post('/api/research-campaigns', json=body)
    assert response.status_code == 422 and 'supply coverage_end' in response.text
    assert client.get('/api/research-campaigns/'+body['campaign_id']).status_code == 404

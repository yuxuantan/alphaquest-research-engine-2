"""Fixed-size portal contract on ordinary saved synthetic backtests."""

import pytest

from alphaquest.app import create_app
from prop_desk_fixtures import desk_calculator_sources
from research_fixtures import ResearchClient
from test_prop_analysis_api import wait
from test_prop_phases import save_source


def check(client, source, phase, profile, micros, horizon=None):
    body = dict(source_backtest_id=source['id'], phase=phase, profile_id=profile, micros=micros)
    if horizon is not None:
        body['observation_sessions'] = horizon
    response = client.post('/api/prop-desk/check', json=body)
    assert response.status_code == 200, response.text
    return dict(body, check_sha256=response.json()['check_sha256'])


def result(client, body):
    response = client.post('/api/prop-desk', json=body)
    assert response.status_code == 202, response.text
    id = response.json()['id']
    job = wait(client, id)
    assert job['status'] == 'complete', job
    saved = client.get('/api/prop-desk/' + id)
    assert saved.status_code == 200, saved.text
    return saved.json()


def test_profile_caps_expiry_cutoff_and_pre_payout_breach(tmp_path, desk_calculator_sources):
    database = tmp_path / 'datasets.sqlite3'
    with ResearchClient(create_app(database)) as client:
        slow = save_source(client, green=2, days=8)
        recovery = save_source(client, recovery=True, days=8)

        # A $1,000 NQ day at 1 MNQ earns $100. It reaches only $2,100 at
        # Apex's 21-session expiry and only $200 at a two-day Lucid cutoff.
        for profile, cutoff, label, expiry, amount in (
            ('apex-50k-eod', None, 'provider_expired', 21, 1000),
            ('lucidflex-50k', 2, 'observation_cutoff', None, 1200),
        ):
            body = check(client, slow, 'evaluation', profile, 1, cutoff)
            job = result(client, body)
            report = job['report']
            assert report['rules']['provider_expiry_trading_sessions'] == expiry
            assert report['rules']['daily_loss_limit'] == amount
            assert report['calculations']['outcome_counts'] == dict(passed=0, breached=0, **{label: 1000})
            assert report['calculations']['median_trading_days_to_target'] is None
            assert result(client, body)['id'] == job['id']
            assert client.post('/api/prop-desk', json=dict(body, micros=2)).status_code == 409
            assert client.get(f"/api/jobs/prop_analysis/{job['id']}").json()['links'] == [
                dict(label='Open Prop Desk', href=f"#prop-desk?analysis={job['id']}")]

        for profile, phase, micros, horizon, message in (
            ('apex-50k-eod', 'evaluation', 60, 20, '21-session modeled expiry'),
            ('apex-50k-eod', 'funded', 41, 30, 'at most 40 MNQ'),
            ('lucidflex-50k', 'evaluation', 41, 60, 'at most 40 MNQ'),
        ):
            rejected = client.post('/api/prop-desk/check', json=dict(
                source_backtest_id=slow['id'], phase=phase, profile_id=profile,
                micros=micros, observation_sessions=horizon))
            assert rejected.status_code == 422 and message in rejected.json()['detail']

        # A $3,000 adverse opening gap crosses both the daily and the account
        # floor at 10 MNQ, even though the saved source later closes profitably.
        body = check(client, recovery, 'funded', 'apex-50k-eod', 10, 30)
        job = result(client, body)
        c = job['report']['calculations']
        assert c['probability_breach_before_first_payout'] == c['probability_breach'] == 1
        assert c['probability_any_payout'] == c['probability_complete_ladder'] == 0
        assert c['mean_account_deductions'] == c['mean_trader_receipts'] == 0
        assert all(row['median_trading_day'] is None and row['reached'] == 0 for row in c['milestones'])
        assert len(client.get('/api/prop-desk').json()['items']) == 3
        legacy = client.get('/api/prop-analyses/sources/' + recovery['id'], params={'discover_exports': 'false'})
        assert all(row['id'] != job['id'] for row in legacy.json()['analyses'])

        # The $1,000 NQ day pays $900 at 9 MNQ. Each five-day cycle
        # clears Apex's qualifying days, consistency and safety net.
        apex_body = check(client, slow, 'funded', 'apex-50k-eod', 9, 30)
        apex = result(client, apex_body)
        apex_calculations = apex['report']['calculations']
        assert [row['median_trading_day'] for row in apex_calculations['milestones']] == [5, 10, 15, 20, 25, 30]
        assert apex_calculations['mean_account_deductions'] == apex_calculations['mean_trader_receipts'] == 13000

        path = client.app.state.prop_analyses.root / job['id'] / 'report.json'
        with path.open('ab') as stream:
            stream.write(b' ')
        assert client.get('/api/prop-desk/' + job['id']).status_code == 409
        assert result(client, body)['id'] != job['id']

    with ResearchClient(create_app(database)) as client:
        assert client.get('/api/prop-desk/' + apex['id']).json()['report'] == apex['report']

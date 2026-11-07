"""Dispatch isolation and opt-out grids keep normal durable source workflows."""
import pytest

from alphaquest.prop import phase_dispatch
from test_backtest_api import save_fixture
from test_optimization import client, optimization_body, start, wait_job


@pytest.mark.parametrize('phase', ['evaluation', 'funded'])
def test_dispatch_only_resolves_requested_phase(monkeypatch, phase):
    calls = []
    sentinel = object()
    def load(name, *, package):
        calls.append((name, package))
        return sentinel
    monkeypatch.setattr(phase_dispatch, 'import_module', load)
    assert phase_dispatch.module_for_mode(phase+'_optimization') is sentinel
    assert calls == [('.'+phase+'_optimization', 'alphaquest.prop')]
    for invalid in ('', 'joint', 'funded_assessment', 'evaluation_optimization_typo'):
        with pytest.raises(ValueError):
            phase_dispatch.module_for_mode(invalid)
        with pytest.raises(ValueError):
            phase_dispatch.module_for(invalid)
    assert len(calls) == 1


@pytest.mark.parametrize('workers', [1, 2])
def test_opt_out_is_saved_reusable_and_separate_from_automatic_jobs(client, monkeypatch, workers):
    dataset = save_fixture(client)
    request = dict(optimization_body(dataset['id']), automatic_prop=False, workers=workers, reuse_results=True)
    def forbidden(*args, **kwargs):
        pytest.fail('Opt-out grid must not prepare or run automatic prop calculations')
    with monkeypatch.context() as patch:
        patch.setattr('alphaquest.optimization_worker.compute_default', forbidden)
        patch.setattr(client.app.state.prop_analyses, 'calculation_snapshot', forbidden)
        job = wait_job(client, start(client, request))
    assert job['status'] == 'complete', job
    assert job['request']['automatic_prop'] is False and job['default_prop_profile'] is None
    assert 'historical_net' not in job['metric_columns']
    rows = client.get(f"/api/optimizations/{job['id']}/results").json()['items']
    assert [float(r['metrics']['total_net_pnl']) for r in rows] == [13, 26, 39]
    for row in rows:
        record = client.get('/api/backtests/'+row['run_id']).json()
        assert 'automatic_prop_analysis' not in record['run_metadata']
        assert 'prop_analysis' not in row
        source = client.get('/api/prop-analyses/sources/'+row['run_id']).json()
        assert source['analyses'] == []
    reused = wait_job(client, start(client, request))
    assert reused['reused_trials'] == 3
    # The old request shape remains automatic; its cache cannot reuse opt-out rows.
    automatic = wait_job(client, start(client, dict(optimization_body(dataset['id']), reuse_results=True)))
    assert automatic['status'] == 'complete' and automatic['default_prop_profile']
    assert automatic['reused_trials'] == 0
    assert wait_job(client, start(client, request))['reused_trials'] == 3
    invalid = client.post('/api/optimizations', json=dict(request, automatic_prop='false'))
    assert invalid.status_code == 422

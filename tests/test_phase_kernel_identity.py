"""Both selectable provider kernels bind phase caches and frozen launches."""
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import pytest

from alphaquest.prop import (
    evaluation_optimization as evaluation,
    funded_optimization as funded,
    lucid_backend,
    native_backend,
)
from alphaquest.prop.phase_profiles import (
    EvaluationProfile, EvaluationSamplingConfig, FundedProfile, NativeExecution,
    SamplingConfig, SavedTradeSource, SimulationConfig, rule_version,
)
from alphaquest.prop.phase_search import PhaseCalendar


PHASES = (evaluation, funded)
BACKENDS = (native_backend, lucid_backend)
REQUIRED_FILES = {
    'native_engine.py', 'native_backend.py', 'lucid_engine.py', 'lucid_rules.py',
    'lucid_backend.py', 'native_control.py', 'native_money.py', 'native_draws.py',
    'native_replay.py', 'native_search.py', 'phase_profiles.py', 'phase_search.py',
    'sizing.py', 'sizing_runtime.py', 'cash_ledger.py', 'rule_provenance.py',
    '../execution.py', '../decimal_math.py', '../session_calendar.py',
    '../strategies/vwap_pullback_risk_sizing.py',
}


def runtime(identity, phase, backend):
    if phase is evaluation:
        return identity['kernel' if backend is native_backend else 'lucid_kernel']
    return identity['native_kernels']['apex' if backend is native_backend else 'lucid']


def native_search(phase):
    """A valid request for hashing only: no source reads or calculations."""
    source = SavedTradeSource('a' * 32)
    calendar = PhaseCalendar(('2026-01-12',), '2026-01-19')
    simulation = SimulationConfig(simulations=2, seed=1729)
    execution = NativeExecution(horizon_calendar_days=7)
    if phase is evaluation:
        profile = EvaluationProfile('apex-50k-eod', rule_version('apex-50k-eod'), '30', '40')
        candidate = evaluation.EvaluationCandidate(source, profile, 3, simulation,
            EvaluationSamplingConfig(block_weekdays=1, chain_simulations=2, chain_seed=1729))
        return evaluation.EvaluationSearch(source.source_backtest_id, (candidate,), calendar,
            native_execution=execution)
    profile = FundedProfile('apex-50k-eod', rule_version('apex-50k-eod'))
    candidate = funded.FundedCandidate(source, profile, 3, simulation, SamplingConfig(1))
    return funded.FundedSearch(source.source_backtest_id, (candidate,), calendar, 7, 0,
        bootstrap_replicates=100, native_execution=execution)


@pytest.mark.parametrize('phase', PHASES, ids=['evaluation', 'funded'])
def test_each_phase_captures_actual_provider_and_native_source_hashes(phase):
    identity = phase.implementation_identity()
    assert REQUIRED_FILES <= identity['files'].keys()
    assert phase.__name__.rsplit('.', 1)[-1] + '.py' in identity['files']
    assert ('evaluation_profiles.py' if phase is evaluation else 'funded_profiles.py') in identity['files']
    directory = Path(phase.__file__).parent
    for name, expected in identity['files'].items():
        assert expected == sha256((directory / name).read_bytes()).hexdigest(), name
    for backend in BACKENDS:
        assert runtime(identity, phase, backend) == backend.identity()
    # Existing keys retain their established meanings; new runtime coverage is additive.
    if phase is funded:
        assert identity['kernel'] == 'native Python reference account transitions'


@pytest.mark.parametrize('phase', PHASES, ids=['evaluation', 'funded'])
@pytest.mark.parametrize('backend', BACKENDS, ids=['apex', 'lucid'])
def test_actual_provider_runtime_change_invalidates_each_phase_cache(phase, backend, monkeypatch):
    if backend.compiled is None:
        pytest.skip('The matching optional compiled provider kernel is unavailable.')
    monkeypatch.setenv('ALPHAQUEST_PROP_BACKEND', 'python')
    request = native_search(phase)
    before = phase.implementation_identity()
    old_key = phase.search_key(request, [])
    assert runtime(before, phase, backend)['name'] == 'python'
    # Select the actual installed compiled module for just this provider. The
    # other provider stays on its actual Python implementation; no math is mocked.
    monkeypatch.setattr(backend, 'module', lambda: backend.compiled)
    after = phase.implementation_identity()
    changed = runtime(after, phase, backend)
    assert changed['name'] == 'compiled'
    assert changed['binary_sha256'] == sha256(Path(backend.compiled.__file__).read_bytes()).hexdigest()
    assert changed['source_sha256'] == runtime(before, phase, backend)['source_sha256']
    other, = (item for item in BACKENDS if item is not backend)
    assert runtime(after, phase, other) == runtime(before, phase, other)
    assert after['files'] == before['files']
    assert after != before
    assert phase.search_key(request, []) != old_key


def test_native_funded_frozen_launch_rejects_each_changed_runtime_before_oos(tmp_path, monkeypatch):
    """A real normal campaign stays readable but cannot launch another kernel."""
    from fastapi.testclient import TestClient
    from alphaquest.app import create_app
    from alphaquest import research_api
    from test_native_phase_campaigns import declaration, source_with_complete_oos
    from test_native_replay_api import wait

    if any(backend.compiled is None for backend in BACKENDS):
        pytest.skip('Both matching optional compiled provider kernels are required for this runtime-switch check.')
    monkeypatch.setenv('ALPHAQUEST_PROP_BACKEND', 'python')
    library = tmp_path / 'library'
    with TestClient(create_app(library / 'datasets.sqlite3')) as client:
        source = source_with_complete_oos(client)
        body = declaration(client, source, phase='funded')
        body['sources'][0]['sizes'] = [3]
        body['is_window']['last_session'] = '2026-01-09'
        body['search_settings'].update(horizon_calendar_days=7)
        body['search_settings']['native_execution']['horizon_calendar_days'] = 7
        body['search_settings']['calendar'].update(start_dates=['2026-01-12'], coverage_end='2026-01-19')
        response = client.post('/api/research-campaigns', json=body)
        assert response.status_code == 201, response.text
        campaign_id = response.json()['campaign_id']
        prefix = '/api/research-campaigns/' + campaign_id
        response = client.post(prefix + '/run')
        assert response.status_code == 202, response.text
        analysis_id = response.json()['analysis_id']
        assert wait(client, analysis_id)['status'] == 'complete'
        report_response = client.get('/api/prop-analyses/' + analysis_id + '/downloads/report.json')
        report = report_response.json()
        row, = report['calculations']['candidates']
        assert row['metrics']['expected_payouts'] == 1500
        response = client.post(prefix + '/freeze', json=dict(candidate_ids=[row['candidate_id']],
            rationale='Synthetic native Funded cash oracle, frozen before any OOS read.'))
        assert response.status_code == 200, response.text
        frozen = client.get(prefix + '/exports/frozen_package.json').content
        archive = client.get('/api/prop-analyses/' + analysis_id + '/downloads/analysis.zip').content
        before = funded.implementation_identity()
        assert report['implementation'] == before
        with client.app.state.prop_analyses.connect() as db:
            access_before = db.execute('SELECT COUNT(*) FROM research_access_events').fetchone()[0]

        async def forbidden(*args, **kwargs):
            pytest.fail('Changed numerical runtime must reject before ordinary OOS launch.')

        monkeypatch.setattr(research_api, 'run_oos_impl', forbidden)
        blocked_runtimes = []
        for backend in BACKENDS:
            with monkeypatch.context() as patch:
                patch.setattr(backend, 'module', lambda: backend.compiled)
                after = funded.implementation_identity()
                assert after['files'] == before['files']
                assert runtime(after, funded, backend)['name'] == 'compiled'
                response = client.post(prefix + '/assessments', json=dict(request_id=uuid4().hex))
                assert response.status_code == 409 and 'implementation changed' in response.text, response.text
                assert client.get(prefix + '/assessments').json()['items'] == []
                assert client.get('/api/prop-analyses/' + analysis_id + '/downloads/report.json').content == report_response.content
                assert client.get('/api/prop-analyses/' + analysis_id + '/downloads/analysis.zip').content == archive
                assert client.get(prefix + '/exports/frozen_package.json').content == frozen
                # Idempotent retrieval is still the original durable calculation.
                assert client.post(prefix + '/run').json()['analysis_id'] == analysis_id
                blocked_runtimes.append(dict(provider=backend.__name__, identity=runtime(after, funded, backend),
                    status_code=response.status_code, detail=response.json()))
        with client.app.state.prop_analyses.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM research_access_events').fetchone()[0] == access_before
        (tmp_path / 'kernel-identity-evidence.json').write_text(json.dumps(dict(
            library=str(library), source_id=source['id'], campaign_id=campaign_id, analysis_id=analysis_id,
            expected_received_cash=1500, implementation=before, blocked_runtimes=blocked_runtimes,
            report_sha256=sha256(report_response.content).hexdigest(), archive_sha256=sha256(archive).hexdigest(),
            frozen_package_sha256=sha256(frozen).hexdigest(), oos_attempts=0), indent=2))

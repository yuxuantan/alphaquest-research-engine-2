"""Independent phase components on ordinary saved synthetic backtests.

All analytical expectations stay here; no runtime oracle tables or fake sources.
"""
from dataclasses import asdict, replace
from hashlib import sha256
import json
import shutil

import pytest

from alphaquest.app import create_app
from alphaquest.backtest_runs import RunStore
from alphaquest.prop import native_analysis as legacy
from alphaquest.prop.evaluation_profiles import simulate_evaluation_profile
from alphaquest.prop.funded_profiles import simulate_funded_profile
from alphaquest.prop.phase_profiles import (
    EvaluationProfile, EvaluationSamplingConfig, FundedProfile, ResearchPeriod,
    SamplingConfig, SavedTradeSource, SimulationConfig, SourceCosts, rule_version,
)
from research_fixtures import ResearchClient
from test_prop_phases import save_source
from test_prop_training_economics import source as legacy_rows


@pytest.fixture(scope='module')
def library(tmp_path_factory):
    root = tmp_path_factory.mktemp('phase-profile-library')
    with ResearchClient(create_app(root / 'datasets.sqlite3')) as client:
        a = save_source(client, days=8)
        b = save_source(client, green=2, days=8)
        recovery = save_source(client, recovery=True, days=8)
        yield client.app.state.runs, a, b, recovery


def evaluation(firm='apex-50k-eod', **changes):
    return replace(EvaluationProfile(firm, rule_version(firm), '49' if firm == 'apex-50k-eod' else '80.5',
                                    '129' if firm == 'apex-50k-eod' else '0'), **changes)


def funded(firm='apex-50k-eod', **changes):
    return replace(FundedProfile(firm, rule_version(firm)), **changes)


SIM = SimulationConfig(simulations=8)
SAMPLE = EvaluationSamplingConfig(chain_simulations=8)
COSTS = SourceCosts(mode='source')


def eval_run(runs, record, **kwargs):
    return simulate_evaluation_profile(runs, SavedTradeSource(record['id']), kwargs.pop('profile', evaluation()),
        kwargs.pop('micros', 10), SIM, sampling=kwargs.pop('sampling', SAMPLE), costs=kwargs.pop('costs', COSTS), **kwargs)


def funded_run(runs, record, **kwargs):
    return simulate_funded_profile(runs, SavedTradeSource(record['id']), kwargs.pop('profile', funded()),
        kwargs.pop('micros', 3), kwargs.pop('horizon_weekdays', 30), SIM, costs=kwargs.pop('costs', COSTS), **kwargs)


def fail_other_phase(*args, **kwargs):
    pytest.fail('Opposite-phase simulator/selector/export discovery was accessed')


class SingleSource:
    """Workers already support this source-record adapter; reject any other ID."""
    def __init__(self, runs, record):
        self.root, self.record = runs.root, record
        self.reads = []

    def read_source_record(self, id):
        assert id == self.record['id'], 'Accessed an opposite-phase source'
        self.reads.append(id)
        return self.record


def test_evaluation_is_independent_and_never_reads_funded(library, monkeypatch):
    from alphaquest.prop import joint_sizing, source
    runs, a, b, _ = library
    restricted = SingleSource(runs, a)
    monkeypatch.setattr(legacy, 'funded', fail_other_phase)
    monkeypatch.setattr(legacy, 'account_backend', fail_other_phase)
    monkeypatch.setattr(legacy, 'calculate', fail_other_phase)
    monkeypatch.setattr(joint_sizing, 'select', fail_other_phase)
    monkeypatch.setattr(source, 'matching_exports', fail_other_phase)
    r = eval_run(restricted, a)
    assert restricted.reads == [a['id'], a['id']]
    assert r.outcomes == ['passed'] * 8
    assert r.duration_weekdays == [1] * 8
    # One $49 purchase, $129 activation; one trade weekday + one activation.
    assert r.acquisition['cost_per_funded'] == 178
    assert r.acquisition['replacement_days'] == 2
    assert r.acquisition['cost_se'] == r.acquisition['replacement_days_se'] == 0
    assert r.censoring.status == r.censoring.chain_status == 'resolved'
    assert 'calendar days' in r.provenance['time_unit']
    assert r.provenance['source']['native_risk'] == a['intratrade_risk']
    assert r.provenance['source']['backtest']['run_metadata']['strategy'] == a['run_metadata']['strategy']
    json.dumps(asdict(r), allow_nan=False)


def test_funded_runs_with_zero_evaluation_passes_and_never_reads_evaluation(library, monkeypatch):
    from alphaquest.prop import joint_sizing, source
    runs, _, b, _ = library
    # This source earns $1000/NQ each day. At 1 MNQ a 21-session
    # evaluation earns only $2100: every sampled attempt expires.
    e = eval_run(runs, b, micros=1)
    assert e.evaluation['passed'] == 0 and e.evaluation['expired_paths'] == 8
    assert e.censoring.status == 'unresolved' and e.censoring.censored_paths == 0
    assert e.acquisition['replacement_days'] is None and e.acquisition['cost_per_funded'] is None
    restricted = SingleSource(runs, b)
    monkeypatch.setattr(legacy, 'evaluation_model', fail_other_phase)
    monkeypatch.setattr(legacy, 'training_economics', fail_other_phase)
    monkeypatch.setattr(legacy, 'calculate', fail_other_phase)
    monkeypatch.setattr(joint_sizing, 'select', fail_other_phase)
    monkeypatch.setattr(source, 'matching_exports', fail_other_phase)
    r = funded_run(restricted, b, micros=10)
    assert restricted.reads == [b['id'], b['id']]
    assert r.payouts['mean_trader_payout'] == 13000
    assert r.survival['lifetime_complete'] and r.censoring.status == 'resolved'
    assert all(len(p['trader_payouts']) == 6 for p in r.paths)
    assert 'evaluation_price' not in r.provenance['profile']
    json.dumps(asdict(r), allow_nan=False)


@pytest.mark.parametrize('firm,eval_days,chain_days,price,total,life', [
    ('apex-50k-eod', 1, 2, 178, 13000, 30),
    ('lucidflex-50k', 3, 3, 80.5, 9000, 25),
])
def test_existing_provider_evaluation_and_payout_rules(library, firm, eval_days, chain_days, price, total, life):
    runs, a, _, _ = library
    e = eval_run(runs, a, profile=evaluation(firm))
    f = funded_run(runs, a, profile=funded(firm))
    assert e.duration_weekdays == [eval_days] * 8
    assert e.acquisition['replacement_days'] == chain_days
    assert e.acquisition['cost_per_funded'] == price
    assert f.payouts['mean_trader_payout'] == total
    assert f.survival['mean_terminal_lifetime_weekdays'] == life
    assert f.paths[0]['trader_payouts'] == [(day, amount) for day, amount in
        ([(5,1500),(10,1500),(15,2000),(20,2500),(25,2500),(30,3000)] if firm == 'apex-50k-eod'
         else [(5,1800),(10,1800),(15,1800),(20,1800),(25,1800)])]
    if firm == 'lucidflex-50k':
        assert f.payouts['mean_gross_account_deduction'] == 10000


def test_funded_approval_policy_and_tiers_are_preserved(library):
    runs, a, _, _ = library
    r = funded_run(runs, a, profile=funded(approval_day_counts=False), horizon_weekdays=35)
    assert [day for day, _ in r.paths[0]['trader_payouts']] == [5,11,17,23,29,35]
    # A request for 40 MNQ starts at the existing 20-MNQ initial tier.
    r = funded_run(runs, a, micros=40, horizon_weekdays=1)
    assert r.paths[0]['equity'] == 6000


def test_risk_breach_precedes_a_profitable_close_in_both_phases(library):
    runs, _, _, recovery = library
    e = eval_run(runs, recovery)
    f = funded_run(runs, recovery, micros=10)
    assert e.outcomes == ['blown'] * 8
    assert f.downside['probability_breach'] == 1
    assert f.payouts['mean_trader_payout'] == 0
    assert all(p['observed_weekdays'] == 1 for p in f.paths)


def test_censoring_and_zero_payout_horizon_do_not_invent_terminal_means(library):
    runs, a, _, _ = library
    e = eval_run(runs, a, profile=evaluation('lucidflex-50k'), micros=1,
                 sampling=replace(SAMPLE, computational_horizon_weekdays=2))
    assert e.censoring.status == 'censored' and e.censoring.censored_paths == 8
    assert e.evaluation['pass_probability_bounds'] == [0, 1]
    assert e.evaluation['provider_deadline_weekdays'] is None
    assert e.evaluation['expired_paths'] == 0 and e.acquisition['replacement_days'] is None
    f = funded_run(runs, a, micros=1, horizon_weekdays=4)
    assert f.censoring.status == 'censored' and f.censoring.censored_paths == 8
    assert f.survival['mean_terminal_lifetime_weekdays'] is None
    assert f.survival['restricted_mean_active_weekdays'] == 4
    assert f.payouts['mean_trader_payout'] == f.downside['payout_p10'] == 0
    assert f.payouts['horizon_observations_complete']
    # Exactly at session 5 the legacy kernel pays; the public cap is inclusive.
    f = funded_run(runs, a, horizon_weekdays=5)
    assert f.payouts['mean_trader_payout'] == 1500
    assert f.survival['mean_terminal_lifetime_weekdays'] is None


def test_chain_abort_remains_censored_without_fabricated_path_counts(library, monkeypatch):
    runs, a, _, _ = library
    original = legacy.evaluation_model
    def guarded(*args, **kwargs):
        if kwargs.get('chain'):
            raise ValueError('No pass within the 10,000-attempt funding-time bound; acquisition time is unavailable.')
        return original(*args, **kwargs)
    monkeypatch.setattr(legacy, 'evaluation_model', guarded)
    e = eval_run(runs, a)
    assert e.censoring.status == e.censoring.chain_status == 'censored'
    assert e.acquisition['replacement_days'] is None
    assert e.acquisition['funding_chain_simulations'] == 0
    assert 'unavailable' in e.censoring.reason


def test_research_period_retains_empty_weekdays_and_never_splits_again(library):
    runs, a, _, _ = library
    first = a['period_start_utc'][:10]
    period = ResearchPeriod(first, first)
    e = eval_run(runs, a, period=period)
    assert e.provenance['source']['profile_research_period']['weekdays'] == 1
    assert e.outcomes == ['passed'] * 8
    with pytest.raises(ValueError, match='outside the saved'):
        eval_run(runs, a, period=ResearchPeriod('2020-01-01', '2020-01-02'))


def test_commission_replacement_is_applied_once_in_both_phases(library):
    runs, a, _, _ = library
    costs = SourceCosts(mode='override', per_side='1')
    e = eval_run(runs, a, costs=costs)
    f = funded_run(runs, a, costs=costs, horizon_weekdays=1)
    # $300 per MNQ minus $2 round trip: 10 MNQ earns $2980 per day,
    # so evaluation needs two days; 3 funded MNQ earns exactly $894.
    assert e.duration_weekdays == [2] * 8
    assert f.paths[0]['equity'] == 894
    assert f.provenance['source']['commission_simulation']['round_turn'] == '2'


@pytest.mark.parametrize('phase', ['evaluation', 'funded'])
@pytest.mark.parametrize('damage,reason', [('risk', 'risk coverage'), ('cost', 'costs do not reconcile'),
                                          ('scaling', 'size scaling'), ('hash', 'SHA-256')])
def test_source_and_risk_rejections_are_shared(library, tmp_path, phase, damage, reason):
    original, a, _, _ = library
    runs = RunStore(tmp_path)
    folder = runs.root / a['id']
    shutil.copytree(original.root / a['id'], folder)
    record = json.loads(json.dumps(a))
    if damage == 'risk':
        record.pop('intratrade_risk')
    elif damage == 'scaling':
        record['run_metadata']['strategy']['parameters']['use_vol_sizing'] = True
    elif damage == 'hash':
        with (folder / 'intratrade_risk.csv').open('a') as stream:
            stream.write('\n')
    else:
        path = folder / 'trades.csv'
        import csv, io
        rows = list(csv.DictReader(io.StringIO(path.read_text())))
        rows[0]['net_pnl'] = '999999'
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    with runs.connect() as db:
        db.execute('INSERT INTO runs VALUES (?,?,?)', (a['id'], '2026-11-05', json.dumps(record)))
    with pytest.raises(ValueError, match=reason):
        (eval_run if phase == 'evaluation' else funded_run)(runs, a)


def test_source_changed_during_simulation_is_rejected(library, monkeypatch):
    runs, a, _, _ = library
    record = json.loads(json.dumps(a))
    restricted = SingleSource(runs, record)
    original = legacy.evaluation_model
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        record['status'] = 'changed'
        return result
    monkeypatch.setattr(legacy, 'evaluation_model', changed)
    with pytest.raises(ValueError, match='completed|manifest changed'):
        eval_run(restricted, a)


@pytest.mark.parametrize('changes', [dict(micros=0), dict(micros=41, profile=evaluation('lucidflex-50k')),
    dict(profile=replace(evaluation(), rule_version='unknown')), dict(micros=41),
    dict(profile=evaluation(activation_fee='-1')), dict(profile=evaluation(daily_loss_limit=False)),
    dict(sampling=replace(SAMPLE, computational_horizon_weekdays=2))])
def test_evaluation_contract_rejections_precede_sampling(library, changes):
    runs, a, _, _ = library
    with pytest.raises(ValueError):
        eval_run(runs, a, **changes)


def test_opposite_phase_contracts_and_invalid_simulation_settings_reject(library):
    runs, a, _, _ = library
    with pytest.raises(ValueError, match='EvaluationProfile'):
        eval_run(runs, a, profile=funded())
    with pytest.raises(ValueError, match='FundedProfile'):
        funded_run(runs, a, profile=evaluation())
    with pytest.raises(ValueError, match='phase-neutral'):
        funded_run(runs, a, sampling=SAMPLE)
    for args in [dict(simulations=0), dict(seed=-1), dict(max_micros=True)]:
        with pytest.raises(ValueError): SimulationConfig(**args)
    with pytest.raises(ValueError): SamplingConfig(0)
    with pytest.raises(ValueError): EvaluationSamplingConfig(chain_simulations=1)
    with pytest.raises(ValueError): rule_version('unknown')


def test_inspectable_component_captures_preserve_saved_product_outputs(library, tmp_path):
    runs, a, b, recovery = library
    def preserved():
        return {str(p.relative_to(runs.root.parent)):sha256(p.read_bytes()).hexdigest()
                for folder in (runs.root, runs.root.parent / 'prop_analyses')
                for p in folder.rglob('*') if p.is_file()}
    before = preserved()
    results = dict(evaluation=eval_run(runs, a), funded=funded_run(runs, a),
        zero_pass_evaluation=eval_run(runs, b, micros=1), funded_without_passes=funded_run(runs, b, micros=10),
        censored_evaluation=eval_run(runs, a, profile=evaluation('lucidflex-50k'), micros=1,
            sampling=replace(SAMPLE, computational_horizon_weekdays=2)),
        censored_funded=funded_run(runs, a, micros=1, horizon_weekdays=4),
        risk_breach=eval_run(runs, recovery))
    for name, result in results.items():
        (tmp_path / (name + '.json')).write_text(json.dumps(asdict(result), indent=2, allow_nan=False))
    assert results['evaluation'].acquisition['cost_per_funded'] == 178
    assert results['evaluation'].acquisition['replacement_days'] == 2
    assert results['funded'].payouts['mean_trader_payout'] == 13000
    assert results['funded_without_passes'].payouts['mean_trader_payout'] == 13000
    assert results['censored_funded'].survival['mean_terminal_lifetime_weekdays'] is None
    assert preserved() == before
    (tmp_path / 'verification.json').write_text(json.dumps(dict(synthetic=True,
        library=str(runs.root.parent), source_ids=dict(winner=a['id'], low_profit=b['id'], risk_breach=recovery['id']),
        captures=list(results), unchanged_saved_files=len(before),
        product_sources_and_reports_preserved=True,
        scope='Development component captures on normal saved backtests; no new product mode or report store'), indent=2))


@pytest.mark.parametrize('firm,expected', [
    ('Apex', '54e3c71eccb1236a31e2f2d47a3b790e4acfcb94c75f8069bbeb347c2e8e7e08'),
    ('Lucid', '3ebc4d1ee7836577dbb2637b38f81278a193f1cf07b562a91b9af2fe9ceb8c83'),
])
def test_full_legacy_calculation_is_identical_to_pre_extraction_baseline(firm, expected):
    settings = legacy.resolved_settings(dict(PROP_FIRM=firm, MAX_TOTAL_NQ='0.3', OUT_OF_SAMPLE_FROM='2026-01-09'))
    result = legacy.calculate(legacy_rows(), settings)
    # Entire calculations payload: schemas, draws, diagnostics, economics,
    # pairs, frozen holdout, distributions and history, captured before editing.
    assert sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest() == expected

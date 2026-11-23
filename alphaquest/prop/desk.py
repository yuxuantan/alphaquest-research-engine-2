"""Fixed-size Prop Desk measurements over one verified saved trade history."""

from dataclasses import asdict
from pathlib import Path
from statistics import mean, median

from .adapter import digest as file_digest, source_record
from .commissions import source_instrument
from .funded_profiles import simulate_funded_profile
from .native_analysis import evaluation_model, wilson
from .phase_profiles import (
    EvaluationProfile, FundedProfile, SamplingConfig, SavedTradeSource,
    SimulationConfig, SourceCosts, prepare_phase_source, provenance, rule_version,
    verify_phase_source,
)
from ..optimization_cache import digest

MODE = 'prop_desk_fixed'
VERSION = 'prop-desk-fixed-v1'
REQUEST_PREFIX = 'prop-desk-fixed:'
PATHS = 1_000
SEED = 42
BLOCK_WEEKDAYS = 5
SOURCE_COSTS = SourceCosts(mode='source')
PROFILES = {
    'apex-50k-eod': dict(label='Apex 50K EOD', caps=dict(evaluation=60, funded=40),
                        evaluation_horizon=21, evaluation_expiry=21, funded_horizon=261),
    'lucidflex-50k': dict(label='LucidFlex 50K', caps=dict(evaluation=40, funded=40),
                         evaluation_horizon=60, evaluation_expiry=None, funded_horizon=261),
}


def prepare(runs, request, configuration):
    """Use the ordinary phase source checks and retain their exact sampled input."""
    profile_id, phase = request.profile_id, request.phase
    lucid = profile_id == 'lucidflex-50k'
    version = rule_version(profile_id)
    if phase == 'evaluation':
        profile = EvaluationProfile(profile_id, version, '80.50' if lucid else '49',
                                    '0' if lucid else '129')
    else:
        profile = FundedProfile(profile_id, version)
    source = SavedTradeSource(request.source_backtest_id, trade_file='')
    if not source_instrument(source_record(runs, source.source_backtest_id)):
        raise ValueError('Prop Desk requires an identified USD NQ or MNQ saved backtest.')
    simulation = SimulationConfig(PATHS, SEED, PROFILES[profile_id]['caps'][phase])
    sampling = SamplingConfig(BLOCK_WEEKDAYS)
    snapshot, days, settings = prepare_phase_source(
        runs, source, profile, request.micros, simulation, None, SOURCE_COSTS)
    verify_phase_source(runs, source, snapshot)
    evidence = provenance(phase, snapshot, profile, request.micros, simulation, sampling)
    # Use the numerical owners' manifest and separately identify the Desk adapter.
    evidence['implementation_sha256']['desk.py'] = file_digest(Path(__file__))
    identity = digest(dict(version=VERSION, configuration=configuration, provenance=evidence,
                           source_days_sha256=digest(days)))
    return dict(profile=profile, source=source, simulation=simulation, sampling=sampling,
                days=days, settings=settings, evidence=evidence, identity=identity)


def calculate(runs, request, configuration, prepared):
    source = prepared['source']
    evidence = prepared['evidence']
    verify_phase_source(runs, source, evidence['source'])
    horizon = configuration['observation_sessions']
    profile = prepared['profile']
    if request.phase == 'evaluation':
        results, paths, rules = evaluation(prepared, horizon)
    else:
        component = simulate_funded_profile(
            runs, source, profile, request.micros, horizon, prepared['simulation'],
            sampling=prepared['sampling'], costs=SOURCE_COSTS)
        if component.provenance['source'] != evidence['source'] or (
            component.provenance['kernel'] != evidence['kernel']
        ):
            raise ValueError('The Funded source or kernel changed during simulation.')
        paths = component.paths
        rules = dict(component.provenance['rules'], trail_updates='End of session before payout deduction',
                     max_mnq=prepared['simulation'].max_micros)
        if profile.profile_id == 'lucidflex-50k':
            rules.update(withdrawal_fraction=.5, payout_timing=(
                'First eligible observed trade close in the intraday request window, otherwise session close. '
                'An intraday request ends trading for that session.'))
        else:
            rules.update(payout_share=1, payout_timing='At session close.')
        evidence['account_rule_sha256'] = component.provenance['account_rule_sha256']
        evidence['receipt_convention'] = component.provenance['receipt_convention']
        results = funded_measurements(paths, rules)
    verify_phase_source(runs, source, evidence['source'])
    return results, paths, dict(starting_balance=50_000, **rules)


def evaluation(prepared, horizon):
    """Score single attempts using the account kernel, without an acquisition chain."""
    profile = prepared['profile']
    lucid = profile.profile_id == 'lucidflex-50k'
    simulation, sampling = prepared['simulation'], prepared['sampling']
    options = dict(consistency=profile.consistency_percent / 100,
                   inactivity_enforced=profile.lucid_inactivity_enforced) if lucid else {}
    sample = evaluation_model(
        prepared['days'], prepared['evidence']['micros'], simulation.simulations,
        simulation.seed, sampling.block_weekdays, prepared['settings'],
        deadline=horizon, chain=False, max_micros=simulation.max_micros, **options)
    expiry = PROFILES[profile.profile_id]['evaluation_expiry']
    names = {'passed': 'passed', 'blown': 'breached',
             'timeout': 'provider_expired' if expiry is not None else 'observation_cutoff'}
    counts = dict.fromkeys(names.values(), 0)
    paths, passing_days = [], []
    for status, sessions in zip(sample['outcomes'].tolist(), sample['days'].tolist(), strict=True):
        outcome = names[status]
        counts[outcome] += 1
        paths.append(dict(outcome=outcome, trading_sessions=sessions))
        if outcome == 'passed':
            passing_days.append(sessions)
    results = dict(outcome_counts=counts,
                   probabilities={key: count / len(paths) for key, count in counts.items()},
                   pass_rate_interval_95=wilson(counts['passed'], len(paths)),
                   median_trading_days_to_target=median(passing_days) if passing_days else None)
    rules = dict(profit_target=3000, maximum_trailing_drawdown=2000,
                 trailing_floor_lock_profit=100 if lucid else 3000,
                 daily_loss_limit=1200 if lucid else 1000,
                 daily_loss_action='Pause trading for the session unless the account floor is breached.',
                 trail_updates='End of session',
                 consistency_percent=profile.consistency_percent if lucid else None,
                 pass_checked='At session close' if lucid else 'After a trade closes',
                 provider_expiry_trading_sessions=expiry,
                 inactivity_enforced=False,
                 max_mnq=simulation.max_micros)
    prepared['evidence']['account_rule_sha256'] = digest(dict(profile=asdict(profile), rules=rules,
                                                             kernel=prepared['evidence']['kernel']))
    return results, paths, rules


def funded_measurements(paths, rules):
    total = len(paths)
    payout_count = len(rules['ladder'])
    milestones = []
    for index in range(payout_count):
        reached = [path['trader_payouts'][index][0] for path in paths
                   if len(path['trader_payouts']) > index]
        milestones.append(dict(payout=index + 1, reached=len(reached),
                               probability=len(reached) / total,
                               median_trading_day=median(reached) if reached else None,
                               account_deduction_cap=rules['ladder'][index]))
    breached = sum(path['outcome'] == 'blown' for path in paths)
    breached_before = sum(path['outcome'] == 'blown' and not path['trader_payouts'] for path in paths)
    return dict(probability_any_payout=milestones[0]['probability'],
                probability_complete_ladder=milestones[-1]['probability'],
                probability_breach=breached / total,
                probability_breach_before_first_payout=breached_before / total,
                open_at_cutoff=sum(path['lifetime_censored'] for path in paths),
                inactive=sum(path['outcome'] == 'inactive' for path in paths),
                mean_account_deductions=mean(sum(value for _, value in path['gross_account_deductions'])
                                             for path in paths),
                mean_trader_receipts=mean(sum(value for _, value in path['trader_payouts'])
                                          for path in paths),
                milestones=milestones)
